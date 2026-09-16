from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ExportacaoEntradaIntercambio")


@_attrs_define
class ExportacaoEntradaIntercambio:
    """
    Attributes:
        tipo (str | Unset):  Default: 'camada'.
        item_id (None | str | Unset):
        formato (None | str | Unset):
        srid (int | None | Unset):
        campos (list[str] | None | Unset):
        titulo (None | str | Unset):
    """

    tipo: str | Unset = "camada"
    item_id: None | str | Unset = UNSET
    formato: None | str | Unset = UNSET
    srid: int | None | Unset = UNSET
    campos: list[str] | None | Unset = UNSET
    titulo: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        tipo = self.tipo

        item_id: None | str | Unset
        if isinstance(self.item_id, Unset):
            item_id = UNSET
        else:
            item_id = self.item_id

        formato: None | str | Unset
        if isinstance(self.formato, Unset):
            formato = UNSET
        else:
            formato = self.formato

        srid: int | None | Unset
        if isinstance(self.srid, Unset):
            srid = UNSET
        else:
            srid = self.srid

        campos: list[str] | None | Unset
        if isinstance(self.campos, Unset):
            campos = UNSET
        elif isinstance(self.campos, list):
            campos = self.campos

        else:
            campos = self.campos

        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if tipo is not UNSET:
            field_dict["tipo"] = tipo
        if item_id is not UNSET:
            field_dict["item_id"] = item_id
        if formato is not UNSET:
            field_dict["formato"] = formato
        if srid is not UNSET:
            field_dict["srid"] = srid
        if campos is not UNSET:
            field_dict["campos"] = campos
        if titulo is not UNSET:
            field_dict["titulo"] = titulo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tipo = d.pop("tipo", UNSET)

        def _parse_item_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        item_id = _parse_item_id(d.pop("item_id", UNSET))

        def _parse_formato(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        formato = _parse_formato(d.pop("formato", UNSET))

        def _parse_srid(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        srid = _parse_srid(d.pop("srid", UNSET))

        def _parse_campos(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                campos_type_0 = cast(list[str], data)

                return campos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        campos = _parse_campos(d.pop("campos", UNSET))

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        exportacao_entrada_intercambio = cls(
            tipo=tipo,
            item_id=item_id,
            formato=formato,
            srid=srid,
            campos=campos,
            titulo=titulo,
        )

        return exportacao_entrada_intercambio
