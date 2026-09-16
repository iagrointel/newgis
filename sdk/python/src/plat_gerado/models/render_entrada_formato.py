from enum import StrEnum


class RenderEntradaFormato(StrEnum):
    PDF = "pdf"
    PNG = "png"

    def __str__(self) -> str:
        return str(self.value)
