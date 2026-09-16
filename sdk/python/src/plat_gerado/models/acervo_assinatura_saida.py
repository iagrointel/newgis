from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AcervoAssinaturaSaida")


@_attrs_define
class AcervoAssinaturaSaida:
    """Resposta do POST de assinatura: o que ficou gravado (quem/quando vivem em plat.acervo_assinatura;
    `assinado_em` volta aqui para a tela mostrar sem nova consulta).

        Attributes:
            camada (str):
            assinada (bool):
            licenca_tipo (None | str | Unset):
            licenca_sha256 (None | str | Unset):
            assinado_em (None | str | Unset):
    """

    camada: str
    assinada: bool
    licenca_tipo: None | str | Unset = UNSET
    licenca_sha256: None | str | Unset = UNSET
    assinado_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        camada = self.camada

        assinada = self.assinada

        licenca_tipo: None | str | Unset
        if isinstance(self.licenca_tipo, Unset):
            licenca_tipo = UNSET
        else:
            licenca_tipo = self.licenca_tipo

        licenca_sha256: None | str | Unset
        if isinstance(self.licenca_sha256, Unset):
            licenca_sha256 = UNSET
        else:
            licenca_sha256 = self.licenca_sha256

        assinado_em: None | str | Unset
        if isinstance(self.assinado_em, Unset):
            assinado_em = UNSET
        else:
            assinado_em = self.assinado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "camada": camada,
                "assinada": assinada,
            }
        )
        if licenca_tipo is not UNSET:
            field_dict["licenca_tipo"] = licenca_tipo
        if licenca_sha256 is not UNSET:
            field_dict["licenca_sha256"] = licenca_sha256
        if assinado_em is not UNSET:
            field_dict["assinado_em"] = assinado_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        camada = d.pop("camada")

        assinada = d.pop("assinada")

        def _parse_licenca_tipo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        licenca_tipo = _parse_licenca_tipo(d.pop("licenca_tipo", UNSET))

        def _parse_licenca_sha256(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        licenca_sha256 = _parse_licenca_sha256(d.pop("licenca_sha256", UNSET))

        def _parse_assinado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        assinado_em = _parse_assinado_em(d.pop("assinado_em", UNSET))

        acervo_assinatura_saida = cls(
            camada=camada,
            assinada=assinada,
            licenca_tipo=licenca_tipo,
            licenca_sha256=licenca_sha256,
            assinado_em=assinado_em,
        )

        acervo_assinatura_saida.additional_properties = d
        return acervo_assinatura_saida

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
