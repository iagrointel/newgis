from enum import StrEnum


class PedidoSimilaridadeMetrica(StrEnum):
    COSSENO = "cosseno"
    EUCLIDIANA = "euclidiana"

    def __str__(self) -> str:
        return str(self.value)
