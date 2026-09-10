from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.grupo_dono import GrupoDono


T = TypeVar("T", bound="Grupo")


@_attrs_define
class Grupo:
    """
    Attributes:
        id (str):
        nome (str):
        resumo (None | str):
        tags (list[str]):
        visibilidade (str):
        entrada (str):
        contribuicao (str):
        atualizacao_compartilhada (bool):
        administrativo (bool):
        protegido (bool):
        dono (GrupoDono):
        membros (int):
        meu_papel (None | str):
        meu_estado (None | str):
        criado_em (None | str | Unset):
    """

    id: str
    nome: str
    resumo: None | str
    tags: list[str]
    visibilidade: str
    entrada: str
    contribuicao: str
    atualizacao_compartilhada: bool
    administrativo: bool
    protegido: bool
    dono: GrupoDono
    membros: int
    meu_papel: None | str
    meu_estado: None | str
    criado_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        nome = self.nome

        resumo: None | str
        resumo = self.resumo

        tags = self.tags

        visibilidade = self.visibilidade

        entrada = self.entrada

        contribuicao = self.contribuicao

        atualizacao_compartilhada = self.atualizacao_compartilhada

        administrativo = self.administrativo

        protegido = self.protegido

        dono = self.dono.to_dict()

        membros = self.membros

        meu_papel: None | str
        meu_papel = self.meu_papel

        meu_estado: None | str
        meu_estado = self.meu_estado

        criado_em: None | str | Unset
        if isinstance(self.criado_em, Unset):
            criado_em = UNSET
        else:
            criado_em = self.criado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nome": nome,
                "resumo": resumo,
                "tags": tags,
                "visibilidade": visibilidade,
                "entrada": entrada,
                "contribuicao": contribuicao,
                "atualizacao_compartilhada": atualizacao_compartilhada,
                "administrativo": administrativo,
                "protegido": protegido,
                "dono": dono,
                "membros": membros,
                "meu_papel": meu_papel,
                "meu_estado": meu_estado,
            }
        )
        if criado_em is not UNSET:
            field_dict["criado_em"] = criado_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.grupo_dono import GrupoDono  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        nome = d.pop("nome")

        def _parse_resumo(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        resumo = _parse_resumo(d.pop("resumo"))

        tags = cast(list[str], d.pop("tags"))

        visibilidade = d.pop("visibilidade")

        entrada = d.pop("entrada")

        contribuicao = d.pop("contribuicao")

        atualizacao_compartilhada = d.pop("atualizacao_compartilhada")

        administrativo = d.pop("administrativo")

        protegido = d.pop("protegido")

        dono = GrupoDono.from_dict(d.pop("dono"))

        membros = d.pop("membros")

        def _parse_meu_papel(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        meu_papel = _parse_meu_papel(d.pop("meu_papel"))

        def _parse_meu_estado(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        meu_estado = _parse_meu_estado(d.pop("meu_estado"))

        def _parse_criado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        criado_em = _parse_criado_em(d.pop("criado_em", UNSET))

        grupo = cls(
            id=id,
            nome=nome,
            resumo=resumo,
            tags=tags,
            visibilidade=visibilidade,
            entrada=entrada,
            contribuicao=contribuicao,
            atualizacao_compartilhada=atualizacao_compartilhada,
            administrativo=administrativo,
            protegido=protegido,
            dono=dono,
            membros=membros,
            meu_papel=meu_papel,
            meu_estado=meu_estado,
            criado_em=criado_em,
        )

        grupo.additional_properties = d
        return grupo

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
