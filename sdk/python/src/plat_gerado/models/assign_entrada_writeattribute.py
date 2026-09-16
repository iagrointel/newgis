from enum import StrEnum


class AssignEntradaWriteattribute(StrEnum):
    CREATEDBYRECORD = "CreatedByRecord"
    RETIREDBYRECORD = "RetiredByRecord"

    def __str__(self) -> str:
        return str(self.value)
