from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="TransferenciaEntrada")


@_attrs_define
class TransferenciaEntrada:
    """
    Attributes:
        novo_dono_id (int):
        ids (list[str] | None | Unset):
        usuario_origem_id (int | None | Unset):
        simular (bool | Unset):  Default: True.
        pastas (str | Unset):  Default: 'manter'.
        pasta_unica_nome (None | str | Unset):
        adicionar_aos_grupos (bool | Unset):  Default: False.
        forcar_parcial (bool | Unset):  Default: False.
    """

    novo_dono_id: int
    ids: list[str] | None | Unset = UNSET
    usuario_origem_id: int | None | Unset = UNSET
    simular: bool | Unset = True
    pastas: str | Unset = "manter"
    pasta_unica_nome: None | str | Unset = UNSET
    adicionar_aos_grupos: bool | Unset = False
    forcar_parcial: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        novo_dono_id = self.novo_dono_id

        ids: list[str] | None | Unset
        if isinstance(self.ids, Unset):
            ids = UNSET
        elif isinstance(self.ids, list):
            ids = self.ids

        else:
            ids = self.ids

        usuario_origem_id: int | None | Unset
        if isinstance(self.usuario_origem_id, Unset):
            usuario_origem_id = UNSET
        else:
            usuario_origem_id = self.usuario_origem_id

        simular = self.simular

        pastas = self.pastas

        pasta_unica_nome: None | str | Unset
        if isinstance(self.pasta_unica_nome, Unset):
            pasta_unica_nome = UNSET
        else:
            pasta_unica_nome = self.pasta_unica_nome

        adicionar_aos_grupos = self.adicionar_aos_grupos

        forcar_parcial = self.forcar_parcial

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "novo_dono_id": novo_dono_id,
            }
        )
        if ids is not UNSET:
            field_dict["ids"] = ids
        if usuario_origem_id is not UNSET:
            field_dict["usuario_origem_id"] = usuario_origem_id
        if simular is not UNSET:
            field_dict["simular"] = simular
        if pastas is not UNSET:
            field_dict["pastas"] = pastas
        if pasta_unica_nome is not UNSET:
            field_dict["pasta_unica_nome"] = pasta_unica_nome
        if adicionar_aos_grupos is not UNSET:
            field_dict["adicionar_aos_grupos"] = adicionar_aos_grupos
        if forcar_parcial is not UNSET:
            field_dict["forcar_parcial"] = forcar_parcial

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        novo_dono_id = d.pop("novo_dono_id")

        def _parse_ids(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                ids_type_0 = cast(list[str], data)

                return ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        ids = _parse_ids(d.pop("ids", UNSET))

        def _parse_usuario_origem_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        usuario_origem_id = _parse_usuario_origem_id(d.pop("usuario_origem_id", UNSET))

        simular = d.pop("simular", UNSET)

        pastas = d.pop("pastas", UNSET)

        def _parse_pasta_unica_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pasta_unica_nome = _parse_pasta_unica_nome(d.pop("pasta_unica_nome", UNSET))

        adicionar_aos_grupos = d.pop("adicionar_aos_grupos", UNSET)

        forcar_parcial = d.pop("forcar_parcial", UNSET)

        transferencia_entrada = cls(
            novo_dono_id=novo_dono_id,
            ids=ids,
            usuario_origem_id=usuario_origem_id,
            simular=simular,
            pastas=pastas,
            pasta_unica_nome=pasta_unica_nome,
            adicionar_aos_grupos=adicionar_aos_grupos,
            forcar_parcial=forcar_parcial,
        )

        return transferencia_entrada
