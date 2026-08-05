import json
from io import BytesIO
from multiprocessing import Pool, cpu_count
from typing import Any, Dict, Iterator, List

import ijson

from app.processors.base_processor import BaseProcessor, ProcessingResult


class JsonProcessor(BaseProcessor):

    # Tamaño de chunk para procesamiento paralelo
    CHUNK_SIZE = 50000  # 50K registros por chunk

    # Umbral para cambiar de camino
    LARGE_FILE_MB = 50

    def process(self, input_data: bytes) -> ProcessingResult:
        """
        Procesa JSON. Archivos chicos en una pasada; grandes por streaming
        y en paralelo.
        """
        file_size_mb = len(input_data) / (1024 * 1024)

        if file_size_mb < self.LARGE_FILE_MB:
            return self._process_small(input_data)

        return self._process_large_streaming(input_data)

    # ------------------------------------------------------------------
    # Camino chico
    # ------------------------------------------------------------------
    def _process_small(self, input_data: bytes) -> ProcessingResult:
        """Archivos < LARGE_FILE_MB: todo en memoria."""
        try:
            data = json.loads(input_data.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Invalid JSON file: {str(e)}")

        if not isinstance(data, list):
            raise ValueError("JSON must be an array of objects")

        if not all(isinstance(record, dict) for record in data):
            raise ValueError("All JSON elements must be objects")

        total_records = len(data)

        if data:
            available_fields = set()
            for record in data:
                available_fields.update(record.keys())
            self._validate_fields(available_fields)

        kept_records, duplicates, filtered = self.process_chunk(data)

        output_data = json.dumps(
            kept_records, indent=2, ensure_ascii=False
        ).encode("utf-8")

        return ProcessingResult(
            data=output_data,
            total=total_records,
            duplicates=duplicates,
            filtered=filtered
        )

    # ------------------------------------------------------------------
    # Camino grande
    # ------------------------------------------------------------------
    def _process_large_streaming(self, input_data: bytes) -> ProcessingResult:
        """
        Archivos >= LARGE_FILE_MB: ijson + paralelo.

        Los bloques salen hacia el pool conforme se arman, y la salida se
        escribe registro por registro. Antes se acumulaba el archivo entero
        dos veces: primero en `chunks` y después en `kept_records`.
        """
        validated = []

        def chunk_stream() -> Iterator[List[Dict[str, Any]]]:
            current_chunk: List[Dict[str, Any]] = []

            try:
                parser = ijson.items(BytesIO(input_data), "item")

                for record in parser:
                    if not isinstance(record, dict):
                        raise ValueError("All JSON elements must be objects")

                    current_chunk.append(record)

                    if len(current_chunk) >= self.CHUNK_SIZE:
                        if not validated:
                            self._validate_from_sample(current_chunk)
                            validated.append(True)

                        yield current_chunk
                        current_chunk = []

                if current_chunk:
                    if not validated:
                        self._validate_from_sample(current_chunk)
                        validated.append(True)

                    yield current_chunk
            except ValueError:
                raise
            except Exception as e:
                raise ValueError(f"Invalid JSON file: {str(e)}")

        num_workers = max(1, cpu_count() - 1)

        seen_global = set()
        total_records = 0
        total_duplicates = 0
        total_filtered = 0

        parts: List[str] = []
        written = 0

        def consume(results) -> None:
            nonlocal total_records, total_duplicates, total_filtered, written

            for chunk_kept, chunk_dups, chunk_filt in results:
                total_records += len(chunk_kept) + chunk_dups + chunk_filt
                total_duplicates += chunk_dups
                total_filtered += chunk_filt

                for record in chunk_kept:
                    # Un bloque solo vio sus propios datos: hay que
                    # re-verificar contra el resto del archivo.
                    key = self.dedup_key(record)

                    if key is not None:
                        if key in seen_global:
                            total_duplicates += 1
                            continue
                        seen_global.add(key)

                    parts.append(
                        json.dumps(record, ensure_ascii=False, indent=2)
                    )
                    written += 1

        if num_workers > 1:
            with Pool(processes=num_workers) as pool:
                consume(pool.imap(self.process_chunk, chunk_stream()))
        else:
            consume(self.process_chunk(chunk) for chunk in chunk_stream())

        if not validated:
            raise ValueError("JSON file is empty")

        output_data = ("[\n" + ",\n".join(parts) + "\n]").encode("utf-8")

        return ProcessingResult(
            data=output_data,
            total=total_records,
            duplicates=total_duplicates,
            filtered=total_filtered
        )

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------
    def _validate_from_sample(self, sample: List[Dict[str, Any]]) -> None:
        available_fields = set()
        for record in sample:
            available_fields.update(record.keys())
        self._validate_fields(available_fields)

    def _validate_fields(self, available_fields) -> None:
        """Valida campos requeridos por preset y el campo seleccionado."""
        missing_fields = [
            field for field in self.required_fields()
            if field not in available_fields
        ]

        if missing_fields:
            missing_str = ", ".join(missing_fields)
            raise ValueError(f"Missing required fields for preset: {missing_str}")

        self.validate_selected_field_exists(available_fields)
