# DataLink API

API para procesamiento y deduplicación de archivos de datos (CSV y JSON).

## 🚀 Características

- ✅ Procesamiento asíncrono de archivos hasta 500MB
- ✅ Soporte para CSV y JSON
- ✅ 5 operaciones predefinidas (presets)
- ✅ Filtros personalizables
- ✅ Deduplicación de registros
- ✅ Estadísticas de procesamiento
- ✅ API REST con FastAPI
- ✅ Storage con MinIO (compatible S3)

## 📋 Requisitos

- Python 3.11+
- Docker y Docker Compose
- PostgreSQL (via Docker)
- MinIO (via Docker)

## 🛠️ Instalación

### 1. Clonar/Descargar el proyecto

```bash
cd data-link-fastapi
```

### 2. Crear entorno virtual

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate  # Windows
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env si es necesario
```

### 5. Levantar infraestructura (PostgreSQL + MinIO)

```bash
docker-compose up -d
```

### 6. Configurar MinIO

1. Abrir http://localhost:9001
2. Login: `minioadmin` / `minioadmin`
3. Crear bucket llamado: `datalink-uploads`

### 7. Iniciar la API

```bash
uvicorn app.main:app --reload
```

La API estará disponible en:
- API: http://localhost:8000
- Documentación interactiva: http://localhost:8000/docs
- Documentación alternativa: http://localhost:8000/redoc

## 📖 Uso

### Crear un job de procesamiento

```bash
curl -X POST "http://localhost:8000/api/v1/process" \
  -F "file=@datos.csv" \
  -F "format=csv" \
  -F "preset=REMOVE_DUPLICATES_BY_EMAIL"
```

Respuesta:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PENDING",
  "status_url": "/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000",
  "message": "Job creado exitosamente"
}
```

### Consultar estado del job

```bash
curl http://localhost:8000/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000
```

### Descargar resultado

```bash
curl http://localhost:8000/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/download -o resultado.csv
```

### Ver presets disponibles

```bash
curl http://localhost:8000/api/v1/presets
```

## 🎯 Presets Disponibles

1. **REMOVE_DUPLICATES_BY_EMAIL** - Elimina duplicados por email
2. **REMOVE_DUPLICATES_BY_ID** - Elimina duplicados por ID
3. **REMOVE_DUPLICATES_BY_EMAIL_AND_PHONE** - Duplicados por email + teléfono
4. **FILTER_ACTIVE_ONLY** - Solo registros con status='active'
5. **REMOVE_EMPTY_RECORDS** - Elimina registros vacíos

## 🔧 Filtros Personalizados (Opcional)

Puedes agregar un filtro adicional al procesamiento:

```bash
curl -X POST "http://localhost:8000/api/v1/process" \
  -F "file=@datos.csv" \
  -F "format=csv" \
  -F "preset=REMOVE_DUPLICATES_BY_EMAIL" \
  -F "filter_field=country" \
  -F "filter_value=Mexico" \
  -F "filter_operator=EQUALS"
```

**Operadores disponibles:**
- `EQUALS` - Igual a
- `NOT_EQUALS` - Diferente de
- `CONTAINS` - Contiene
- `NOT_CONTAINS` - No contiene
- `STARTS_WITH` - Empieza con
- `ENDS_WITH` - Termina con

## 📁 Estructura del Proyecto

```
data-link-fastapi/
├── app/
│   ├── __init__.py
│   ├── main.py              # Aplicación principal
│   ├── config.py            # Configuración
│   ├── database.py          # Setup de BD
│   │
│   ├── models/              # Modelos SQLAlchemy
│   │   └── job.py
│   │
│   ├── schemas/             # Schemas Pydantic
│   │   └── job.py
│   │
│   ├── enums/               # Enumeraciones
│   │   ├── job_status.py
│   │   ├── file_format.py
│   │   ├── preset_operation.py
│   │   └── filter_operator.py
│   │
│   ├── services/            # Lógica de negocio
│   │   ├── storage_service.py
│   │   ├── processing_service.py
│   │   └── worker_service.py
│   │
│   ├── processors/          # Procesadores de datos
│   │   ├── base_processor.py
│   │   ├── csv_processor.py
│   │   └── json_processor.py
│   │
│   └── routers/             # Endpoints API
│       └── jobs.py
│
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

## 🧪 Testing

```bash
# Crear archivo de prueba CSV
echo "id,email,status
1,test@example.com,active
2,test@example.com,active
3,user@example.com,inactive" > test.csv

# Procesarlo
curl -X POST "http://localhost:8000/api/v1/process" \
  -F "file=@test.csv" \
  -F "format=csv" \
  -F "preset=REMOVE_DUPLICATES_BY_EMAIL"

# Resultado: 2 registros (eliminó 1 duplicado)
```

## 🚀 Deploy a Producción

### Railway

```bash
# Instalar CLI
npm i -g @railway/cli

# Login
railway login

# Crear proyecto
railway init

# Agregar PostgreSQL
railway add --plugin postgresql

# Deploy
railway up
```

### Fly.io

```bash
# Instalar CLI
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Launch
fly launch

# Agregar PostgreSQL
fly postgres create

# Deploy
fly deploy
```

## 📊 Consumo de Recursos

- **Memoria**: ~100-200MB en reposo
- **Memoria en procesamiento**: +200-500MB (archivos grandes)
- **CPU**: Bajo en reposo, alto durante procesamiento

## 🔒 Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `DATABASE_URL` | URL de PostgreSQL | - |
| `MINIO_ENDPOINT` | Endpoint de MinIO | localhost:9000 |
| `MINIO_ACCESS_KEY` | Access key MinIO | minioadmin |
| `MINIO_SECRET_KEY` | Secret key MinIO | minioadmin |
| `MINIO_BUCKET` | Nombre del bucket | datalink-uploads |
| `MAX_FILE_SIZE_MB` | Tamaño máximo archivo | 500 |
| `WORKER_ENABLED` | Habilitar worker | true |
| `WORKER_INTERVAL_SECONDS` | Intervalo del worker | 5 |

## 📝 Licencia

MIT

## 👨‍💻 Autor

DataLink API - Desarrollado con FastAPI y Python
