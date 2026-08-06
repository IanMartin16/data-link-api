import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

from app.enums.preset_operation import PresetOperation
from app.enums.filter_operator import FilterOperator


# Lo que los procesadores aceptan como entrada: una ruta en disco.
Source = Union[str, Path]


class ProcessingResult:
    """
    El resultado vive en disco, no en memoria.

    `output_path` es un archivo temporal: el llamador debe subirlo al bucket
    en streaming y despues llamar cleanup(). La propiedad `data` sigue
    existiendo por compatibilidad, pero lee el archivo COMPLETO a RAM —
    usala solo en pruebas o con archivos chicos.
    """

    def __init__(
        self,
        output_path: Source,
        total: int,
        duplicates: int,
        filtered: int,
    ):
        self.output_path = str(output_path)
        self.total_records = total
        self.duplicates_removed = duplicates
        self.records_filtered = filtered

    @property
    def size_bytes(self) -> int:
        return os.path.getsize(self.output_path)

    @property
    def data(self) -> bytes:
        with open(self.output_path, "rb") as fh:
            return fh.read()

    def cleanup(self) -> None:
        """Borra el temporal. Llamar siempre en un finally."""
        try:
            os.unlink(self.output_path)
        except OSError:
            pass


def make_temp_file(suffix: str) -> str:
    """Crea un temporal cerrado y devuelve su ruta."""
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="datalink_")
    os.close(fd)
    return path


