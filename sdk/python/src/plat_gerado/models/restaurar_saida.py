from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="RestaurarSaida")


@_attrs_define
class RestaurarSaida:
    """
    Attributes:
        sucesso (bool):
        id (str):
        recriada (bool):
        fid (int | None | Unset):
        versao (int | None | Unset):
        avisos (list[str] | Unset):
    """

    sucesso: bool
    id: str
    recriada: bool
    fid: int | None | Unset = UNSET
    versao: int | None | Unset = UNSET
    avisos: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        sucesso = self.sucesso

        id = self.id

        recriada = self.recriada

        fid: int | None | Unset
        if isinstance(self.fid, Unset):
            fid = UNSET
        else:
            fid = self.fid

        versao: int | None | Unset
        if isinstance(self.versao, Unset):
            versao = UNSET
        else:
            versao = self.versao

        avisos: list[str] | Unset = UNSET
        if not isinstance(self.avisos, Unset):
            avisos = self.avisos

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "sucesso": sucesso,
                "id": id,
                "recriada": recriada,
            }
        )
        if fid is not UNSET:
            field_dict["fid"] = fid
        if versao is not UNSET:
            field_dict["versao"] = versao
        if avisos is not UNSET:
            field_dict["avisos"] = avisos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        sucesso = d.pop("sucesso")

        id = d.pop("id")

        recriada = d.pop("recriada")

        def _parse_fid(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        fid = _parse_fid(d.pop("fid", UNSET))

        def _parse_versao(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        versao = _parse_versao(d.pop("versao", UNSET))

        avisos = cast(list[str], d.pop("avisos", UNSET))

        restaurar_saida = cls(
            sucesso=sucesso,
            id=id,
            recriada=recriada,
            fid=fid,
            versao=versao,
            avisos=avisos,
        )

        restaurar_saida.additional_properties = d
        return restaurar_saida

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
