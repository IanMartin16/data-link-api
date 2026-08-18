"""
Arranque del worker en su propio proceso.

    python -m app.worker

NO es otra implementacion: la logica sigue viviendo en worker_service.py.
Esto solo le da un proceso propio, que es lo que APScheduler no hace por si
mismo — BackgroundScheduler corre en un hilo del proceso que lo arranca, asi
que si worker_service.start() se llama desde el startup de FastAPI, el
procesamiento sigue dentro de uvicorn.

Con esto:
  - la API se despliega y reinicia sin tocar los jobs en curso
  - un job pesado no le quita CPU a uvicorn
  - los recursos de cada servicio se dimensionan por separado

En el servicio de la API hay que poner WORKER_ENABLED=false, o los dos
procesos consumen la misma cola.
"""

import logging
import signal
import threading

# Importar TODOS los modelos aunque no se usen aqui: registran sus tablas en
# Base.metadata. Sin esto, la FK processing_jobs.user_id -> users.id no
# resuelve en este proceso y el claim revienta con NoReferencedTableError.
from app.models import job, plan_limits, user  # noqa: F401

from app.config import get_settings
from app.services.worker_service import worker_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

settings = get_settings()

_stop = threading.Event()


def _handle_signal(signum, frame):
    """
    Railway manda SIGTERM en cada deploy y espera antes de matar el proceso.
    Solo se levanta la bandera; el apagado real ocurre abajo.
    """
    log.info("Senal %s recibida: cerrando el worker.", signum)
    _stop.set()


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    if not settings.worker_enabled:
        log.error("WORKER_ENABLED esta en false: este proceso no haria nada.")
        return

    worker_service.start()
    log.info("Worker corriendo en proceso propio. Esperando trabajo.")

    _stop.wait()

    # scheduler.shutdown() espera por defecto a que terminen los jobs en
    # ejecucion, asi que un job en vuelo se completa antes de cerrar.
    log.info("Esperando a que termine el trabajo en curso...")
    worker_service.stop()
    log.info("Worker detenido.")


if __name__ == "__main__":
    main()
