"""
Espera a que haya un job en PROCESSING y manda SIGTERM al worker.

    python kill_on_processing.py

Existe porque la ventana entre que el job se crea y el worker lo reclama es
de un par de segundos, y disparar el kill a mano cae siempre ahi. Esto lo
dispara cuando el job YA esta corriendo, que es el caso que interesa probar.

Uso:
  1. terminal A:  python -m app.worker
  2. terminal B:  python kill_on_processing.py     (se queda esperando)
  3. sube el archivo desde la consola
  4. mira la terminal A
"""

import subprocess
import sys
import time

from app.database import SessionLocal
from app.models.job import ProcessingJob
from app.enums.job_status import JobStatus

TIMEOUT = 300  # segundos esperando a que aparezca un job corriendo


def worker_pid() -> int | None:
    """PID del proceso padre del worker (los hijos del pool comparten cmdline)."""
    result = subprocess.run(
        ["pgrep", "-o", "-f", "app.worker"], capture_output=True, text=True
    )
    return int(result.stdout.strip()) if result.stdout.strip() else None


def main() -> None:
    pid = worker_pid()
    if pid is None:
        print("No encuentro el worker corriendo. Arrancalo primero.")
        sys.exit(1)

    print(f"Worker PID {pid}. Esperando a que un job entre en PROCESSING...\n")

    deadline = time.time() + TIMEOUT

    while time.time() < deadline:
        db = SessionLocal()
        try:
            job = (
                db.query(ProcessingJob)
                .filter(ProcessingJob.status == JobStatus.PROCESSING)
                .order_by(ProcessingJob.started_at.desc())
                .first()
            )

            if job is not None:
                print(f"Job {job.id} en PROCESSING ({job.original_file_name})")
                print(f"Enviando SIGTERM al PID {pid}\n")
                subprocess.run(["kill", "-TERM", str(pid)])

                print("Mira la terminal del worker:")
                print("  OK    -> 'Senal 15 recibida', luego SILENCIO mientras")
                print("           procesa, y hasta el final 'Worker detenido'.")
                print("           El job debe quedar COMPLETED.")
                print("  FALLA -> 'Worker detenido' en 1-2 s y el job atorado")
                print("           en PROCESSING.\n")
                return
        finally:
            db.close()

        time.sleep(0.2)

    print("Se acabo el tiempo sin ver ningun job en PROCESSING.")


if __name__ == "__main__":
    main()
