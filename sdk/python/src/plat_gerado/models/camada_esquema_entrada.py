from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.campo_entrada import CampoEntrada


T = TypeVar("T", bound="CamadaEsquemaEntrada")


@_attrs_define
class CamadaEsquemaEntrada:
    """
    Attributes:
        titulo (str):
        geometria (str):
        srid (int):
        campos (list[CampoEntrada] | Unset):
    """

    titulo: str
    geometria: str
    srid: int
    campos: list[CampoEntrada] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        titulo = self.titulo

        geometria = self.geometria

        srid = self.srid

        campos: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.campos, Unset):
            campos = []
            for campos_item_data in self.campos:
                campos_item = campos_item_data.to_dict()
                campos.append(campos_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "titulo": titulo,
                "geometria": geometria,
                "srid": srid,
            }
        )
        if campos is not UNSET:
            field_dict["campos"] = campos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.campo_entrada import CampoEntrada  # noqa: PLC0415

        d = dict(src_dict)
        titulo = d.pop("titulo")

        geometria = d.pop("geometria")

        srid = d.pop("srid")

        _campos = d.pop("campos", UNSET)
        campos: list[CampoEntrada] | Unset = UNSET
        if _campos is not UNSET:
            campos = []
            for campos_item_data in _campos:
                campos_item = CampoEntrada.from_dict(campos_item_data)

                campos.append(campos_item)

        camada_esquema_entrada = cls(
            titulo=titulo,
            geometria=geometria,
            srid=srid,
            campos=campos,
        )

        return camada_esquema_entrada
