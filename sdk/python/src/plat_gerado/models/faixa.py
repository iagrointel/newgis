from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="Faixa")


@_attrs_define
class Faixa:
    """
    Attributes:
        id (str):
        tipo_id (str):
        inicio (int):
        fim (int):
        tamanho (int):
        consumidos (int):
        estado (str):
        criado_em (str):
        liberada_em (None | str):
        usuario_id (int | None | Unset):
        dono (None | str | Unset):
    """

    id: str
    tipo_id: str
    inicio: int
    fim: int
    tamanho: int
    consumidos: int
    estado: str
    criado_em: str
    liberada_em: None | str
    usuario_id: int | None | Unset = UNSET
    dono: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        tipo_id = self.tipo_id

        inicio = self.inicio

        fim = self.fim

        tamanho = self.tamanho

        consumidos = self.consumidos

        estado = self.estado

        criado_em = self.criado_em

        liberada_em: None | str
        liberada_em = self.liberada_em

        usuario_id: int | None | Unset
        if isinstance(self.usuario_id, Unset):
            usuario_id = UNSET
        else:
            usuario_id = self.usuario_id

        dono: None | str | Unset
        if isinstance(self.dono, Unset):
            dono = UNSET
        else:
            dono = self.dono

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "tipo_id": tipo_id,
                "inicio": inicio,
                "fim": fim,
                "tamanho": tamanho,
                "consumidos": consumidos,
                "estado": estado,
                "criado_em": criado_em,
                "liberada_em": liberada_em,
            }
        )
        if usuario_id is not UNSET:
            field_dict["usuario_id"] = usuario_id
        if dono is not UNSET:
            field_dict["dono"] = dono

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        tipo_id = d.pop("tipo_id")

        inicio = d.pop("inicio")

        fim = d.pop("fim")

        tamanho = d.pop("tamanho")

        consumidos = d.pop("consumidos")

        estado = d.pop("estado")

        criado_em = d.pop("criado_em")

        def _parse_liberada_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        liberada_em = _parse_liberada_em(d.pop("liberada_em"))

        def _parse_usuario_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        usuario_id = _parse_usuario_id(d.pop("usuario_id", UNSET))

        def _parse_dono(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dono = _parse_dono(d.pop("dono", UNSET))

        faixa = cls(
            id=id,
            tipo_id=tipo_id,
            inicio=inicio,
            fim=fim,
            tamanho=tamanho,
            consumidos=consumidos,
            estado=estado,
            criado_em=criado_em,
            liberada_em=liberada_em,
            usuario_id=usuario_id,
            dono=dono,
        )

        faixa.additional_properties = d
        return faixa

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
