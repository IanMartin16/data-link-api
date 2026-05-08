from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import init_db
from app.routers import jobs, auth
from app.services.worker_service import worker_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Iniciando DataLink API...")
    init_db()
    print("✅ Base de datos inicializada")
    worker_service.start()
    print("✅ Worker iniciado")
    
    yield
    
    # Shutdown
    worker_service.stop()
    print("👋 DataLink API detenida")

app = FastAPI(
    title="Data_Link API",
    version="1.0.0",
    lifespan=lifespan,
    description=(
        "Asynchronous CSV and JSON processing API for deduplication, filtering, "
        "and lightweight data cleanup.\n\n"
        "Built for developers and designed as a reliable processing core within the Evilink ecosystem."
    )
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(jobs.router)
app.include_router(auth.router)

@app.get("/")
async def root():
    return {
        "message": "DataLink API v1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}
