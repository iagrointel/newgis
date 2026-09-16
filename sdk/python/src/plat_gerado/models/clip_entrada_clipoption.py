from enum import StrEnum


class ClipEntradaClipoption(StrEnum):
    DISCARDAREA = "DiscardArea"
    PRESERVEAREA = "PreserveArea"
    PRESERVEBOTHAREASSPLIT = "PreserveBothAreasSplit"

    def __str__(self) -> str:
        return str(self.value)
