from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="RelacaoEntrada")


@_attrs_define
class RelacaoEntrada:
    """
    Attributes:
        destino (str):
        tipo (str):
        posicao (int | None | Unset):
    """

    destino: str
    tipo: str
    posicao: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        destino = self.destino

        tipo = self.tipo

        posicao: int | None | Unset
        if isinstance(self.posicao, Unset):
            posicao = UNSET
        else:
            posicao = self.posicao

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "destino": destino,
                "tipo": tipo,
            }
        )
        if posicao is not UNSET:
            field_dict["posicao"] = posicao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        destino = d.pop("destino")

        tipo = d.pop("tipo")

        def _parse_posicao(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        posicao = _parse_posicao(d.pop("posicao", UNSET))

        relacao_entrada = cls(
            destino=destino,
            tipo=tipo,
            posicao=posicao,
        )

        return relacao_entrada
