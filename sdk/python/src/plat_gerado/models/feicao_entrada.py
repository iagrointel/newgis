from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.feicao_entrada_atributos import FeicaoEntradaAtributos
    from ..models.feicao_entrada_geometria_type_0 import FeicaoEntradaGeometriaType0


T = TypeVar("T", bound="FeicaoEntrada")


@_attrs_define
class FeicaoEntrada:
    """
    Attributes:
        atributos (FeicaoEntradaAtributos | Unset):
        geometria (FeicaoEntradaGeometriaType0 | None | Unset):
    """

    atributos: FeicaoEntradaAtributos | Unset = UNSET
    geometria: FeicaoEntradaGeometriaType0 | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.feicao_entrada_geometria_type_0 import FeicaoEntradaGeometriaType0  # noqa: PLC0415

        atributos: dict[str, Any] | Unset = UNSET
        if not isinstance(self.atributos, Unset):
            atributos = self.atributos.to_dict()

        geometria: dict[str, Any] | None | Unset
        if isinstance(self.geometria, Unset):
            geometria = UNSET
        elif isinstance(self.geometria, FeicaoEntradaGeometriaType0):
            geometria = self.geometria.to_dict()
        else:
            geometria = self.geometria

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if atributos is not UNSET:
            field_dict["atributos"] = atributos
        if geometria is not UNSET:
            field_dict["geometria"] = geometria

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.feicao_entrada_atributos import FeicaoEntradaAtributos  # noqa: PLC0415
        from ..models.feicao_entrada_geometria_type_0 import FeicaoEntradaGeometriaType0  # noqa: PLC0415

        d = dict(src_dict)
        _atributos = d.pop("atributos", UNSET)
        atributos: FeicaoEntradaAtributos | Unset
        if isinstance(_atributos, Unset):
            atributos = UNSET
        else:
            atributos = FeicaoEntradaAtributos.from_dict(_atributos)

        def _parse_geometria(data: object) -> FeicaoEntradaGeometriaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                geometria_type_0 = FeicaoEntradaGeometriaType0.from_dict(data)

                return geometria_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FeicaoEntradaGeometriaType0 | None | Unset, data)

        geometria = _parse_geometria(d.pop("geometria", UNSET))

        feicao_entrada = cls(
            atributos=atributos,
            geometria=geometria,
        )

        return feicao_entrada
