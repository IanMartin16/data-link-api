# 🚀 Deploy DataLink V1 a Railway - Guía Completa

## 📋 Pre-Deploy Checklist

### ✅ Lo que YA tienes
- [x] API funcionando local
- [x] Pricing y límites implementados
- [x] Base de datos PostgreSQL
- [x] MinIO para storage
- [x] Autenticación con API Key
- [x] Validaciones de planes

### ⏳ Lo que falta antes de deploy

#### 1. Variables de Entorno en Producción

```bash
# .env.production (NO commitear, solo para Railway)

# Database (Railway PostgreSQL)
DATABASE_URL=postgresql://postgres:password@host:5432/railway

# MinIO (Railway o externo)
MINIO_ENDPOINT=minio.railway.app:9000
MINIO_ACCESS_KEY=tu_access_key
MINIO_SECRET_KEY=tu_secret_key
MINIO_BUCKET_NAME=datalink-prod
MINIO_USE_SSL=true

# API
API_URL=https://datalink-api.up.railway.app

# CORS (tu dominio)
ALLOWED_ORIGINS=https://tudominio.com,https://www.tudominio.com

# Otros (opcional)
ENVIRONMENT=production
LOG_LEVEL=info
```

---

## 🚂 Paso a Paso: Deploy a Railway

### Paso 1: Preparar tu Proyecto

```bash
cd C:\Users\imart\Desktop\projects\data-link-api

# 1. Copiar archivos de configuración
copy Dockerfile .
copy .dockerignore .
copy railway.json .

# 2. Verificar requirements.txt
# Debe incluir todas las dependencias
cat requirements.txt
```

**requirements.txt debe tener:**
```txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
python-multipart==0.0.6
minio==7.2.0
pydantic==2.5.0
pydantic-settings==2.1.0
pandas==2.1.3
apscheduler==3.10.4
python-dotenv==1.0.0
```

---

### Paso 2: Crear Proyecto en Railway

```bash
# 1. Instalar Railway CLI (opcional)
npm i -g @railway/cli

# O usar la web directamente
# https://railway.app
```

**En Railway Web:**

1. **Nuevo Proyecto:**
   - Click "New Project"
   - Selecciona "Deploy from GitHub repo"
   - Conecta tu repo de GitHub

2. **Agregar PostgreSQL:**
   - Click "+ New"
   - Select "Database" → "PostgreSQL"
   - Railway auto-configura todo
   - Copia la `DATABASE_URL` que te da

3. **Agregar MinIO (Opcional):**
   - Click "+ New"
   - Select "Template" → Busca "MinIO"
   - O usa MinIO externo (AWS S3, Cloudflare R2)

---

### Paso 3: Configurar Variables de Entorno

En Railway Dashboard:

```
Variables → Add Variables:

DATABASE_URL=postgresql://... (auto-generada)
MINIO_ENDPOINT=...
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...
MINIO_BUCKET_NAME=datalink-prod
MINIO_USE_SSL=true
ALLOWED_ORIGINS=https://tudominio.com
```

---

### Paso 4: Deploy

```bash
# Si usas Railway CLI
railway login
railway link
railway up

# O via GitHub
# Push a main → Railway auto-deploy
git add .
git commit -m "Deploy V1 to Railway"
git push origin main
```

**Railway hará:**
1. Detectar `Dockerfile`
2. Build imagen
3. Deploy container
4. Asignar URL pública

---

### Paso 5: Inicializar Base de Datos en Producción

**Opción A: Desde local hacia Railway DB**

```bash
# 1. Obtener DATABASE_URL de Railway
# Ejemplo: postgresql://postgres:pass@containers-us-west-123.railway.app:5432/railway

# 2. Editar init_database_standalone.py
# Cambiar DB_CONFIG a Railway credentials

DB_CONFIG = {
    'host': 'containers-us-west-123.railway.app',
    'port': 5432,
    'database': 'railway',
    'user': 'postgres',
    'password': 'tu_password_railway'
}

# 3. Ejecutar
python scripts/init_database_standalone.py
```

**Opción B: Ejecutar dentro del container Railway**

```bash
# Via Railway CLI
railway run python scripts/init_database_standalone.py

# O crear script de startup
```

---

### Paso 6: Crear Usuario de Prueba en Producción

```bash
# Opción 1: Script local → Railway DB
python scripts/create_user.py test@datalink.com

# Opción 2: Via Railway CLI
railway run python scripts/create_user.py test@datalink.com

# Opción 3: SQL directo
railway connect postgres
# Luego INSERT INTO users...
```

---

### Paso 7: Testing en Producción

