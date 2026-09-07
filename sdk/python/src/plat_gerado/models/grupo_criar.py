from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="GrupoCriar")


@_attrs_define
class GrupoCriar:
    """
    Attributes:
        nome (str):
        resumo (None | str | Unset):
        tags (list[str] | Unset):
        visibilidade (str | Unset):  Default: 'membros'.
        entrada (str | Unset):  Default: 'convite'.
        contribuicao (str | Unset):  Default: 'todos'.
        atualizacao_compartilhada (bool | Unset):  Default: False.
        administrativo (bool | Unset):  Default: False.
        protegido (bool | Unset):  Default: False.
    """

    nome: str
    resumo: None | str | Unset = UNSET
    tags: list[str] | Unset = UNSET
    visibilidade: str | Unset = "membros"
    entrada: str | Unset = "convite"
    contribuicao: str | Unset = "todos"
    atualizacao_compartilhada: bool | Unset = False
    administrativo: bool | Unset = False
    protegido: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        resumo: None | str | Unset
        if isinstance(self.resumo, Unset):
            resumo = UNSET
        else:
            resumo = self.resumo

        tags: list[str] | Unset = UNSET
        if not isinstance(self.tags, Unset):
            tags = self.tags

        visibilidade = self.visibilidade

        entrada = self.entrada

        contribuicao = self.contribuicao

        atualizacao_compartilhada = self.atualizacao_compartilhada

        administrativo = self.administrativo

        protegido = self.protegido

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
            }
        )
        if resumo is not UNSET:
            field_dict["resumo"] = resumo
        if tags is not UNSET:
            field_dict["tags"] = tags
        if visibilidade is not UNSET:
            field_dict["visibilidade"] = visibilidade
        if entrada is not UNSET:
            field_dict["entrada"] = entrada
        if contribuicao is not UNSET:
            field_dict["contribuicao"] = contribuicao
        if atualizacao_compartilhada is not UNSET:
            field_dict["atualizacao_compartilhada"] = atualizacao_compartilhada
        if administrativo is not UNSET:
            field_dict["administrativo"] = administrativo
        if protegido is not UNSET:
            field_dict["protegido"] = protegido

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        def _parse_resumo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resumo = _parse_resumo(d.pop("resumo", UNSET))

        tags = cast(list[str], d.pop("tags", UNSET))

        visibilidade = d.pop("visibilidade", UNSET)

        entrada = d.pop("entrada", UNSET)

        contribuicao = d.pop("contribuicao", UNSET)

        atualizacao_compartilhada = d.pop("atualizacao_compartilhada", UNSET)

        administrativo = d.pop("administrativo", UNSET)

        protegido = d.pop("protegido", UNSET)

        grupo_criar = cls(
            nome=nome,
            resumo=resumo,
            tags=tags,
            visibilidade=visibilidade,
            entrada=entrada,
            contribuicao=contribuicao,
            atualizacao_compartilhada=atualizacao_compartilhada,
            administrativo=administrativo,
            protegido=protegido,
        )

        return grupo_criar
