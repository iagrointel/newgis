from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="MetadadoIsoEntrada")


@_attrs_define
class MetadadoIsoEntrada:
    """Corpo de POST /api/itens/{id}/metadado.xml (item L0-09-c): o documento ISO 19139 inteiro num campo de
    texto. O teto aqui é de caracteres; o de bytes, que é o que vale para o analisador, está em
    `limites.METADADO_XML_BYTES_MAX` e é conferido em `metadado.ler_documento`.

        Attributes:
            xml (str):
    """

    xml: str

    def to_dict(self) -> dict[str, Any]:
        xml = self.xml

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "xml": xml,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        xml = d.pop("xml")

        metadado_iso_entrada = cls(
            xml=xml,
        )

        return metadado_iso_entrada