class BaseProcessor(ABC):

    # Presets cuyo trabajo es deduplicar. El resto filtra.
    DEDUP_PRESETS = {
        PresetOperation.REMOVE_DUPLICATES_BY_EMAIL,
        PresetOperation.REMOVE_DUPLICATES_BY_ID,
        PresetOperation.REMOVE_DUPLICATES_BY_EMAIL_AND_PHONE,
        PresetOperation.REMOVE_DUPLICATES_BY_FIELD,
    }

    def __init__(
        self,
        preset: PresetOperation,
        filter_field: str = None,
        filter_value: str = None,
        filter_operator: FilterOperator = None
    ):
        self.preset = preset
        self.filter_field = filter_field
        self.filter_value = filter_value
        self.filter_operator = filter_operator

    @abstractmethod
    def process(self, source: Source) -> ProcessingResult:
        """
        Procesa el archivo que vive en `source` (una ruta en disco).

        Antes recibia `bytes`, lo que obligaba a tener el archivo entero en
        RAM antes de empezar: 371 MB de entrada se veian como ~545 MB de
        consumo. Con una ruta, pandas e ijson leen por bloques desde disco
        y el pico deja de depender del tamano del archivo.
        """

    @staticmethod
    def source_size_mb(source: Source) -> float:
        return os.path.getsize(source) / (1024 * 1024)

    @staticmethod
    def worker_count() -> int:
        """
        Procesos para el pool.

        cpu_count() dentro de un contenedor devuelve los cores del HOST, no
        los que el plan asigno. En Railway eso puede significar arrancar 30
        procesos sobre 2 vCPU y perder rendimiento en vez de ganarlo.
        DL_WORKERS manda cuando esta definido.
        """
        configured = os.getenv("DL_WORKERS")
        if configured and configured.isdigit() and int(configured) > 0:
            return int(configured)

        try:
            from multiprocessing import cpu_count
            return max(1, cpu_count() - 1)
        except NotImplementedError:
            return 1

    def required_fields(self) -> List[str]:
        """Campos requeridos por preset a nivel dataset."""
        if self.preset == PresetOperation.REMOVE_DUPLICATES_BY_EMAIL:
            return ["email"]

        elif self.preset == PresetOperation.REMOVE_DUPLICATES_BY_ID:
            return ["id"]

        elif self.preset == PresetOperation.REMOVE_DUPLICATES_BY_EMAIL_AND_PHONE:
            return ["email", "phone"]

        elif self.preset == PresetOperation.REMOVE_DUPLICATES_BY_FIELD:
            return []

        elif self.preset == PresetOperation.FILTER_ACTIVE_ONLY:
            return ["status"]

        elif self.preset == PresetOperation.REMOVE_EMPTY_RECORDS:
            return []

        return []

    def is_dedup_preset(self) -> bool:
        return self.preset in self.DEDUP_PRESETS

    def normalize_text(self, value: Any) -> str:
        """Normalización básica de texto."""
        if value is None:
            return ""
        return str(value).strip()

    def normalize_email(self, value: Any) -> str:
        """Normalización específica para email."""
        return self.normalize_text(value).lower()

    # ------------------------------------------------------------------
    # Llave de deduplicación — FUENTE ÚNICA
    #
    # Antes esta lógica vivía duplicada en apply_preset (aquí) y en
    # _get_dedup_key (en cada procesador). Llegaron a divergir: uno
    # normalizaba el email y el otro no, así que dentro de un chunk
    # "Ana@x.com" y "ana@x.com" se deduplicaban pero entre chunks no.
    # Ahora hay un solo lugar donde se decide qué es la llave.
    # ------------------------------------------------------------------
    def dedup_key(self, record: Dict[str, Any]) -> Optional[str]:
        """
        Llave de deduplicación del registro.

        Devuelve None cuando el registro NO debe deduplicarse: llave vacía,
        combinación incompleta, o preset que no deduplica. Un None siempre
        significa "consérvalo tal cual".
        """
        if self.preset == PresetOperation.REMOVE_DUPLICATES_BY_EMAIL:
            return self.normalize_email(record.get("email")) or None

        elif self.preset == PresetOperation.REMOVE_DUPLICATES_BY_ID:
            return self.normalize_text(record.get("id")) or None

        elif self.preset == PresetOperation.REMOVE_DUPLICATES_BY_EMAIL_AND_PHONE:
            email = self.normalize_email(record.get("email"))
            phone = self.normalize_text(record.get("phone"))

            if not email or not phone:
                return None

            return f"{email}|{phone}"

        elif self.preset == PresetOperation.REMOVE_DUPLICATES_BY_FIELD:
            if not self.filter_field:
                return None

            return self.normalize_text(record.get(self.filter_field)) or None

        return None

    def apply_preset(self, record: Dict[str, Any], seen: set) -> bool:
        """
        Aplica el preset.
        Retorna True si el registro pasa, False si debe excluirse.
        """
        if self.is_dedup_preset():
            key = self.dedup_key(record)

            # Sin llave utilizable no se deduplica: el registro se conserva.
            if key is None:
                return True

            if key in seen:
                return False

            seen.add(key)
            return True

        elif self.preset == PresetOperation.FILTER_ACTIVE_ONLY:
            status = self.normalize_text(record.get("status")).lower()
            return status == "active"

        elif self.preset == PresetOperation.REMOVE_EMPTY_RECORDS:
            # Conserva el registro si al menos un campo tiene contenido real
            return any(
                self.normalize_text(value)
                for value in record.values()
            )

        return True

    def apply_custom_filter(self, record: Dict[str, Any]) -> bool:
        """
        Aplica filtro custom.
        Retorna True si el registro pasa.
        """
        if not self.filter_field or not self.filter_value or not self.filter_operator:
            return True

        field_value = record.get(self.filter_field)
        if field_value is None:
            return False

        return self.filter_operator.evaluate(
            self.normalize_text(field_value),
            self.normalize_text(self.filter_value)
        )

    def validate_selected_field_exists(self, available_fields) -> None:
        """
        Valida que REMOVE_DUPLICATES_BY_FIELD tenga un campo seleccionado
        y que ese campo exista en el dataset.
        """
        if self.preset != PresetOperation.REMOVE_DUPLICATES_BY_FIELD:
            return

        if not self.filter_field:
            raise ValueError(
                "This preset requires a field name. "
                "Please choose the field to deduplicate by."
            )

        available_fields_set = set(str(field) for field in available_fields)

        if self.filter_field not in available_fields_set:
            available = ", ".join(sorted(available_fields_set))
            raise ValueError(
                f'Field "{self.filter_field}" was not found in your file. '
                f"Available fields: {available}"
            )

    # ------------------------------------------------------------------
    # Procesamiento de un bloque — COMPARTIDO
    #
    # Vivía solo en JsonProcessor. CsvProcessor lo llamaba sin tenerlo,
    # y por eso el camino de archivos grandes tronaba con AttributeError.
    # ------------------------------------------------------------------
    def process_chunk(
        self, chunk: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """
        Procesa un bloque de registros de forma aislada.

        Retorna (registros_conservados, duplicados, filtrados).

        NO devuelve el conjunto `seen`: el merge global vuelve a calcular la
        llave con dedup_key(), así que devolverlo obligaba a serializar
        cientos de miles de strings de vuelta al proceso padre para tirarlas.
        """
        seen = set()
        duplicates = 0
        filtered = 0
        kept_records = []

        for record in chunk:
            if not self.apply_preset(record, seen):
                duplicates += 1
                continue

            if not self.apply_custom_filter(record):
                filtered += 1
                continue

            kept_records.append(record)

        return (kept_records, duplicates, filtered)
