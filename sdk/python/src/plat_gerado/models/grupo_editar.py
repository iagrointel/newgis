from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="GrupoEditar")


@_attrs_define
class GrupoEditar:
    """
    Attributes:
        nome (None | str | Unset):
        resumo (None | str | Unset):
        tags (list[str] | None | Unset):
        visibilidade (None | str | Unset):
        entrada (None | str | Unset):
        contribuicao (None | str | Unset):
        atualizacao_compartilhada (bool | None | Unset):
        administrativo (bool | None | Unset):
        protegido (bool | None | Unset):
        dono_id (int | None | Unset):
    """

    nome: None | str | Unset = UNSET
    resumo: None | str | Unset = UNSET
    tags: list[str] | None | Unset = UNSET
    visibilidade: None | str | Unset = UNSET
    entrada: None | str | Unset = UNSET
    contribuicao: None | str | Unset = UNSET
    atualizacao_compartilhada: bool | None | Unset = UNSET
    administrativo: bool | None | Unset = UNSET
    protegido: bool | None | Unset = UNSET
    dono_id: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        nome: None | str | Unset
        if isinstance(self.nome, Unset):
            nome = UNSET
        else:
            nome = self.nome

        resumo: None | str | Unset
        if isinstance(self.resumo, Unset):
            resumo = UNSET
        else:
            resumo = self.resumo

        tags: list[str] | None | Unset
        if isinstance(self.tags, Unset):
            tags = UNSET
        elif isinstance(self.tags, list):
            tags = self.tags

        else:
            tags = self.tags

        visibilidade: None | str | Unset
        if isinstance(self.visibilidade, Unset):
            visibilidade = UNSET
        else:
            visibilidade = self.visibilidade

        entrada: None | str | Unset
        if isinstance(self.entrada, Unset):
            entrada = UNSET
        else:
            entrada = self.entrada

        contribuicao: None | str | Unset
        if isinstance(self.contribuicao, Unset):
            contribuicao = UNSET
        else:
            contribuicao = self.contribuicao

        atualizacao_compartilhada: bool | None | Unset
        if isinstance(self.atualizacao_compartilhada, Unset):
            atualizacao_compartilhada = UNSET
        else:
            atualizacao_compartilhada = self.atualizacao_compartilhada

        administrativo: bool | None | Unset
        if isinstance(self.administrativo, Unset):
            administrativo = UNSET
        else:
            administrativo = self.administrativo

        protegido: bool | None | Unset
        if isinstance(self.protegido, Unset):
            protegido = UNSET
        else:
            protegido = self.protegido

        dono_id: int | None | Unset
        if isinstance(self.dono_id, Unset):
            dono_id = UNSET
        else:
            dono_id = self.dono_id

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if nome is not UNSET:
            field_dict["nome"] = nome
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
        if dono_id is not UNSET:
            field_dict["dono_id"] = dono_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome = _parse_nome(d.pop("nome", UNSET))

        def _parse_resumo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resumo = _parse_resumo(d.pop("resumo", UNSET))

        def _parse_tags(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                tags_type_0 = cast(list[str], data)

                return tags_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        tags = _parse_tags(d.pop("tags", UNSET))

        def _parse_visibilidade(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        visibilidade = _parse_visibilidade(d.pop("visibilidade", UNSET))

        def _parse_entrada(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        entrada = _parse_entrada(d.pop("entrada", UNSET))

        def _parse_contribuicao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        contribuicao = _parse_contribuicao(d.pop("contribuicao", UNSET))

        def _parse_atualizacao_compartilhada(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        atualizacao_compartilhada = _parse_atualizacao_compartilhada(d.pop("atualizacao_compartilhada", UNSET))

        def _parse_administrativo(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        administrativo = _parse_administrativo(d.pop("administrativo", UNSET))

        def _parse_protegido(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        protegido = _parse_protegido(d.pop("protegido", UNSET))

        def _parse_dono_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        dono_id = _parse_dono_id(d.pop("dono_id", UNSET))

        grupo_editar = cls(
            nome=nome,
            resumo=resumo,
            tags=tags,
            visibilidade=visibilidade,
            entrada=entrada,
            contribuicao=contribuicao,
            atualizacao_compartilhada=atualizacao_compartilhada,
            administrativo=administrativo,
            protegido=protegido,
            dono_id=dono_id,
        )

        return grupo_editar
