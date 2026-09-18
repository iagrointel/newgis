from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="WebhookSegredo")


@_attrs_define
class WebhookSegredo:
    """Criar/rotacionar: o campo extra `segredo` viaja UMA vez; quem perder, rotaciona.

    Attributes:
        id (str):
        nome (str):
        url (str):
        eventos (list[str]):
        ativo (bool):
        falhas_consecutivas (int):
        criado_em (str):
        segredo (str):
        desativada_em (None | str | Unset):
        desativada_motivo (None | str | Unset):
        criado_por (None | str | Unset):
        criado_por_login (None | str | Unset):
    """

    id: str
    nome: str
    url: str
    eventos: list[str]
    ativo: bool
    falhas_consecutivas: int
    criado_em: str
    segredo: str
    desativada_em: None | str | Unset = UNSET
    desativada_motivo: None | str | Unset = UNSET
    criado_por: None | str | Unset = UNSET
    criado_por_login: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        nome = self.nome

        url = self.url

        eventos = self.eventos

        ativo = self.ativo

        falhas_consecutivas = self.falhas_consecutivas

        criado_em = self.criado_em

        segredo = self.segredo

        desativada_em: None | str | Unset
        if isinstance(self.desativada_em, Unset):
            desativada_em = UNSET
        else:
            desativada_em = self.desativada_em

        desativada_motivo: None | str | Unset
        if isinstance(self.desativada_motivo, Unset):
            desativada_motivo = UNSET
        else:
            desativada_motivo = self.desativada_motivo

        criado_por: None | str | Unset
        if isinstance(self.criado_por, Unset):
            criado_por = UNSET
        else:
            criado_por = self.criado_por

        criado_por_login: None | str | Unset
        if isinstance(self.criado_por_login, Unset):
            criado_por_login = UNSET
        else:
            criado_por_login = self.criado_por_login

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nome": nome,
                "url": url,
                "eventos": eventos,
                "ativo": ativo,
                "falhas_consecutivas": falhas_consecutivas,
                "criado_em": criado_em,
                "segredo": segredo,
            }
        )
        if desativada_em is not UNSET:
            field_dict["desativada_em"] = desativada_em
        if desativada_motivo is not UNSET:
            field_dict["desativada_motivo"] = desativada_motivo
        if criado_por is not UNSET:
            field_dict["criado_por"] = criado_por
        if criado_por_login is not UNSET:
            field_dict["criado_por_login"] = criado_por_login

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        nome = d.pop("nome")

        url = d.pop("url")

        eventos = cast(list[str], d.pop("eventos"))

        ativo = d.pop("ativo")

        falhas_consecutivas = d.pop("falhas_consecutivas")

        criado_em = d.pop("criado_em")

        segredo = d.pop("segredo")

        def _parse_desativada_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        desativada_em = _parse_desativada_em(d.pop("desativada_em", UNSET))

        def _parse_desativada_motivo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        desativada_motivo = _parse_desativada_motivo(d.pop("desativada_motivo", UNSET))

        def _parse_criado_por(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        criado_por = _parse_criado_por(d.pop("criado_por", UNSET))

        def _parse_criado_por_login(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        criado_por_login = _parse_criado_por_login(d.pop("criado_por_login", UNSET))

        webhook_segredo = cls(
            id=id,
            nome=nome,
            url=url,
            eventos=eventos,
            ativo=ativo,
            falhas_consecutivas=falhas_consecutivas,
            criado_em=criado_em,
            segredo=segredo,
            desativada_em=desativada_em,
            desativada_motivo=desativada_motivo,
            criado_por=criado_por,
            criado_por_login=criado_por_login,
        )

        webhook_segredo.additional_properties = d
        return webhook_segredo

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