```bash
# URL de Railway (ejemplo)
API_URL="https://datalink-api.up.railway.app"
API_KEY="tu_api_key_produccion"

# Test 1: Health check
curl $API_URL/health

# Test 2: Usage
curl -H "X-API-Key: $API_KEY" \
  $API_URL/api/v1/usage

# Test 3: Process file
curl -X POST $API_URL/api/v1/process \
  -H "X-API-Key: $API_KEY" \
  -F "file=@test.csv" \
  -F "format=csv" \
  -F "preset=REMOVE_DUPLICATES_BY_EMAIL"
```

---

## ⚠️ Problemas Comunes

### Error: "Connection refused" (PostgreSQL)

**Causa:** DATABASE_URL incorrecta

**Solución:**
```bash
# En Railway Dashboard
# Variables → DATABASE_URL debe ser:
postgresql://postgres:password@hostname:5432/railway

# NO:
postgresql://localhost:5432/datalink
```

---

### Error: "MinIO connection timeout"

**Causa:** MinIO no accesible desde Railway

**Solución A: Usar Railway MinIO**
```bash
# Deploy MinIO template en Railway
# Usar URL interna: minio.railway.internal:9000
```

**Solución B: Usar S3-compatible externo**
```bash
# Cloudflare R2 (gratis hasta 10GB)
# Backblaze B2
# AWS S3
```

---

### Error: "Import module not found"

**Causa:** Falta dependencia en requirements.txt

**Solución:**
```bash
# Generar requirements completo
pip freeze > requirements.txt

# Verificar
cat requirements.txt
```

---

## 🔒 Seguridad en Producción

### 1. HTTPS Only

Railway auto-provee HTTPS. Forzar en código:

```python
# app/main.py

from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

if settings.environment == "production":
    app.add_middleware(HTTPSRedirectMiddleware)
```

---

### 2. CORS Restrictivo

```python
# app/main.py

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://tudominio.com",
        "https://www.tudominio.com"
    ],  # NO "*" en producción
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

---

### 3. Rate Limiting

```python
# app/middleware/rate_limit.py

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# En endpoints
@limiter.limit("100/hour")
@router.post("/process")
async def create_job(...):
    ...
```

---

## 💰 Costos Estimados Railway

```
PostgreSQL:    $5/mes (Starter)
MinIO/Storage: $0 (usar S3/R2 externo)
API Container: $5/mes (500MB RAM)

Total: ~$10/mes

Con escala:
PostgreSQL:    $20/mes (Pro)
API Container: $20/mes (2GB RAM)
Total: ~$40/mes
```

---

## 📊 Monitoring

### Logs en Railway

```bash
# Via CLI
railway logs

# Via Dashboard
# Project → Deployments → View Logs
```

### Agregar Logging en Código

```python
# app/main.py

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup():
    logger.info("🚀 DataLink API started")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Database: {settings.database_url.split('@')[1]}")
```

---

## 🎯 Post-Deploy Checklist

- [ ] API responde en URL pública
- [ ] PostgreSQL conectada
- [ ] MinIO/S3 funciona
- [ ] Usuario de prueba creado
- [ ] Test `/usage` funciona
- [ ] Test `/process` funciona
- [ ] Test límites FREE (10 archivos)
- [ ] Logs limpios (sin errores)
- [ ] HTTPS funcionando
- [ ] CORS configurado

---

## 🚀 Custom Domain (Opcional)

En Railway:

1. Settings → Domains
2. Click "Generate Domain" o "Custom Domain"
3. Si custom: Agregar DNS records

```
Type: CNAME
Name: api
Value: datalink-api.up.railway.app
```

Resultado: `https://api.tudominio.com`

---

## 📝 Notas Importantes

### PostgreSQL Backups

Railway hace backups automáticos, pero mejor:

```bash
# Backup manual
railway connect postgres
pg_dump railway > backup.sql

# Restore
psql railway < backup.sql
```

### Migraciones Futuras

Usa Alembic para cambios de schema:

```bash
alembic revision --autogenerate -m "Add new column"
alembic upgrade head
```

### Secrets Management

**NUNCA** commitear `.env` a Git:

```bash
# .gitignore
.env
.env.local
.env.production
```

---

## ✅ Ready para Deploy

Cuando todo esté listo:

```bash
# 1. Commit final
git add .
git commit -m "Production ready - V1"
git push origin main

# 2. Railway auto-deploy

# 3. Init DB
railway run python scripts/init_database_standalone.py

# 4. Create test user
railway run python scripts/create_user.py test@datalink.com

# 5. Test
curl https://tu-url.railway.app/health

# 6. 🎉 LIVE!
```

---

¿Alguna duda sobre el deploy? 🚀
