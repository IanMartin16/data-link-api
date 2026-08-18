"""
Mide tiempo y pico de memoria del procesador sin pasar por HTTP ni por MinIO.

    python bench_local.py data_link_6M.csv csv REMOVE_DUPLICATES_BY_EMAIL
    python bench_local.py data_link_6M.csv csv REMOVE_DUPLICATES_BY_FIELD email

Mide el arbol de procesos completo, no solo el padre: con multiprocessing la
memoria de los workers no aparece en el proceso principal, que es justo lo que
Railway si te suma.

Requiere psutil:  pip install psutil
"""

import os
import sys
import threading
import time

try:
    import psutil
except ImportError:
    print("Falta psutil:  pip install psutil")
    sys.exit(1)

from app.enums.preset_operation import PresetOperation
from app.processors.csv_processor import CsvProcessor
from app.processors.json_processor import JsonProcessor

MB = 1024 * 1024


class MemoryWatcher(threading.Thread):
    """Muestrea el RSS del proceso y de todos sus hijos."""

    def __init__(self, interval: float = 0.2):
        super().__init__(daemon=True)
        self.interval = interval
        self.peak = 0
        self.baseline = 0
        self.samples = []
        self._stop = threading.Event()
        self._proc = psutil.Process()

    def _total_rss(self) -> int:
        total = self._proc.memory_info().rss
        for child in self._proc.children(recursive=True):
            try:
                total += child.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return total

    def run(self) -> None:
        self.baseline = self._total_rss()
        self.peak = self.baseline

        while not self._stop.is_set():
            try:
                rss = self._total_rss()
            except psutil.NoSuchProcess:
                break

            self.samples.append(rss)
            self.peak = max(self.peak, rss)
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()
        self.join(timeout=2)


def main() -> None:
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    path = sys.argv[1]
    fmt = sys.argv[2].lower()
    preset_name = sys.argv[3]
    field = sys.argv[4] if len(sys.argv) > 4 else None

    if not os.path.exists(path):
        print(f"No existe: {path}")
        sys.exit(1)

    size_mb = os.path.getsize(path) / MB
    preset = PresetOperation[preset_name]
    processor_class = CsvProcessor if fmt == "csv" else JsonProcessor
    processor = processor_class(preset, filter_field=field)

    print(f"\nArchivo:   {path}  ({size_mb:.2f} MB)")
    print(f"Preset:    {preset_name}" + (f"  campo={field}" if field else ""))
    print(f"Workers:   DL_WORKERS={os.getenv('DL_WORKERS', '(sin fijar)')}")
    print(f"CHUNK:     {processor_class.CHUNK_SIZE:,} filas")
    print("\nProcesando...\n")

    watcher = MemoryWatcher()
    watcher.start()
    time.sleep(0.5)  # deja que tome la linea base

    started = time.perf_counter()
    result = processor.process(path)
    elapsed = time.perf_counter() - started

    watcher.stop()

    out_mb = result.size_bytes / MB
    kept = result.total_records - result.duplicates_removed - result.records_filtered
    reduction = 0.0
    if result.total_records:
        reduction = (
            (result.duplicates_removed + result.records_filtered)
            * 100.0
            / result.total_records
        )

    print("--- resultado ---")
    print(f"  Registros:        {result.total_records:,}")
    print(f"  Duplicados:       {result.duplicates_removed:,}")
    print(f"  Filtrados:        {result.records_filtered:,}")
    print(f"  Conservados:      {kept:,}")
    print(f"  Reduccion:        {reduction:.2f}%")
    print(f"  Salida:           {out_mb:.2f} MB")

    print("\n--- rendimiento ---")
    print(f"  Tiempo:           {elapsed:.2f} s")
    print(f"  Ritmo:            {result.total_records / elapsed:,.0f} registros/s")

    print("\n--- memoria (arbol completo) ---")
    print(f"  Linea base:       {watcher.baseline / MB:.1f} MB")
    print(f"  Pico:             {watcher.peak / MB:.1f} MB")
    print(f"  Delta:            {(watcher.peak - watcher.baseline) / MB:.1f} MB")
    print(f"  Delta / archivo:  {(watcher.peak - watcher.baseline) / MB / size_mb:.2f}x")

    print(
        "\n  Si 'Delta / archivo' baja al crecer el archivo, la memoria dejo de\n"
        "  escalar con el tamano. Si se mantiene o sube, algo sigue reteniendo\n"
        "  el dataset completo.\n"
    )

    result.cleanup()


if __name__ == "__main__":
    main()
