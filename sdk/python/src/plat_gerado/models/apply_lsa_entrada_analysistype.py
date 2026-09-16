from enum import StrEnum


class ApplyLsaEntradaAnalysistype(StrEnum):
    CONSISTENCY_CHECK = "CONSISTENCY_CHECK"
    WEIGHTED_LEAST_SQUARES = "WEIGHTED_LEAST_SQUARES"

    def __str__(self) -> str:
        return str(self.value)
