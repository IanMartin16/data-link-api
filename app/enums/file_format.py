from enum import Enum

class FileFormat(str, Enum):
    JSON = "json"
    CSV = "csv"
    
    @property
    def mime_type(self):
        return {
            "json": "application/json",
            "csv": "text/csv"
        }[self.value]
