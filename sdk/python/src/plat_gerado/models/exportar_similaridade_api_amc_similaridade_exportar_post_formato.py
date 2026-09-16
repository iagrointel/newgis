from enum import StrEnum


class ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato(StrEnum):
    CSV = "csv"
    GEOJSON = "geojson"

    def __str__(self) -> str:
        return str(self.value)
