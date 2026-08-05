import csv
from io import BytesIO, StringIO
from multiprocessing import Pool, cpu_count
from typing import Any, Dict, Iterator, List

import pandas as pd

from app.processors.base_processor import BaseProcessor, ProcessingResult


class CsvProcessor(BaseProcessor):

    # Tamaño de chunk para lectura de Pandas
    CHUNK_SIZE = 50000  # 50K filas por chunk

    # Umbral para cambiar de camino
    LARGE_FILE_MB = 50

    # Opciones de lectura compartidas.
    # dtype=str + keep_default_na=False conservan el archivo tal cual: sin esto
    # pandas convierte "007" en 7 y una columna con huecos vuelve enteros en
    # flotantes ("1" -> "1.0"), es decir, la herramienta de limpieza alteraba
    # los datos que debía respetar.
    READ_OPTIONS = {"dtype": str, "keep_default_na": False}

    def process(self, input_data: bytes) -> ProcessingResult:
        """
        Procesa CSV. Archivos chicos en una pasada; grandes por bloques
        en paralelo.
        """
        file_size_mb = len(input_data) / (1024 * 1024)

        if file_size_mb < self.LARGE_FILE_MB:
            return self._process_small(input_data)

        return self._process_large_chunked(input_data)

    # ------------------------------------------------------------------
    # Camino chico
    # ------------------------------------------------------------------
    def _process_small(self, input_data: bytes) -> ProcessingResult:
        """Archivos < LARGE_FILE_MB: todo en memoria."""
        try:
            df = pd.read_csv(BytesIO(input_data), **self.READ_OPTIONS)
        except Exception as e:
            raise ValueError(f"Invalid CSV file: {str(e)}")

        columns = df.columns.tolist()
        self._validate_columns(columns)

        total_records = len(df)
        records = df.to_dict("records")
        del df

        kept_records, duplicates, filtered = self.process_chunk(records)

        output_data = self._write_csv(iter(kept_records), columns)

        return ProcessingResult(
            data=output_data,
            total=total_records,
            duplicates=duplicates,
            filtered=filtered
        )

    # ------------------------------------------------------------------
    # Camino grande
    # ------------------------------------------------------------------
    def _process_large_chunked(self, input_data: bytes) -> ProcessingResult:
        """
        Archivos >= LARGE_FILE_MB: lectura por bloques + paralelo.

        Los bloques se entregan al pool conforme se leen, en vez de
        acumularse todos primero. Antes, el paso de lectura dejaba el
        dataset completo en RAM como diccionarios de Python y recién
        entonces empezaba a trabajar: el camino "de bajo consumo"
        gastaba más memoria que el simple.
        """
        columns_holder: List[List[str]] = []

        def chunk_stream() -> Iterator[List[Dict[str, Any]]]:
            try:
                chunk_iterator = pd.read_csv(
                    BytesIO(input_data),
                    chunksize=self.CHUNK_SIZE,
                    **self.READ_OPTIONS
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

        num_workers = max(1, cpu_count() - 1)

        seen_global = set()
        total_records = 0
        total_duplicates = 0
        total_filtered = 0

        buffer = StringIO()
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
                        buffer, fieldnames=columns, extrasaction="ignore"
                    )
                    writer.writeheader()

                for record in chunk_kept:
                    # Un bloque solo vio sus propios datos: hay que
                    # re-verificar contra el resto del archivo.
                    key = self.dedup_key(record)

                    if key is not None:
                        if key in seen_global:
                            total_duplicates += 1
                            continue
                        seen_global.add(key)

                    writer.writerow(record)

        if num_workers > 1:
            with Pool(processes=num_workers) as pool:
                # imap consume el generador de forma perezosa y devuelve
                # los resultados en orden, así que el archivo se escribe
                # conforme avanza en vez de acumularse entero.
                consume(pool.imap(self.process_chunk, chunk_stream()))
        else:
            consume(self.process_chunk(chunk) for chunk in chunk_stream())

        if writer is None:
            raise ValueError("CSV file is empty")

        return ProcessingResult(
            data=buffer.getvalue().encode("utf-8"),
            total=total_records,
            duplicates=total_duplicates,
            filtered=total_filtered
        )

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------
    def _validate_columns(self, columns) -> None:
        """Valida campos requeridos por preset y el campo seleccionado."""
        missing_fields = [
            field for field in self.required_fields() if field not in columns
        ]

        if missing_fields:
            missing_str = ", ".join(missing_fields)
            raise ValueError(f"Missing required fields for preset: {missing_str}")

        self.validate_selected_field_exists(columns)

    def _write_csv(self, records: Iterator[Dict[str, Any]], columns) -> bytes:
        """Escribe registros a CSV sin construir un DataFrame intermedio."""
        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()

        for record in records:
            writer.writerow(record)

        return buffer.getvalue().encode("utf-8")
