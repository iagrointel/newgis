from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.resolver_entrada_atributos_type_0 import ResolverEntradaAtributosType0
    from ..models.resolver_entrada_geometria_type_0 import ResolverEntradaGeometriaType0


T = TypeVar("T", bound="ResolverEntrada")


@_attrs_define
class ResolverEntrada:
    """
    Attributes:
        decisao (str):
        atributos (None | ResolverEntradaAtributosType0 | Unset):
        geometria (None | ResolverEntradaGeometriaType0 | Unset):
    """

    decisao: str
    atributos: None | ResolverEntradaAtributosType0 | Unset = UNSET
    geometria: None | ResolverEntradaGeometriaType0 | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.resolver_entrada_atributos_type_0 import ResolverEntradaAtributosType0  # noqa: PLC0415
        from ..models.resolver_entrada_geometria_type_0 import ResolverEntradaGeometriaType0  # noqa: PLC0415

        decisao = self.decisao

        atributos: dict[str, Any] | None | Unset
        if isinstance(self.atributos, Unset):
            atributos = UNSET
        elif isinstance(self.atributos, ResolverEntradaAtributosType0):
            atributos = self.atributos.to_dict()
        else:
            atributos = self.atributos

        geometria: dict[str, Any] | None | Unset
        if isinstance(self.geometria, Unset):
            geometria = UNSET
        elif isinstance(self.geometria, ResolverEntradaGeometriaType0):
            geometria = self.geometria.to_dict()
        else:
            geometria = self.geometria

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "decisao": decisao,
            }
        )
        if atributos is not UNSET:
            field_dict["atributos"] = atributos
        if geometria is not UNSET:
            field_dict["geometria"] = geometria

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.resolver_entrada_atributos_type_0 import ResolverEntradaAtributosType0  # noqa: PLC0415
        from ..models.resolver_entrada_geometria_type_0 import ResolverEntradaGeometriaType0  # noqa: PLC0415

        d = dict(src_dict)
        decisao = d.pop("decisao")

        def _parse_atributos(data: object) -> None | ResolverEntradaAtributosType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                atributos_type_0 = ResolverEntradaAtributosType0.from_dict(data)

                return atributos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ResolverEntradaAtributosType0 | Unset, data)

        atributos = _parse_atributos(d.pop("atributos", UNSET))

        def _parse_geometria(data: object) -> None | ResolverEntradaGeometriaType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                geometria_type_0 = ResolverEntradaGeometriaType0.from_dict(data)

                return geometria_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ResolverEntradaGeometriaType0 | Unset, data)

        geometria = _parse_geometria(d.pop("geometria", UNSET))

        resolver_entrada = cls(
            decisao=decisao,
            atributos=atributos,
            geometria=geometria,
        )

        return resolver_entrada
