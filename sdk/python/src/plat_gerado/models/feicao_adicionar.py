from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.feicao_adicionar_atributos import FeicaoAdicionarAtributos
    from ..models.feicao_adicionar_geometria_type_0 import FeicaoAdicionarGeometriaType0


T = TypeVar("T", bound="FeicaoAdicionar")


@_attrs_define
class FeicaoAdicionar:
    """
    Attributes:
        grupo (str):
        tipo (int):
        geometria (FeicaoAdicionarGeometriaType0 | None | Unset):
        atributos (FeicaoAdicionarAtributos | Unset):
        terminal_inicio (None | str | Unset):
        terminal_fim (None | str | Unset):
    """

    grupo: str
    tipo: int
    geometria: FeicaoAdicionarGeometriaType0 | None | Unset = UNSET
    atributos: FeicaoAdicionarAtributos | Unset = UNSET
    terminal_inicio: None | str | Unset = UNSET
    terminal_fim: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.feicao_adicionar_geometria_type_0 import FeicaoAdicionarGeometriaType0  # noqa: PLC0415

        grupo = self.grupo

        tipo = self.tipo

        geometria: dict[str, Any] | None | Unset
        if isinstance(self.geometria, Unset):
            geometria = UNSET
        elif isinstance(self.geometria, FeicaoAdicionarGeometriaType0):
            geometria = self.geometria.to_dict()
        else:
            geometria = self.geometria

        atributos: dict[str, Any] | Unset = UNSET
        if not isinstance(self.atributos, Unset):
            atributos = self.atributos.to_dict()

        terminal_inicio: None | str | Unset
        if isinstance(self.terminal_inicio, Unset):
            terminal_inicio = UNSET
        else:
            terminal_inicio = self.terminal_inicio

        terminal_fim: None | str | Unset
        if isinstance(self.terminal_fim, Unset):
            terminal_fim = UNSET
        else:
            terminal_fim = self.terminal_fim

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "grupo": grupo,
                "tipo": tipo,
            }
        )
        if geometria is not UNSET:
            field_dict["geometria"] = geometria
        if atributos is not UNSET:
            field_dict["atributos"] = atributos
        if terminal_inicio is not UNSET:
            field_dict["terminal_inicio"] = terminal_inicio
        if terminal_fim is not UNSET:
            field_dict["terminal_fim"] = terminal_fim

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.feicao_adicionar_atributos import FeicaoAdicionarAtributos  # noqa: PLC0415
        from ..models.feicao_adicionar_geometria_type_0 import FeicaoAdicionarGeometriaType0  # noqa: PLC0415

        d = dict(src_dict)
        grupo = d.pop("grupo")

        tipo = d.pop("tipo")

        def _parse_geometria(data: object) -> FeicaoAdicionarGeometriaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                geometria_type_0 = FeicaoAdicionarGeometriaType0.from_dict(data)

                return geometria_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FeicaoAdicionarGeometriaType0 | None | Unset, data)

        geometria = _parse_geometria(d.pop("geometria", UNSET))

        _atributos = d.pop("atributos", UNSET)
        atributos: FeicaoAdicionarAtributos | Unset
        if isinstance(_atributos, Unset):
            atributos = UNSET
        else:
            atributos = FeicaoAdicionarAtributos.from_dict(_atributos)

        def _parse_terminal_inicio(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        terminal_inicio = _parse_terminal_inicio(d.pop("terminal_inicio", UNSET))

        def _parse_terminal_fim(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        terminal_fim = _parse_terminal_fim(d.pop("terminal_fim", UNSET))

        feicao_adicionar = cls(
            grupo=grupo,
            tipo=tipo,
            geometria=geometria,
            atributos=atributos,
            terminal_inicio=terminal_inicio,
            terminal_fim=terminal_fim,
        )

        return feicao_adicionar
