from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="CompartilhamentoEntrada")


@_attrs_define
class CompartilhamentoEntrada:
    """
    Attributes:
        acesso (None | str | Unset):
        grupos (list[str] | None | Unset):
        destaques (list[str] | None | Unset):
        aplicar_a_dependencias (list[str] | None | Unset):
    """

    acesso: None | str | Unset = UNSET
    grupos: list[str] | None | Unset = UNSET
    destaques: list[str] | None | Unset = UNSET
    aplicar_a_dependencias: list[str] | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        acesso: None | str | Unset
        if isinstance(self.acesso, Unset):
            acesso = UNSET
        else:
            acesso = self.acesso

        grupos: list[str] | None | Unset
        if isinstance(self.grupos, Unset):
            grupos = UNSET
        elif isinstance(self.grupos, list):
            grupos = self.grupos

        else:
            grupos = self.grupos

        destaques: list[str] | None | Unset
        if isinstance(self.destaques, Unset):
            destaques = UNSET
        elif isinstance(self.destaques, list):
            destaques = self.destaques

        else:
            destaques = self.destaques

        aplicar_a_dependencias: list[str] | None | Unset
        if isinstance(self.aplicar_a_dependencias, Unset):
            aplicar_a_dependencias = UNSET
        elif isinstance(self.aplicar_a_dependencias, list):
            aplicar_a_dependencias = self.aplicar_a_dependencias

        else:
            aplicar_a_dependencias = self.aplicar_a_dependencias

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if acesso is not UNSET:
            field_dict["acesso"] = acesso
        if grupos is not UNSET:
            field_dict["grupos"] = grupos
        if destaques is not UNSET:
            field_dict["destaques"] = destaques
        if aplicar_a_dependencias is not UNSET:
            field_dict["aplicar_a_dependencias"] = aplicar_a_dependencias

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_acesso(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        acesso = _parse_acesso(d.pop("acesso", UNSET))

        def _parse_grupos(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                grupos_type_0 = cast(list[str], data)

                return grupos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        grupos = _parse_grupos(d.pop("grupos", UNSET))

        def _parse_destaques(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                destaques_type_0 = cast(list[str], data)

                return destaques_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        destaques = _parse_destaques(d.pop("destaques", UNSET))

        def _parse_aplicar_a_dependencias(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                aplicar_a_dependencias_type_0 = cast(list[str], data)

                return aplicar_a_dependencias_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        aplicar_a_dependencias = _parse_aplicar_a_dependencias(d.pop("aplicar_a_dependencias", UNSET))

        compartilhamento_entrada = cls(
            acesso=acesso,
            grupos=grupos,
            destaques=destaques,
            aplicar_a_dependencias=aplicar_a_dependencias,
        )

        return compartilhamento_entrada
