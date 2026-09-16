from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.renomeacao_renomeado_por import RenomeacaoRenomeadoPor


T = TypeVar("T", bound="Renomeacao")


@_attrs_define
class Renomeacao:
    """
    Attributes:
        codigo_externo_anterior (None | str):
        codigo_externo_novo (str):
        renomeado_por (RenomeacaoRenomeadoPor):
        renomeado_em (str):
    """

    codigo_externo_anterior: None | str
    codigo_externo_novo: str
    renomeado_por: RenomeacaoRenomeadoPor
    renomeado_em: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        codigo_externo_anterior: None | str
        codigo_externo_anterior = self.codigo_externo_anterior

        codigo_externo_novo = self.codigo_externo_novo

        renomeado_por = self.renomeado_por.to_dict()

        renomeado_em = self.renomeado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "codigo_externo_anterior": codigo_externo_anterior,
                "codigo_externo_novo": codigo_externo_novo,
                "renomeado_por": renomeado_por,
                "renomeado_em": renomeado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.renomeacao_renomeado_por import RenomeacaoRenomeadoPor  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_codigo_externo_anterior(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        codigo_externo_anterior = _parse_codigo_externo_anterior(d.pop("codigo_externo_anterior"))

        codigo_externo_novo = d.pop("codigo_externo_novo")

        renomeado_por = RenomeacaoRenomeadoPor.from_dict(d.pop("renomeado_por"))

        renomeado_em = d.pop("renomeado_em")

        renomeacao = cls(
            codigo_externo_anterior=codigo_externo_anterior,
            codigo_externo_novo=codigo_externo_novo,
            renomeado_por=renomeado_por,
            renomeado_em=renomeado_em,
        )

        renomeacao.additional_properties = d
        return renomeacao

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
