from enum import StrEnum


class DivideEntradaDivideOptionType0(StrEnum):
    EQUALAREA = "EqualArea"
    EQUALWIDTH = "EqualWidth"
    PROPORTIONALAREA = "ProportionalArea"

    def __str__(self) -> str:
        return str(self.value)
