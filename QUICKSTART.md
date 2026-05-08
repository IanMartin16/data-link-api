# 🚀 Guía de Inicio Rápido - DataLink API

## Pasos para iniciar (5 minutos)

### 1. Preparar entorno

```bash
# Crear entorno virtual
python -m venv venv

# Activar
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Configurar variables

```bash
# Copiar archivo de configuración
cp .env.example .env

# El archivo .env ya tiene valores por defecto que funcionan
# No necesitas modificarlo para desarrollo local
```

### 3. Levantar servicios (PostgreSQL + MinIO)

```bash
docker-compose up -d
```

### 4. Configurar MinIO

1. Abrir navegador en: http://localhost:9001
2. Login:
   - Usuario: `minioadmin`
   - Password: `minioadmin`
3. Crear bucket:
   - Click en "Buckets" → "Create Bucket"
   - Nombre: `datalink-uploads`
   - Click "Create Bucket"

### 5. Iniciar API

```bash
uvicorn app.main:app --reload
```

✅ **La API está lista en http://localhost:8000**

## Probar la API

### Opción 1: Documentación interactiva (recomendado)

Abre http://localhost:8000/docs en tu navegador

### Opción 2: Usando curl

```bash
# Procesar archivo CSV de prueba
curl -X POST "http://localhost:8000/api/v1/process" \
  -F "file=@test_data.csv" \
  -F "format=csv" \
  -F "preset=REMOVE_DUPLICATES_BY_EMAIL"

# Respuesta:
# {
#   "job_id": "abc-123-def...",
#   "status": "PENDING",
#   "status_url": "/api/v1/jobs/abc-123-def...",
#   "message": "Job creado exitosamente"
# }

# Consultar estado (reemplaza JOB_ID)
curl http://localhost:8000/api/v1/jobs/JOB_ID

# Descargar resultado (cuando status sea COMPLETED)
curl http://localhost:8000/api/v1/jobs/JOB_ID/download -o resultado.csv
```

## Verificar que todo funciona

```bash
# 1. Verificar salud de la API
curl http://localhost:8000/health
# Respuesta: {"status":"healthy"}

# 2. Ver presets disponibles
curl http://localhost:8000/api/v1/presets

# 3. Procesar archivo de prueba
curl -X POST "http://localhost:8000/api/v1/process" \
  -F "file=@test_data.csv" \
  -F "format=csv" \
  -F "preset=REMOVE_DUPLICATES_BY_EMAIL"
```

## Solución de problemas

### Error: "Connection refused" al iniciar la API

**Causa**: PostgreSQL o MinIO no están corriendo

**Solución**:
```bash
docker-compose up -d
docker ps  # Verificar que ambos contenedores estén UP
```

### Error: "Bucket does not exist"

**Causa**: No se creó el bucket en MinIO

**Solución**:
1. Ir a http://localhost:9001
2. Crear bucket llamado `datalink-uploads`

### Error al importar módulos

**Causa**: Entorno virtual no está activado o dependencias no instaladas

**Solución**:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

## Próximos pasos

1. ✅ Lee el README.md completo
2. ✅ Prueba todos los presets
3. ✅ Prueba con archivos JSON
4. ✅ Experimenta con filtros personalizados
5. ✅ Revisa la documentación en /docs

## Comandos útiles

```bash
# Ver logs de PostgreSQL
docker logs datalink-postgres

# Ver logs de MinIO
docker logs datalink-minio

# Parar todo
docker-compose down

# Parar y borrar datos
docker-compose down -v

# Reiniciar desde cero
docker-compose down -v
docker-compose up -d
# Recrear bucket en MinIO
```

¡Listo para comenzar! 🎉
