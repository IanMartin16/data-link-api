import json
from multiprocessing import Pool
from typing import Any, Dict, Iterator, List

import ijson

from app.processors.base_processor import (
    BaseProcessor,
    ProcessingResult,
    Source,
    make_temp_file,
)


class JsonProcessor(BaseProcessor):

    # Registros por bloque
    CHUNK_SIZE = 50000

    # Umbral para cambiar de camino
    LARGE_FILE_MB = 50

    def process(self, source: Source) -> ProcessingResult:
        if self.source_size_mb(source) < self.LARGE_FILE_MB:
            return self._process_small(source)
        return self._process_large_streaming(source)

    # ------------------------------------------------------------------
    # Camino chico
    # ------------------------------------------------------------------
    def _process_small(self, source: Source) -> ProcessingResult:
        try:
            with open(source, "rb") as fh:
                data = json.loads(fh.read().decode("utf-8"))
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

        output_path = make_temp_file(".json")
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(kept_records, fh, indent=2, ensure_ascii=False)

        return ProcessingResult(
            output_path=output_path,
            total=total_records,
            duplicates=duplicates,
            filtered=filtered,
        )

    # ------------------------------------------------------------------
    # Camino grande
    # ------------------------------------------------------------------
    def _process_large_streaming(self, source: Source) -> ProcessingResult:
        """
        ijson lee desde disco y la salida se escribe registro por registro.
        El pico de memoria depende de CHUNK_SIZE, no del tamano del archivo.
        """
        validated: List[bool] = []

        def chunk_stream() -> Iterator[List[Dict[str, Any]]]:
            current_chunk: List[Dict[str, Any]] = []

            try:
                with open(source, "rb") as fh:
                    for record in ijson.items(fh, "item"):
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

        num_workers = self.worker_count()

        seen_global = set()
        total_records = 0
        total_duplicates = 0
        total_filtered = 0

        output_path = make_temp_file(".json")

        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write("[\n")
            written = 0

            def consume(results) -> None:
                nonlocal total_records, total_duplicates, total_filtered, written

                for chunk_kept, chunk_dups, chunk_filt in results:
                    total_records += len(chunk_kept) + chunk_dups + chunk_filt
                    total_duplicates += chunk_dups
                    total_filtered += chunk_filt

                    for record in chunk_kept:
                        key = self.dedup_key(record)

                        if key is not None:
                            if key in seen_global:
                                total_duplicates += 1
                                continue
                            seen_global.add(key)

                        if written:
                            fh.write(",\n")

                        fh.write(json.dumps(record, ensure_ascii=False, indent=2))
                        written += 1

            if num_workers > 1:
                with Pool(processes=num_workers) as pool:
                    consume(pool.imap(self.process_chunk, chunk_stream()))
            else:
                consume(self.process_chunk(chunk) for chunk in chunk_stream())

            fh.write("\n]\n")

        if not validated:
            raise ValueError("JSON file is empty")

        return ProcessingResult(
            output_path=output_path,
            total=total_records,
            duplicates=total_duplicates,
            filtered=total_filtered,
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
        missing_fields = [
            field for field in self.required_fields()
            if field not in available_fields
        ]

        if missing_fields:
            missing_str = ", ".join(missing_fields)
            raise ValueError(f"Missing required fields for preset: {missing_str}")

        self.validate_selected_field_exists(available_fields)
