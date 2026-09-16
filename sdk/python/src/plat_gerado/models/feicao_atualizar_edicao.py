from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.feicao_atualizar_edicao_atributos_type_0 import FeicaoAtualizarEdicaoAtributosType0
    from ..models.feicao_atualizar_edicao_geometria_type_0 import FeicaoAtualizarEdicaoGeometriaType0


T = TypeVar("T", bound="FeicaoAtualizarEdicao")


@_attrs_define
class FeicaoAtualizarEdicao:
    """
    Attributes:
        id (str):
        versao (int):
        atributos (FeicaoAtualizarEdicaoAtributosType0 | None | Unset):
        geometria (FeicaoAtualizarEdicaoGeometriaType0 | None | Unset):
    """

    id: str
    versao: int
    atributos: FeicaoAtualizarEdicaoAtributosType0 | None | Unset = UNSET
    geometria: FeicaoAtualizarEdicaoGeometriaType0 | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.feicao_atualizar_edicao_atributos_type_0 import (
            FeicaoAtualizarEdicaoAtributosType0,  # noqa: PLC0415
        )
        from ..models.feicao_atualizar_edicao_geometria_type_0 import (
            FeicaoAtualizarEdicaoGeometriaType0,  # noqa: PLC0415
        )

        id = self.id

        versao = self.versao

        atributos: dict[str, Any] | None | Unset
        if isinstance(self.atributos, Unset):
            atributos = UNSET
        elif isinstance(self.atributos, FeicaoAtualizarEdicaoAtributosType0):
            atributos = self.atributos.to_dict()
        else:
            atributos = self.atributos

        geometria: dict[str, Any] | None | Unset
        if isinstance(self.geometria, Unset):
            geometria = UNSET
        elif isinstance(self.geometria, FeicaoAtualizarEdicaoGeometriaType0):
            geometria = self.geometria.to_dict()
        else:
            geometria = self.geometria

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "versao": versao,
            }
        )
        if atributos is not UNSET:
            field_dict["atributos"] = atributos
        if geometria is not UNSET:
            field_dict["geometria"] = geometria

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.feicao_atualizar_edicao_atributos_type_0 import (
            FeicaoAtualizarEdicaoAtributosType0,  # noqa: PLC0415
        )
        from ..models.feicao_atualizar_edicao_geometria_type_0 import (
            FeicaoAtualizarEdicaoGeometriaType0,  # noqa: PLC0415
        )

        d = dict(src_dict)
        id = d.pop("id")

        versao = d.pop("versao")

        def _parse_atributos(data: object) -> FeicaoAtualizarEdicaoAtributosType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                atributos_type_0 = FeicaoAtualizarEdicaoAtributosType0.from_dict(data)

                return atributos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FeicaoAtualizarEdicaoAtributosType0 | None | Unset, data)

        atributos = _parse_atributos(d.pop("atributos", UNSET))

        def _parse_geometria(data: object) -> FeicaoAtualizarEdicaoGeometriaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                geometria_type_0 = FeicaoAtualizarEdicaoGeometriaType0.from_dict(data)

                return geometria_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FeicaoAtualizarEdicaoGeometriaType0 | None | Unset, data)

        geometria = _parse_geometria(d.pop("geometria", UNSET))

        feicao_atualizar_edicao = cls(
            id=id,
            versao=versao,
            atributos=atributos,
            geometria=geometria,
        )

        return feicao_atualizar_edicao
