from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.roteiro_origem import RoteiroOrigem


T = TypeVar("T", bound="RoteiroCriar")


@_attrs_define
class RoteiroCriar:
    """
    Attributes:
        fila_id (str):
        origem (RoteiroOrigem):
        titulo (None | str | Unset):
        alvo_ids (list[str] | Unset):
        maximo (int | Unset):  Default: 40.
    """

    fila_id: str
    origem: RoteiroOrigem
    titulo: None | str | Unset = UNSET
    alvo_ids: list[str] | Unset = UNSET
    maximo: int | Unset = 40

    def to_dict(self) -> dict[str, Any]:
        fila_id = self.fila_id

        origem = self.origem.to_dict()

        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        alvo_ids: list[str] | Unset = UNSET
        if not isinstance(self.alvo_ids, Unset):
            alvo_ids = self.alvo_ids

        maximo = self.maximo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "fila_id": fila_id,
                "origem": origem,
            }
        )
        if titulo is not UNSET:
            field_dict["titulo"] = titulo
        if alvo_ids is not UNSET:
            field_dict["alvo_ids"] = alvo_ids
        if maximo is not UNSET:
            field_dict["maximo"] = maximo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.roteiro_origem import RoteiroOrigem  # noqa: PLC0415

        d = dict(src_dict)
        fila_id = d.pop("fila_id")

        origem = RoteiroOrigem.from_dict(d.pop("origem"))

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        alvo_ids = cast(list[str], d.pop("alvo_ids", UNSET))

        maximo = d.pop("maximo", UNSET)

        roteiro_criar = cls(
            fila_id=fila_id,
            origem=origem,
            titulo=titulo,
            alvo_ids=alvo_ids,
            maximo=maximo,
        )

        return roteiro_criar
