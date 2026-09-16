from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.endpoint_publico import EndpointPublico


T = TypeVar("T", bound="EndpointPublicoPagina")


@_attrs_define
class EndpointPublicoPagina:
    """
    Attributes:
        total (int):
        vivos (int):
        fora_do_ar (int):
        nunca_testados (int):
        itens (list[EndpointPublico]):
        testado_em_ultimo (None | str | Unset):
    """

    total: int
    vivos: int
    fora_do_ar: int
    nunca_testados: int
    itens: list[EndpointPublico]
    testado_em_ultimo: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total = self.total

        vivos = self.vivos

        fora_do_ar = self.fora_do_ar

        nunca_testados = self.nunca_testados

        itens = []
        for itens_item_data in self.itens:
            itens_item = itens_item_data.to_dict()
            itens.append(itens_item)

        testado_em_ultimo: None | str | Unset
        if isinstance(self.testado_em_ultimo, Unset):
            testado_em_ultimo = UNSET
        else:
            testado_em_ultimo = self.testado_em_ultimo

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total": total,
                "vivos": vivos,
                "fora_do_ar": fora_do_ar,
                "nunca_testados": nunca_testados,
                "itens": itens,
            }
        )
        if testado_em_ultimo is not UNSET:
            field_dict["testado_em_ultimo"] = testado_em_ultimo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.endpoint_publico import EndpointPublico  # noqa: PLC0415

        d = dict(src_dict)
        total = d.pop("total")

        vivos = d.pop("vivos")

        fora_do_ar = d.pop("fora_do_ar")

        nunca_testados = d.pop("nunca_testados")

        itens = []
        _itens = d.pop("itens")
        for itens_item_data in _itens:
            itens_item = EndpointPublico.from_dict(itens_item_data)

            itens.append(itens_item)

        def _parse_testado_em_ultimo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        testado_em_ultimo = _parse_testado_em_ultimo(d.pop("testado_em_ultimo", UNSET))

        endpoint_publico_pagina = cls(
            total=total,
            vivos=vivos,
            fora_do_ar=fora_do_ar,
            nunca_testados=nunca_testados,
            itens=itens,
            testado_em_ultimo=testado_em_ultimo,
        )

        endpoint_publico_pagina.additional_properties = d
        return endpoint_publico_pagina

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
