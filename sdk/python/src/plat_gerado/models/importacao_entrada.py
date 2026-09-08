from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="ImportacaoEntrada")


@_attrs_define
class ImportacaoEntrada:
    """
    Attributes:
        arquivo_id (str):
        formato (str):
    """

    arquivo_id: str
    formato: str

    def to_dict(self) -> dict[str, Any]:
        arquivo_id = self.arquivo_id

        formato = self.formato

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "arquivo_id": arquivo_id,
                "formato": formato,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        arquivo_id = d.pop("arquivo_id")

        formato = d.pop("formato")

        importacao_entrada = cls(
            arquivo_id=arquivo_id,
            formato=formato,
        )

        return importacao_entrada
