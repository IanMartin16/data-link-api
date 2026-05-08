from enum import Enum


class PresetOperation(str, Enum):
    REMOVE_DUPLICATES_BY_EMAIL = "REMOVE_DUPLICATES_BY_EMAIL"
    REMOVE_DUPLICATES_BY_ID = "REMOVE_DUPLICATES_BY_ID"
    REMOVE_DUPLICATES_BY_EMAIL_AND_PHONE = "REMOVE_DUPLICATES_BY_EMAIL_AND_PHONE"
    FILTER_ACTIVE_ONLY = "FILTER_ACTIVE_ONLY"
    REMOVE_EMPTY_RECORDS = "REMOVE_EMPTY_RECORDS"

    @property
    def display_name(self):
        return {
            "REMOVE_DUPLICATES_BY_EMAIL": "Remove duplicates by email",
            "REMOVE_DUPLICATES_BY_ID": "Remove duplicates by ID",
            "REMOVE_DUPLICATES_BY_EMAIL_AND_PHONE": "Remove duplicates by email and phone",
            "FILTER_ACTIVE_ONLY": "Filter active records only",
            "REMOVE_EMPTY_RECORDS": "Remove empty records"
        }[self.value]

    @property
    def description(self):
        return {
            "REMOVE_DUPLICATES_BY_EMAIL": "Removes duplicate records based on the email field",
            "REMOVE_DUPLICATES_BY_ID": "Removes duplicate records based on the id field",
            "REMOVE_DUPLICATES_BY_EMAIL_AND_PHONE": "Removes duplicate records using email and phone as a combined key",
            "FILTER_ACTIVE_ONLY": "Keeps only records where status is active",
            "REMOVE_EMPTY_RECORDS": "Removes records with no meaningful content"
        }[self.value]