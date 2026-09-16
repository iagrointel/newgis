from enum import StrEnum


class ViewshedEntradaModo(StrEnum):
    DEM = "dem"
    GROUND = "ground"
    NORMAL = "normal"

    def __str__(self) -> str:
        return str(self.value)
