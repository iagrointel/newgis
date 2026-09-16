from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="RedeEntrada")


@_attrs_define
class RedeEntrada:
    """
    Attributes:
        nome (str):
        disciplina (str):
        descricao (None | str | Unset):
        tolerancia_m (float | Unset):  Default: 0.05.
    """

    nome: str
    disciplina: str
    descricao: None | str | Unset = UNSET
    tolerancia_m: float | Unset = 0.05
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        disciplina = self.disciplina

        descricao: None | str | Unset
        if isinstance(self.descricao, Unset):
            descricao = UNSET
        else:
            descricao = self.descricao

        tolerancia_m = self.tolerancia_m

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nome": nome,
                "disciplina": disciplina,
            }
        )
        if descricao is not UNSET:
            field_dict["descricao"] = descricao
        if tolerancia_m is not UNSET:
            field_dict["tolerancia_m"] = tolerancia_m

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        disciplina = d.pop("disciplina")

        def _parse_descricao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        descricao = _parse_descricao(d.pop("descricao", UNSET))

        tolerancia_m = d.pop("tolerancia_m", UNSET)

        rede_entrada = cls(
            nome=nome,
            disciplina=disciplina,
            descricao=descricao,
            tolerancia_m=tolerancia_m,
        )

        rede_entrada.additional_properties = d
        return rede_entrada

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
