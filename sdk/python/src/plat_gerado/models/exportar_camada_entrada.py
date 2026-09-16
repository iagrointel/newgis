from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.exportar_camada_entrada_campos_type_0_item import ExportarCamadaEntradaCamposType0Item


T = TypeVar("T", bound="ExportarCamadaEntrada")


@_attrs_define
class ExportarCamadaEntrada:
    """
    Attributes:
        formato (str):
        crs_srid (int | None | Unset):
        campos (list[ExportarCamadaEntradaCamposType0Item] | None | Unset):
    """

    formato: str
    crs_srid: int | None | Unset = UNSET
    campos: list[ExportarCamadaEntradaCamposType0Item] | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        formato = self.formato

        crs_srid: int | None | Unset
        if isinstance(self.crs_srid, Unset):
            crs_srid = UNSET
        else:
            crs_srid = self.crs_srid

        campos: list[dict[str, Any]] | None | Unset
        if isinstance(self.campos, Unset):
            campos = UNSET
        elif isinstance(self.campos, list):
            campos = []
            for campos_type_0_item_data in self.campos:
                campos_type_0_item = campos_type_0_item_data.to_dict()
                campos.append(campos_type_0_item)

        else:
            campos = self.campos

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "formato": formato,
            }
        )
        if crs_srid is not UNSET:
            field_dict["crs_srid"] = crs_srid
        if campos is not UNSET:
            field_dict["campos"] = campos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.exportar_camada_entrada_campos_type_0_item import (
            ExportarCamadaEntradaCamposType0Item,  # noqa: PLC0415
        )

        d = dict(src_dict)
        formato = d.pop("formato")

        def _parse_crs_srid(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        crs_srid = _parse_crs_srid(d.pop("crs_srid", UNSET))

        def _parse_campos(data: object) -> list[ExportarCamadaEntradaCamposType0Item] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                campos_type_0 = []
                _campos_type_0 = data
                for campos_type_0_item_data in _campos_type_0:
                    campos_type_0_item = ExportarCamadaEntradaCamposType0Item.from_dict(campos_type_0_item_data)

                    campos_type_0.append(campos_type_0_item)

                return campos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ExportarCamadaEntradaCamposType0Item] | None | Unset, data)

        campos = _parse_campos(d.pop("campos", UNSET))

        exportar_camada_entrada = cls(
            formato=formato,
            crs_srid=crs_srid,
            campos=campos,
        )

        return exportar_camada_entrada
