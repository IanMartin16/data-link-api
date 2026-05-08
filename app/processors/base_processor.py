from abc import ABC, abstractmethod
from typing import Dict, Any, List
from app.enums.preset_operation import PresetOperation
from app.enums.filter_operator import FilterOperator


class ProcessingResult:
    def __init__(self, data: bytes, total: int, duplicates: int, filtered: int):
        self.data = data
        self.total_records = total
        self.duplicates_removed = duplicates
        self.records_filtered = filtered


class BaseProcessor(ABC):
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
    def process(self, input_data: bytes) -> ProcessingResult:
        pass

    def required_fields(self) -> List[str]:
        """Campos requeridos por preset a nivel dataset."""
        if self.preset == PresetOperation.REMOVE_DUPLICATES_BY_EMAIL:
            return ["email"]

        elif self.preset == PresetOperation.REMOVE_DUPLICATES_BY_ID:
            return ["id"]

        elif self.preset == PresetOperation.REMOVE_DUPLICATES_BY_EMAIL_AND_PHONE:
            return ["email", "phone"]

        elif self.preset == PresetOperation.FILTER_ACTIVE_ONLY:
            return ["status"]

        elif self.preset == PresetOperation.REMOVE_EMPTY_RECORDS:
            return []

        return []

    def normalize_text(self, value: Any) -> str:
        """Normalización básica de texto."""
        if value is None:
            return ""
        return str(value).strip()

    def normalize_email(self, value: Any) -> str:
        """Normalización específica para email."""
        return self.normalize_text(value).lower()

    def apply_preset(self, record: Dict[str, Any], seen: set) -> bool:
        """
        Aplica el preset.
        Retorna True si el registro pasa.
        Retorna False si debe excluirse.
        """

        if self.preset == PresetOperation.REMOVE_DUPLICATES_BY_EMAIL:
            email = self.normalize_email(record.get("email"))

            # No usar vacíos como clave deduplicable
            if not email:
                return True

            if email in seen:
                return False

            seen.add(email)
            return True

        elif self.preset == PresetOperation.REMOVE_DUPLICATES_BY_ID:
            record_id = self.normalize_text(record.get("id"))

            # No usar vacíos como clave deduplicable
            if not record_id:
                return True

            if record_id in seen:
                return False

            seen.add(record_id)
            return True

        elif self.preset == PresetOperation.REMOVE_DUPLICATES_BY_EMAIL_AND_PHONE:
            email = self.normalize_email(record.get("email"))
            phone = self.normalize_text(record.get("phone"))

            # No usar combinaciones vacías como clave deduplicable
            if not email or not phone:
                return True

            key = f"{email}|{phone}"

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