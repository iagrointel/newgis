from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="IngestaoEntrada")


@_attrs_define
class IngestaoEntrada:
    """
    Attributes:
        arquivo_id (str):
        titulo (None | str | Unset):
        epsg_declarado (int | None | Unset):
    """

    arquivo_id: str
    titulo: None | str | Unset = UNSET
    epsg_declarado: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        arquivo_id = self.arquivo_id

        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        epsg_declarado: int | None | Unset
        if isinstance(self.epsg_declarado, Unset):
            epsg_declarado = UNSET
        else:
            epsg_declarado = self.epsg_declarado

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "arquivo_id": arquivo_id,
            }
        )
        if titulo is not UNSET:
            field_dict["titulo"] = titulo
        if epsg_declarado is not UNSET:
            field_dict["epsg_declarado"] = epsg_declarado

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        arquivo_id = d.pop("arquivo_id")

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        def _parse_epsg_declarado(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        epsg_declarado = _parse_epsg_declarado(d.pop("epsg_declarado", UNSET))

        ingestao_entrada = cls(
            arquivo_id=arquivo_id,
            titulo=titulo,
            epsg_declarado=epsg_declarado,
        )

        return ingestao_entrada
