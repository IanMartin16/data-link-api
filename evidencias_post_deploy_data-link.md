# Data_Link — Hito Post Deploy Railway

Estado general

Producto: Data_Link API
Versión: v1.0.0
Ambiente: Producción controlada en Railway
Estado actual: En observación post deploy por 48 horas
Fecha de validación: 13–14 mayo 2026
Resultado: Deploy exitoso, pruebas funcionales completadas y rendimiento sobresaliente.
---

## Resumen ejecutivo

Data_Link fue desplegado exitosamente en Railway como API productiva para procesamiento asíncrono de archivos CSV y JSON.

Durante el post deploy se validaron los componentes principales del producto:

API FastAPI en Railway
Postgres Railway
Railway Object Storage / S3-compatible
Worker de procesamiento
Worker de cleanup
Planes FREE / STARTER
API keys productivas
Integración con Status-Hub
Procesamiento CSV/JSON
Descarga de resultados
Limpieza automática de archivos en bucket

El resultado fue altamente positivo. Data_Link demostró rendimiento sobresaliente en producción, con procesamiento de archivos grandes en tiempos muy bajos y consumo de memoria controlado después de ajustes en processing_service.py.
---

## Arquitectura productiva validada

La arquitectura final para este deploy quedó así:

Cliente / API Consumer
        ↓
Data_Link API - Railway
        ↓
Postgres Railway
        ↓
Railway Object Storage / S3-compatible
        ↓
Worker de procesamiento
        ↓
Worker de limpieza / cleanup
        ↓
Status-Hub observability

Se decidió no utilizar MinIO en Railway para evitar el costo de mantener un servicio adicional corriendo 24/7.

MinIO queda reservado para ambiente local.

Local/dev  → MinIO
Prod       → Railway Object Storage
--- 

## Decisiones técnicas importantes

1. Railway Object Storage en lugar de MinIO productivo

Se validó que Data_Link puede trabajar correctamente con storage S3-compatible sin requerir MinIO en producción.

Esto reduce:

- consumo de RAM
- consumo de CPU
- costo operativo
- complejidad de infraestructura
- mantenimiento de un servicio adicional

## 2. Storage híbrido

Data_Link quedó preparado para operar de forma híbrida:

STORAGE_BACKEND=minio → local
STORAGE_BACKEND=s3    → producción

La lógica de negocio no depende directamente de Railway ni de MinIO, sino de un StorageService compatible.
---

### Validación de procesamiento en producción

Prueba 10k CSV
``` json 
{
  "records": 10000,
  "file_size_mb": 0.76,
  "duplicates_removed": 5400,
  "records_kept": 4600,
  "reduction_percentage": 54,
  "status": "COMPLETED"
}
``` 
Resultado: exitoso.
---

Prueba 30k CSV
``` json
{
  "records": 30000,
  "file_size_mb": 1.67,
  "duplicates_removed": 3500,
  "records_kept": 26500,
  "reduction_percentage": 11.67,
  "status": "COMPLETED"
}
```
Resultado: exitoso.
---

Prueba 800k CSV
``` json
{
  "records": 800000,
  "file_size_mb": 47.27,
  "duplicates_removed": 535000,
  "records_kept": 265000,
  "reduction_percentage": 66.88,
  "status": "COMPLETED"
}
```
Tiempo aproximado:

23.45 segundos

Resultado: exitoso.
---

Prueba 1M CSV
``` json
{
  "records": 1000000,
  "file_size_mb": 59.13,
  "duplicates_removed": 735000,
  "records_kept": 265000,
  "reduction_percentage": 73.5,
  "status": "COMPLETED"
}
```
Mejor tiempo observado:

~29.26 segundos en producción

En una prueba experimental posterior se observó incluso un resultado de aproximadamente:

~6.61 segundos

Aunque esa prueba provocó apagado posterior de la app, confirmó el potencial extremo del motor y abrió una línea futura de optimización controlada.
---

Prueba JSON 300k
``` json
{
  "records": 300000,
  "file_size_mb": 43.03,
  "duplicates_removed": 40000,
  "records_kept": 260000,
  "reduction_percentage": 13.33,
  "status": "COMPLETED"
}
```
Tiempo aproximado:

