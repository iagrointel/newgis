from enum import StrEnum


class MergeEntradaTargetParcelTypeType0(StrEnum):
    ESTRATO = "estrato"
    GLEBA = "gleba"
    LOTE = "lote"
    QUADRA = "quadra"
    SERVIDAO = "servidao"

    def __str__(self) -> str:
        return str(self.value)
