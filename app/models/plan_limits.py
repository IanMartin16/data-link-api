from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.sql import func

from app.database import Base
from app.enums.file_format import FileFormat


class PlanLimits(Base):
    __tablename__ = "plan_limits"

    # Plan identifier
    plan = Column(String(20), primary_key=True)

    # File usage limits
    files_per_month = Column(Integer, nullable=False)   # use -1 only if ever needed later
    max_file_size_mb = Column(Integer, nullable=False)

    # Record limits are per format: JSON weighs ~2.4x more than CSV for the
    # same number of records, so a single limit would either be unreachable
    # for JSON or too generous for CSV.
    max_records_per_file = Column(Integer, nullable=False)   # CSV
    max_records_json = Column(Integer, nullable=False)       # JSON

    # Feature access
    num_presets = Column(Integer, nullable=False)
    custom_filters_allowed = Column(Boolean, nullable=False, default=False)

    # API limits
    api_keys_count = Column(Integer, nullable=False, default=1)
    requests_per_hour = Column(Integer, nullable=False)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<PlanLimits {self.plan}>"

    @property
    def is_unlimited_files(self):
        """Return True when the plan has no monthly file cap."""
        return self.files_per_month == -1

    def max_records_for(self, file_format) -> int:
        """Record cap for the given format."""
        value = getattr(file_format, "value", file_format)

        if str(value).lower() == FileFormat.JSON.value.lower():
            return self.max_records_json

        return self.max_records_per_file

    def can_process_file(
        self,
        file_size_mb: float,
        current_month_files: int,
        record_count: int | None = None,
        file_format=None,
    ) -> tuple[bool, str]:
        """
        Validate whether the current plan can process the file.

        Returns:
            (can_process, error_message)
        """

        if not self.is_unlimited_files and current_month_files >= self.files_per_month:
            return False, f"Monthly file limit reached ({self.files_per_month} files)"

        if file_size_mb > self.max_file_size_mb:
            return False, (
                f"File size exceeds plan limit "
                f"({file_size_mb:.2f}MB > {self.max_file_size_mb}MB)"
            )

        if record_count is not None:
            max_records = self.max_records_for(file_format)

            if record_count > max_records:
                label = str(getattr(file_format, "value", file_format) or "").upper()
                suffix = f" for {label}" if label else ""

                return False, (
                    f"Record count exceeds plan limit{suffix} "
                    f"({record_count} > {max_records})"
                )

        return True, ""


PLAN_LIMITS_SEED = [
    {
        "plan": "FREE",
        "files_per_month": 10,
        "max_file_size_mb": 15,
        "max_records_per_file": 200000,   # CSV
        "max_records_json": 100000,
        "num_presets": 2,
        "custom_filters_allowed": False,
        "api_keys_count": 1,
        "requests_per_hour": 20
    },
    {
        "plan": "STARTER",
        "files_per_month": 100,
        "max_file_size_mb": 150,
        "max_records_per_file": 2000000,  # CSV
        "max_records_json": 1000000,
        "num_presets": 6,
        "custom_filters_allowed": True,
        "api_keys_count": 1,
        "requests_per_hour": 100
    }
]
