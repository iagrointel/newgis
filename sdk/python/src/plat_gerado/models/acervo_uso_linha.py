from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AcervoUsoLinha")


@_attrs_define
class AcervoUsoLinha:
    """Uso de uma camada pelo inquilino no recorte pedido (dia ou mês).

    Attributes:
        acervo_camada_id (str):
        consultas (int):
        feicoes (int):
        view_nome (None | str | Unset):
        dias (int | None | Unset):
    """

    acervo_camada_id: str
    consultas: int
    feicoes: int
    view_nome: None | str | Unset = UNSET
    dias: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        acervo_camada_id = self.acervo_camada_id

        consultas = self.consultas

        feicoes = self.feicoes

        view_nome: None | str | Unset
        if isinstance(self.view_nome, Unset):
            view_nome = UNSET
        else:
            view_nome = self.view_nome

        dias: int | None | Unset
        if isinstance(self.dias, Unset):
            dias = UNSET
        else:
            dias = self.dias

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "acervo_camada_id": acervo_camada_id,
                "consultas": consultas,
                "feicoes": feicoes,
            }
        )
        if view_nome is not UNSET:
            field_dict["view_nome"] = view_nome
        if dias is not UNSET:
            field_dict["dias"] = dias

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        acervo_camada_id = d.pop("acervo_camada_id")

        consultas = d.pop("consultas")

        feicoes = d.pop("feicoes")

        def _parse_view_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        view_nome = _parse_view_nome(d.pop("view_nome", UNSET))

        def _parse_dias(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        dias = _parse_dias(d.pop("dias", UNSET))

        acervo_uso_linha = cls(
            acervo_camada_id=acervo_camada_id,
            consultas=consultas,
            feicoes=feicoes,
            view_nome=view_nome,
            dias=dias,
        )

        acervo_uso_linha.additional_properties = d
        return acervo_uso_linha

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
