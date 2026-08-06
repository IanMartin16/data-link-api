import csv
from multiprocessing import Pool, cpu_count
from typing import Any, Dict, Iterator, List

import pandas as pd

from app.processors.base_processor import (
    BaseProcessor,
    ProcessingResult,
    Source,
    make_temp_file,
)


class CsvProcessor(BaseProcessor):

    # Filas por bloque de lectura
    CHUNK_SIZE = 50000

    # Umbral para cambiar de camino
    LARGE_FILE_MB = 50

    # dtype=str + keep_default_na=False conservan el archivo tal cual: sin esto
    # pandas convierte "007" en 7 y una columna con huecos vuelve enteros en
    # flotantes ("1" -> "1.0").
    READ_OPTIONS = {"dtype": str, "keep_default_na": False}

    def process(self, source: Source) -> ProcessingResult:
        if self.source_size_mb(source) < self.LARGE_FILE_MB:
            return self._process_small(source)
        return self._process_large_chunked(source)

    # ------------------------------------------------------------------
    # Camino chico
    # ------------------------------------------------------------------
    def _process_small(self, source: Source) -> ProcessingResult:
        try:
            df = pd.read_csv(source, **self.READ_OPTIONS)
        except Exception as e:
            raise ValueError(f"Invalid CSV file: {str(e)}")

        columns = df.columns.tolist()
        self._validate_columns(columns)

        total_records = len(df)
        records = df.to_dict("records")
        del df

        kept_records, duplicates, filtered = self.process_chunk(records)

        output_path = make_temp_file(".csv")
        with open(output_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(kept_records)

        return ProcessingResult(
            output_path=output_path,
            total=total_records,
            duplicates=duplicates,
            filtered=filtered,
        )

    # ------------------------------------------------------------------
    # Camino grande
    # ------------------------------------------------------------------
    def _process_large_chunked(self, source: Source) -> ProcessingResult:
        """
        Lectura por bloques desde disco + paralelo + escritura incremental.

        Ni la entrada ni la salida se sostienen completas en memoria: el pico
        depende de CHUNK_SIZE, no del tamano del archivo. Lo unico que crece
        con el dataset es `seen_global`, que es inevitable para deduplicar
        de verdad contra todo el archivo.
        """
        columns_holder: List[List[str]] = []

        def chunk_stream() -> Iterator[List[Dict[str, Any]]]:
            try:
                chunk_iterator = pd.read_csv(
                    source, chunksize=self.CHUNK_SIZE, **self.READ_OPTIONS
                )

                for chunk_df in chunk_iterator:
                    if not columns_holder:
                        columns = chunk_df.columns.tolist()
                        self._validate_columns(columns)
                        columns_holder.append(columns)

                    yield chunk_df.to_dict("records")
            except ValueError:
                raise
            except Exception as e:
                raise ValueError(f"Invalid CSV file: {str(e)}")

        num_workers = self.worker_count()

        seen_global = set()
        total_records = 0
        total_duplicates = 0
        total_filtered = 0

        output_path = make_temp_file(".csv")

        with open(output_path, "w", newline="", encoding="utf-8") as fh:
            writer = None

            def consume(results) -> None:
                nonlocal total_records, total_duplicates, total_filtered, writer

                for chunk_kept, chunk_dups, chunk_filt in results:
                    total_records += len(chunk_kept) + chunk_dups + chunk_filt
                    total_duplicates += chunk_dups
                    total_filtered += chunk_filt

                    if writer is None:
                        columns = columns_holder[0] if columns_holder else []
                        writer = csv.DictWriter(
                            fh, fieldnames=columns, extrasaction="ignore"
                        )
                        writer.writeheader()

                    for record in chunk_kept:
                        # Cada bloque solo vio sus propios datos.
                        key = self.dedup_key(record)

                        if key is not None:
                            if key in seen_global:
                                total_duplicates += 1
                                continue
                            seen_global.add(key)

                        writer.writerow(record)

            if num_workers > 1:
                with Pool(processes=num_workers) as pool:
                    consume(pool.imap(self.process_chunk, chunk_stream()))
            else:
                consume(self.process_chunk(chunk) for chunk in chunk_stream())

            if writer is None:
                raise ValueError("CSV file is empty")

        return ProcessingResult(
            output_path=output_path,
            total=total_records,
            duplicates=total_duplicates,
            filtered=total_filtered,
        )

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------
    def _validate_columns(self, columns) -> None:
        missing_fields = [
            field for field in self.required_fields() if field not in columns
        ]

        if missing_fields:
            missing_str = ", ".join(missing_fields)
            raise ValueError(f"Missing required fields for preset: {missing_str}")

        self.validate_selected_field_exists(columns)
