from enum import StrEnum


class ExecucaoEntradaAprovacaoTipo(StrEnum):
    LIMIAR = "limiar"
    TOP_PCT = "top_pct"

    def __str__(self) -> str:
        return str(self.value)
