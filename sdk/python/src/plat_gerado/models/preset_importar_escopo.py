from enum import StrEnum


class PresetImportarEscopo(StrEnum):
    INQUILINO = "inquilino"
    USUARIO = "usuario"

    def __str__(self) -> str:
        return str(self.value)
