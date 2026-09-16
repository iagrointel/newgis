from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.particionar_por import ParticionarPor


T = TypeVar("T", bound="GeoparquetEntrada")


@_attrs_define
class GeoparquetEntrada:
    """
    Attributes:
        item_id (str):
        modo (str | Unset):  Default: 'exportar'.
        where (None | str | Unset):
        particionar_por (None | ParticionarPor | Unset):
        grupo_linhas (int | None | Unset):
    """

    item_id: str
    modo: str | Unset = "exportar"
    where: None | str | Unset = UNSET
    particionar_por: None | ParticionarPor | Unset = UNSET
    grupo_linhas: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.particionar_por import ParticionarPor  # noqa: PLC0415

        item_id = self.item_id

        modo = self.modo

        where: None | str | Unset
        if isinstance(self.where, Unset):
            where = UNSET
        else:
            where = self.where

        particionar_por: dict[str, Any] | None | Unset
        if isinstance(self.particionar_por, Unset):
            particionar_por = UNSET
        elif isinstance(self.particionar_por, ParticionarPor):
            particionar_por = self.particionar_por.to_dict()
        else:
            particionar_por = self.particionar_por

        grupo_linhas: int | None | Unset
        if isinstance(self.grupo_linhas, Unset):
            grupo_linhas = UNSET
        else:
            grupo_linhas = self.grupo_linhas

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "item_id": item_id,
            }
        )
        if modo is not UNSET:
            field_dict["modo"] = modo
        if where is not UNSET:
            field_dict["where"] = where
        if particionar_por is not UNSET:
            field_dict["particionar_por"] = particionar_por
        if grupo_linhas is not UNSET:
            field_dict["grupo_linhas"] = grupo_linhas

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.particionar_por import ParticionarPor  # noqa: PLC0415

        d = dict(src_dict)
        item_id = d.pop("item_id")

        modo = d.pop("modo", UNSET)

        def _parse_where(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        where = _parse_where(d.pop("where", UNSET))

        def _parse_particionar_por(data: object) -> None | ParticionarPor | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                particionar_por_type_0 = ParticionarPor.from_dict(data)

                return particionar_por_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ParticionarPor | Unset, data)

        particionar_por = _parse_particionar_por(d.pop("particionar_por", UNSET))

        def _parse_grupo_linhas(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        grupo_linhas = _parse_grupo_linhas(d.pop("grupo_linhas", UNSET))

        geoparquet_entrada = cls(
            item_id=item_id,
            modo=modo,
            where=where,
            particionar_por=particionar_por,
            grupo_linhas=grupo_linhas,
        )

        return geoparquet_entrada
