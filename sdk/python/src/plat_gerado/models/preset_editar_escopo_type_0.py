from enum import StrEnum


class PresetEditarEscopoType0(StrEnum):
    INQUILINO = "inquilino"
    USUARIO = "usuario"

    def __str__(self) -> str:
        return str(self.value)
