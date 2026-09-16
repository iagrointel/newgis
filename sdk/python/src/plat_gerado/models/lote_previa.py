from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="LotePrevia")


@_attrs_define
class LotePrevia:
    """
    Attributes:
        id (str):
        antes (Any | Unset):
        depois (Any | Unset):
        erro (None | str | Unset):
        mensagem (None | str | Unset):
    """

    id: str
    antes: Any | Unset = UNSET
    depois: Any | Unset = UNSET
    erro: None | str | Unset = UNSET
    mensagem: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        antes = self.antes

        depois = self.depois

        erro: None | str | Unset
        if isinstance(self.erro, Unset):
            erro = UNSET
        else:
            erro = self.erro

        mensagem: None | str | Unset
        if isinstance(self.mensagem, Unset):
            mensagem = UNSET
        else:
            mensagem = self.mensagem

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
            }
        )
        if antes is not UNSET:
            field_dict["antes"] = antes
        if depois is not UNSET:
            field_dict["depois"] = depois
        if erro is not UNSET:
            field_dict["erro"] = erro
        if mensagem is not UNSET:
            field_dict["mensagem"] = mensagem

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        antes = d.pop("antes", UNSET)

        depois = d.pop("depois", UNSET)

        def _parse_erro(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        erro = _parse_erro(d.pop("erro", UNSET))

        def _parse_mensagem(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mensagem = _parse_mensagem(d.pop("mensagem", UNSET))

        lote_previa = cls(
            id=id,
            antes=antes,
            depois=depois,
            erro=erro,
            mensagem=mensagem,
        )

        lote_previa.additional_properties = d
        return lote_previa

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
