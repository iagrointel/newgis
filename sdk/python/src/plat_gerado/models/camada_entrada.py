from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="CamadaEntrada")


@_attrs_define
class CamadaEntrada:
    """
    Attributes:
        camada_id (str):
        nome_gpkg (None | str | Unset):
        filtro (None | str | Unset):
    """

    camada_id: str
    nome_gpkg: None | str | Unset = UNSET
    filtro: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        camada_id = self.camada_id

        nome_gpkg: None | str | Unset
        if isinstance(self.nome_gpkg, Unset):
            nome_gpkg = UNSET
        else:
            nome_gpkg = self.nome_gpkg

        filtro: None | str | Unset
        if isinstance(self.filtro, Unset):
            filtro = UNSET
        else:
            filtro = self.filtro

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "camada_id": camada_id,
            }
        )
        if nome_gpkg is not UNSET:
            field_dict["nome_gpkg"] = nome_gpkg
        if filtro is not UNSET:
            field_dict["filtro"] = filtro

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        camada_id = d.pop("camada_id")

        def _parse_nome_gpkg(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome_gpkg = _parse_nome_gpkg(d.pop("nome_gpkg", UNSET))

        def _parse_filtro(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        filtro = _parse_filtro(d.pop("filtro", UNSET))

        camada_entrada = cls(
            camada_id=camada_id,
            nome_gpkg=nome_gpkg,
            filtro=filtro,
        )

        return camada_entrada
