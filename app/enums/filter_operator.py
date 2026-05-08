from enum import Enum

class FilterOperator(str, Enum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    CONTAINS = "CONTAINS"
    NOT_CONTAINS = "NOT_CONTAINS"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    
    def evaluate(self, field_value: str, target_value: str) -> bool:
        if not field_value or not target_value:
            return False
        
        field = str(field_value).lower()
        target = str(target_value).lower()
        
        if self == FilterOperator.EQUALS:
            return field == target
        elif self == FilterOperator.NOT_EQUALS:
            return field != target
        elif self == FilterOperator.CONTAINS:
            return target in field
        elif self == FilterOperator.NOT_CONTAINS:
            return target not in field
        elif self == FilterOperator.STARTS_WITH:
            return field.startswith(target)
        elif self == FilterOperator.ENDS_WITH:
            return field.endswith(target)
        
        return False
