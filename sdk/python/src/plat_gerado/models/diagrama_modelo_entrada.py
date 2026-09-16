from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.diagrama_modelo_entrada_regras_item import DiagramaModeloEntradaRegrasItem


T = TypeVar("T", bound="DiagramaModeloEntrada")


@_attrs_define
class DiagramaModeloEntrada:
    """Modelo (template) de diagrama do inquilino: as regras de construção e o layout padrão. As regras são
    validadas em `diagrama._validar_regras` contra o vocabulário fechado do módulo.

        Attributes:
            nome (str):
            layout (str):
            regras (list[DiagramaModeloEntradaRegrasItem] | Unset):
    """

    nome: str
    layout: str
    regras: list[DiagramaModeloEntradaRegrasItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        layout = self.layout

        regras: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.regras, Unset):
            regras = []
            for regras_item_data in self.regras:
                regras_item = regras_item_data.to_dict()
                regras.append(regras_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nome": nome,
                "layout": layout,
            }
        )
        if regras is not UNSET:
            field_dict["regras"] = regras

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.diagrama_modelo_entrada_regras_item import DiagramaModeloEntradaRegrasItem  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        layout = d.pop("layout")

        _regras = d.pop("regras", UNSET)
        regras: list[DiagramaModeloEntradaRegrasItem] | Unset = UNSET
        if _regras is not UNSET:
            regras = []
            for regras_item_data in _regras:
                regras_item = DiagramaModeloEntradaRegrasItem.from_dict(regras_item_data)

                regras.append(regras_item)

        diagrama_modelo_entrada = cls(
            nome=nome,
            layout=layout,
            regras=regras,
        )

        diagrama_modelo_entrada.additional_properties = d
        return diagrama_modelo_entrada

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
