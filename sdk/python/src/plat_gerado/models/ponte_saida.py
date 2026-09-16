from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PonteSaida")


@_attrs_define
class PonteSaida:
    """
    Attributes:
        id (str):
        conexao (str):
        conexao_nome (str):
        formulario (str):
        projeto (int):
        xml_form_id (str):
        versao (None | str | Unset):
        hash_central (None | str | Unset):
        publicado_em (None | str | Unset):
        sincronizado_em (None | str | Unset):
    """

    id: str
    conexao: str
    conexao_nome: str
    formulario: str
    projeto: int
    xml_form_id: str
    versao: None | str | Unset = UNSET
    hash_central: None | str | Unset = UNSET
    publicado_em: None | str | Unset = UNSET
    sincronizado_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        conexao = self.conexao

        conexao_nome = self.conexao_nome

        formulario = self.formulario

        projeto = self.projeto

        xml_form_id = self.xml_form_id

        versao: None | str | Unset
        if isinstance(self.versao, Unset):
            versao = UNSET
        else:
            versao = self.versao

        hash_central: None | str | Unset
        if isinstance(self.hash_central, Unset):
            hash_central = UNSET
        else:
            hash_central = self.hash_central

        publicado_em: None | str | Unset
        if isinstance(self.publicado_em, Unset):
            publicado_em = UNSET
        else:
            publicado_em = self.publicado_em

        sincronizado_em: None | str | Unset
        if isinstance(self.sincronizado_em, Unset):
            sincronizado_em = UNSET
        else:
            sincronizado_em = self.sincronizado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "conexao": conexao,
                "conexao_nome": conexao_nome,
                "formulario": formulario,
                "projeto": projeto,
                "xml_form_id": xml_form_id,
            }
        )
        if versao is not UNSET:
            field_dict["versao"] = versao
        if hash_central is not UNSET:
            field_dict["hash_central"] = hash_central
        if publicado_em is not UNSET:
            field_dict["publicado_em"] = publicado_em
        if sincronizado_em is not UNSET:
            field_dict["sincronizado_em"] = sincronizado_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        conexao = d.pop("conexao")

        conexao_nome = d.pop("conexao_nome")

        formulario = d.pop("formulario")

        projeto = d.pop("projeto")

        xml_form_id = d.pop("xml_form_id")

        def _parse_versao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        versao = _parse_versao(d.pop("versao", UNSET))

        def _parse_hash_central(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        hash_central = _parse_hash_central(d.pop("hash_central", UNSET))

        def _parse_publicado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        publicado_em = _parse_publicado_em(d.pop("publicado_em", UNSET))

        def _parse_sincronizado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sincronizado_em = _parse_sincronizado_em(d.pop("sincronizado_em", UNSET))

        ponte_saida = cls(
            id=id,
            conexao=conexao,
            conexao_nome=conexao_nome,
            formulario=formulario,
            projeto=projeto,
            xml_form_id=xml_form_id,
            versao=versao,
            hash_central=hash_central,
            publicado_em=publicado_em,
            sincronizado_em=sincronizado_em,
        )

        ponte_saida.additional_properties = d
        return ponte_saida

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
