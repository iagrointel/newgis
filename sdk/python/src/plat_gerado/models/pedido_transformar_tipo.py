from enum import StrEnum


class PedidoTransformarTipo(StrEnum):
    BBOX = "bbox"
    PONTO = "ponto"

    def __str__(self) -> str:
        return str(self.value)