19.99 segundos

Resultado: exitoso.
---

### Observaciones de memoria RAM

Durante las primeras pruebas pesadas se observó un pico aproximado de:

~260 MB RAM

Después de ajustes en processing_service.py, se logró reducir el pico en una prueba de 800k CSV a aproximadamente:

~190 MB RAM

En prueba JSON de 300k registros, el consumo observado fue aproximadamente:

~136 MB RAM

La memoria en idle regresó a un rango aproximado de:

~106 MB RAM

Esto indica que no se observó una fuga persistente de memoria. El consumo sube durante procesamiento pesado, pero vuelve a estabilizarse.
---

### Cleanup de bucket validado

Se implementó y validó el ciclo de limpieza de archivos en bucket.

Cada job conserva metadata histórica en Postgres, pero los archivos físicos son eliminados del bucket después de expirar.

Campos agregados y validados:

expires_at
files_deleted
files_deleted_at

Resultado validado:

✅ input_file_url eliminado del bucket
✅ output_file_url eliminado del bucket
✅ files_deleted = true
✅ files_deleted_at registrado
✅ metadata histórica conservada

Esto permite controlar costos de storage y evita acumulación silenciosa de archivos.
---

### Integración con Status-Hub

Data_Link ya fue integrado y consumido por Status-Hub.

Estado observado:

Status: Operational
Health: Healthy
Latency observada: ~23ms

Esto confirma que Data_Link ya forma parte del ecosistema de observabilidad de Evilink.
---

### Planes y límites validados

Planes activos:

FREE
STARTER

FREE

10 archivos/mes
10 MB por archivo
200k registros por archivo
2 presets
sin custom filters
20 requests/hora

STARTER

100 archivos/mes
100 MB por archivo
2M registros por archivo
5 presets
custom filters habilitados
100 requests/hora

La prueba de 1M registros confirmó que STARTER puede soportar procesamiento real de alto valor.
---

### Hallazgos clave

1. Data_Link tiene rendimiento premium

El motor de procesamiento superó expectativas, especialmente en CSV grandes.

Procesar 1M registros en producción en menos de un minuto confirma que Data_Link tiene potencial comercial fuerte.

2. El storage productivo funciona correctamente

Railway Object Storage funcionó como alternativa productiva a MinIO, reduciendo complejidad y evitando un servicio adicional.

3. El cleanup es indispensable

El cleanup no es opcional. Es parte central del modelo operativo para evitar crecimiento de storage y controlar costos.

4. STARTER debe valorarse cuidadosamente

Los límites actuales de STARTER permiten uso real y de alto valor. No debe ser tratado como un plan barato o trivial.

5. Data_Link Transform tiene potencial premium

El mismo motor puede impulsar una línea superior con:

conversión a Parquet
optimización de datasets
procesamiento avanzado
priority processing
features premium
---

### Estado final del hito

Data_Link Railway Deploy: COMPLETADO
Post deploy inicial: EXITOSO
Storage productivo: VALIDADO
Cleanup: VALIDADO
Status-Hub: INTEGRADO
Pruebas grandes: SUPERADAS
RAM: OPTIMIZADA Y EN OBSERVACIÓN
Estado actual: OBSERVACIÓN 48H
---

### Pendientes inmediatos

1. Observar estabilidad durante 48 horas.
2. Revisar Railway Metrics: RAM, CPU, logs y storage.
3. Confirmar que Status-Hub se mantenga Operational.
4. No introducir cambios grandes durante observación.
5. Definir precio STARTER con base en costo real y valor entregado.
6. Preparar siguiente fase: Stripe / pricing / launch page.

### Conclusión

Data_Link completó exitosamente su despliegue productivo en Railway y validó su capacidad como producto real dentro del ecosistema Evilink.

El procesamiento de archivos grandes, la integración con storage S3-compatible, el cleanup automático, la observabilidad mediante Status-Hub y la estabilidad inicial confirman que Data_Link está listo para entrar en una fase de observación final antes de declararlo launch ready.

Mi opinión: este es uno de los hitos más importantes de Evilink hasta ahora, porque Data_Link ya no es solo una API funcional; es una pieza comercialmente defendible, técnicamente eficiente y operativamente viable.
---