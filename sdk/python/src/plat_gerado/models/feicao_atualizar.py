from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.feicao_atualizar_atributos_type_0 import FeicaoAtualizarAtributosType0
    from ..models.feicao_atualizar_geometria_type_0 import FeicaoAtualizarGeometriaType0


T = TypeVar("T", bound="FeicaoAtualizar")


@_attrs_define
class FeicaoAtualizar:
    """Grupo e tipo NÃO mudam (mudança de classe é apagar + adicionar); só geometria, atributos e os
    terminais declarados nas pontas.

        Attributes:
            id (str):
            geometria (FeicaoAtualizarGeometriaType0 | None | Unset):
            atributos (FeicaoAtualizarAtributosType0 | None | Unset):
            terminal_inicio (None | str | Unset):
            terminal_fim (None | str | Unset):
    """

    id: str
    geometria: FeicaoAtualizarGeometriaType0 | None | Unset = UNSET
    atributos: FeicaoAtualizarAtributosType0 | None | Unset = UNSET
    terminal_inicio: None | str | Unset = UNSET
    terminal_fim: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.feicao_atualizar_atributos_type_0 import FeicaoAtualizarAtributosType0  # noqa: PLC0415
        from ..models.feicao_atualizar_geometria_type_0 import FeicaoAtualizarGeometriaType0  # noqa: PLC0415

        id = self.id

        geometria: dict[str, Any] | None | Unset
        if isinstance(self.geometria, Unset):
            geometria = UNSET
        elif isinstance(self.geometria, FeicaoAtualizarGeometriaType0):
            geometria = self.geometria.to_dict()
        else:
            geometria = self.geometria

        atributos: dict[str, Any] | None | Unset
        if isinstance(self.atributos, Unset):
            atributos = UNSET
        elif isinstance(self.atributos, FeicaoAtualizarAtributosType0):
            atributos = self.atributos.to_dict()
        else:
            atributos = self.atributos

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
                "id": id,
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
        from ..models.feicao_atualizar_atributos_type_0 import FeicaoAtualizarAtributosType0  # noqa: PLC0415
        from ..models.feicao_atualizar_geometria_type_0 import FeicaoAtualizarGeometriaType0  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        def _parse_geometria(data: object) -> FeicaoAtualizarGeometriaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                geometria_type_0 = FeicaoAtualizarGeometriaType0.from_dict(data)

                return geometria_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FeicaoAtualizarGeometriaType0 | None | Unset, data)

        geometria = _parse_geometria(d.pop("geometria", UNSET))

        def _parse_atributos(data: object) -> FeicaoAtualizarAtributosType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                atributos_type_0 = FeicaoAtualizarAtributosType0.from_dict(data)

                return atributos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FeicaoAtualizarAtributosType0 | None | Unset, data)

        atributos = _parse_atributos(d.pop("atributos", UNSET))

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

        feicao_atualizar = cls(
            id=id,
            geometria=geometria,
            atributos=atributos,
            terminal_inicio=terminal_inicio,
            terminal_fim=terminal_fim,
        )

        return feicao_atualizar
