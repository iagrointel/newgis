from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.feicao_adicionar_edicao_atributos import FeicaoAdicionarEdicaoAtributos
    from ..models.feicao_adicionar_edicao_geometria_type_0 import FeicaoAdicionarEdicaoGeometriaType0


T = TypeVar("T", bound="FeicaoAdicionarEdicao")


@_attrs_define
class FeicaoAdicionarEdicao:
    """
    Attributes:
        atributos (FeicaoAdicionarEdicaoAtributos | Unset):
        geometria (FeicaoAdicionarEdicaoGeometriaType0 | None | Unset):
    """

    atributos: FeicaoAdicionarEdicaoAtributos | Unset = UNSET
    geometria: FeicaoAdicionarEdicaoGeometriaType0 | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.feicao_adicionar_edicao_geometria_type_0 import (
            FeicaoAdicionarEdicaoGeometriaType0,  # noqa: PLC0415
        )

        atributos: dict[str, Any] | Unset = UNSET
        if not isinstance(self.atributos, Unset):
            atributos = self.atributos.to_dict()

        geometria: dict[str, Any] | None | Unset
        if isinstance(self.geometria, Unset):
            geometria = UNSET
        elif isinstance(self.geometria, FeicaoAdicionarEdicaoGeometriaType0):
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
        from ..models.feicao_adicionar_edicao_atributos import FeicaoAdicionarEdicaoAtributos  # noqa: PLC0415
        from ..models.feicao_adicionar_edicao_geometria_type_0 import (
            FeicaoAdicionarEdicaoGeometriaType0,  # noqa: PLC0415
        )

        d = dict(src_dict)
        _atributos = d.pop("atributos", UNSET)
        atributos: FeicaoAdicionarEdicaoAtributos | Unset
        if isinstance(_atributos, Unset):
            atributos = UNSET
        else:
            atributos = FeicaoAdicionarEdicaoAtributos.from_dict(_atributos)

        def _parse_geometria(data: object) -> FeicaoAdicionarEdicaoGeometriaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                geometria_type_0 = FeicaoAdicionarEdicaoGeometriaType0.from_dict(data)

                return geometria_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FeicaoAdicionarEdicaoGeometriaType0 | None | Unset, data)

        geometria = _parse_geometria(d.pop("geometria", UNSET))

        feicao_adicionar_edicao = cls(
            atributos=atributos,
            geometria=geometria,
        )

        return feicao_adicionar_edicao
