from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models
from app.api.health import router as health_router
from app.config import get_settings
from app.database import init_db, seed_plan_limits
from app.routers import (
    admin,
    analytics,
    auth,
    billing,
    dashboard,
    jobs,
)
from app.services.worker_service import worker_service

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Iniciando DataLink API...")

    init_db()
    print("✅ Base de datos inicializada")

    seed_plan_limits()
    print("✅ Plan limits inicializados")

    if settings.worker_enabled:
        worker_service.start()
        print("✅ Worker iniciado")
    else:
        print("⏸️ Worker deshabilitado")

    try:
        yield
    finally:
        if settings.worker_enabled:
            worker_service.stop()

        print("👋 DataLink API detenida")


app = FastAPI(
    title="Data_Link API",
    version="1.0.0",
    lifespan=lifespan,
    description=(
        "Asynchronous CSV and JSON processing API for deduplication, "
        "filtering, and lightweight data cleanup.\n\n"
        "Built for developers and designed as a reliable processing "
        "core within the evi_link ecosystem."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)

app.include_router(jobs.router)
app.include_router(auth.router)
app.include_router(analytics.router)
app.include_router(billing.router)
app.include_router(dashboard.router)
app.include_router(admin.router)


@app.get("/")
async def root():
    return {
        "message": "Data_Link API v1.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }