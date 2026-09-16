from enum import StrEnum


class FatorEntradaPapel(StrEnum):
    ATRAI = "atrai"
    CUSTO = "custo"

    def __str__(self) -> str:
        return str(self.value)
