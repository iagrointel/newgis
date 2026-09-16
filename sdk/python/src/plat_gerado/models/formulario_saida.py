from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.formulario_saida_documento import FormularioSaidaDocumento


T = TypeVar("T", bound="FormularioSaida")


@_attrs_define
class FormularioSaida:
    """
    Attributes:
        id (str):
        titulo (str):
        documento (FormularioSaidaDocumento):
    """

    id: str
    titulo: str
    documento: FormularioSaidaDocumento
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        titulo = self.titulo

        documento = self.documento.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "titulo": titulo,
                "documento": documento,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.formulario_saida_documento import FormularioSaidaDocumento  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        titulo = d.pop("titulo")

        documento = FormularioSaidaDocumento.from_dict(d.pop("documento"))

        formulario_saida = cls(
            id=id,
            titulo=titulo,
            documento=documento,
        )

        formulario_saida.additional_properties = d
        return formulario_saida

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
