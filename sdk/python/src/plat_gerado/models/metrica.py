from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="Metrica")


@_attrs_define
class Metrica:
    """
    Attributes:
        recebidos (int | Unset):  Default: 0.
        aceitos (int | Unset):  Default: 0.
        descartados_filtro (int | Unset):  Default: 0.
        descartados_limite (int | Unset):  Default: 0.
        descartados_invalido (int | Unset):  Default: 0.
        atraso_ms_ultimo (int | None | Unset):
        atraso_ms_p50 (int | None | Unset):
        ultimo_evento_em (None | str | Unset):
        atualizado_em (None | str | Unset):
    """

    recebidos: int | Unset = 0
    aceitos: int | Unset = 0
    descartados_filtro: int | Unset = 0
    descartados_limite: int | Unset = 0
    descartados_invalido: int | Unset = 0
    atraso_ms_ultimo: int | None | Unset = UNSET
    atraso_ms_p50: int | None | Unset = UNSET
    ultimo_evento_em: None | str | Unset = UNSET
    atualizado_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        recebidos = self.recebidos

        aceitos = self.aceitos

        descartados_filtro = self.descartados_filtro

        descartados_limite = self.descartados_limite

        descartados_invalido = self.descartados_invalido

        atraso_ms_ultimo: int | None | Unset
        if isinstance(self.atraso_ms_ultimo, Unset):
            atraso_ms_ultimo = UNSET
        else:
            atraso_ms_ultimo = self.atraso_ms_ultimo

        atraso_ms_p50: int | None | Unset
        if isinstance(self.atraso_ms_p50, Unset):
            atraso_ms_p50 = UNSET
        else:
            atraso_ms_p50 = self.atraso_ms_p50

        ultimo_evento_em: None | str | Unset
        if isinstance(self.ultimo_evento_em, Unset):
            ultimo_evento_em = UNSET
        else:
            ultimo_evento_em = self.ultimo_evento_em

        atualizado_em: None | str | Unset
        if isinstance(self.atualizado_em, Unset):
            atualizado_em = UNSET
        else:
            atualizado_em = self.atualizado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if recebidos is not UNSET:
            field_dict["recebidos"] = recebidos
        if aceitos is not UNSET:
            field_dict["aceitos"] = aceitos
        if descartados_filtro is not UNSET:
            field_dict["descartados_filtro"] = descartados_filtro
        if descartados_limite is not UNSET:
            field_dict["descartados_limite"] = descartados_limite
        if descartados_invalido is not UNSET:
            field_dict["descartados_invalido"] = descartados_invalido
        if atraso_ms_ultimo is not UNSET:
            field_dict["atraso_ms_ultimo"] = atraso_ms_ultimo
        if atraso_ms_p50 is not UNSET:
            field_dict["atraso_ms_p50"] = atraso_ms_p50
        if ultimo_evento_em is not UNSET:
            field_dict["ultimo_evento_em"] = ultimo_evento_em
        if atualizado_em is not UNSET:
            field_dict["atualizado_em"] = atualizado_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        recebidos = d.pop("recebidos", UNSET)

        aceitos = d.pop("aceitos", UNSET)

        descartados_filtro = d.pop("descartados_filtro", UNSET)

        descartados_limite = d.pop("descartados_limite", UNSET)

        descartados_invalido = d.pop("descartados_invalido", UNSET)

        def _parse_atraso_ms_ultimo(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        atraso_ms_ultimo = _parse_atraso_ms_ultimo(d.pop("atraso_ms_ultimo", UNSET))

        def _parse_atraso_ms_p50(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        atraso_ms_p50 = _parse_atraso_ms_p50(d.pop("atraso_ms_p50", UNSET))

        def _parse_ultimo_evento_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ultimo_evento_em = _parse_ultimo_evento_em(d.pop("ultimo_evento_em", UNSET))

        def _parse_atualizado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        atualizado_em = _parse_atualizado_em(d.pop("atualizado_em", UNSET))

        metrica = cls(
            recebidos=recebidos,
            aceitos=aceitos,
            descartados_filtro=descartados_filtro,
            descartados_limite=descartados_limite,
            descartados_invalido=descartados_invalido,
            atraso_ms_ultimo=atraso_ms_ultimo,
            atraso_ms_p50=atraso_ms_p50,
            ultimo_evento_em=ultimo_evento_em,
            atualizado_em=atualizado_em,
        )

        metrica.additional_properties = d
        return metrica

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
