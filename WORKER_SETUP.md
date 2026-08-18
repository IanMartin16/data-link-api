# Separar el worker — qué cambia

## 1. El servicio nuevo

En el **mismo proyecto** de Railway, un segundo servicio apuntando al mismo
repo:

| | API | Worker |
|---|---|---|
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | `python -m app.worker` |
| Health check | sí | ninguno — no expone HTTP |
| `DL_WORKERS` | no aplica | número de vCPU del servicio |
| Resto de variables | iguales | iguales (misma BD, mismo bucket) |

Comparten proyecto, así que se ven por red privada y usan las mismas
credenciales de Postgres y MinIO sin salir a internet.

## 2. Quitar el disparo desde la API

Busca dónde se llama a `process_job` después de `create_job` — probablemente
un `BackgroundTasks` o un hilo en el endpoint. **Bórralo.** La API solo crea
el job en `PENDING`; el worker lo recoge.

Ese es el cambio que hace que un deploy de la API deje de poder matar un
trabajo en curso.

## 3. Variables nuevas

```
DL_WORKERS=2          # procesos del pool. Igual a los vCPU del worker
DL_POLL_INTERVAL=2    # segundos entre consultas cuando la cola está vacía
DL_STALE_MINUTES=30   # un job en PROCESSING más viejo que esto se da por muerto
```

`DL_POLL_INTERVAL` reemplaza al intervalo de 20s que tenías. Con la cola vacía
son consultas baratísimas; bajarlo a 2 segundos quita casi toda la espera de
recogida que veías en `started_at`.

## 4. Lo que resuelve

**Apagado ordenado.** El worker atrapa `SIGTERM`: termina el job actual y no
toma otro. Railway espera antes de matar el proceso, así que un deploy normal
ya no interrumpe nada.

**Barrido al arrancar.** Cualquier job en `PROCESSING` más viejo que
`DL_STALE_MINUTES` se marca `FAILED` con un mensaje claro. Es la red que
faltaba: un job no sobrevive a un reinicio, así que uno viejo en ese estado
está muerto por definición.

**Toma atómica.** `FOR UPDATE SKIP LOCKED` permite escalar a varias réplicas
del worker sin que dos tomen el mismo job. Si lo haces, sube
`DL_STALE_MINUTES` por encima del job más largo que esperes — si no, una
réplica podría marcar como muerto un trabajo que otra sí está corriendo.

## 5. Verificación

1. Sube un archivo desde la consola → la fila nace en `PENDING`
2. En los logs del worker: `Job <id> tomado`
3. Al terminar: `Job <id> completado en Xs`
4. Reinicia la **API** mientras un job corre → el job termina igual
5. Reinicia el **worker** mientras un job corre → al volver, el barrido lo
   marca `FAILED` en vez de dejarlo colgado

El paso 4 es el que antes fallaba.

## 6. Pendiente relacionado

`processing_service.process_job` llama a `mark_as_processing()`, y el worker ya
lo hizo al tomar el job. No rompe nada — vuelve a escribir el mismo estado y
pisa `started_at` con un valor unos milisegundos posterior. Si quieres que
`started_at` sea exacto, quita esa llamada del servicio y déjala solo en el
worker.
