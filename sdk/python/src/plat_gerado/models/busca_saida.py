from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.registro_saida import RegistroSaida


T = TypeVar("T", bound="BuscaSaida")


@_attrs_define
class BuscaSaida:
    """
    Attributes:
        url_pedida (str):
        total (int):
        devolvidos (int):
        inicio (int):
        registros (list[RegistroSaida]):
        proximo (int | None | Unset):
    """

    url_pedida: str
    total: int
    devolvidos: int
    inicio: int
    registros: list[RegistroSaida]
    proximo: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        url_pedida = self.url_pedida

        total = self.total

        devolvidos = self.devolvidos

        inicio = self.inicio

        registros = []
        for registros_item_data in self.registros:
            registros_item = registros_item_data.to_dict()
            registros.append(registros_item)

        proximo: int | None | Unset
        if isinstance(self.proximo, Unset):
            proximo = UNSET
        else:
            proximo = self.proximo

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "url_pedida": url_pedida,
                "total": total,
                "devolvidos": devolvidos,
                "inicio": inicio,
                "registros": registros,
            }
        )
        if proximo is not UNSET:
            field_dict["proximo"] = proximo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.registro_saida import RegistroSaida  # noqa: PLC0415

        d = dict(src_dict)
        url_pedida = d.pop("url_pedida")

        total = d.pop("total")

        devolvidos = d.pop("devolvidos")

        inicio = d.pop("inicio")

        registros = []
        _registros = d.pop("registros")
        for registros_item_data in _registros:
            registros_item = RegistroSaida.from_dict(registros_item_data)

            registros.append(registros_item)

        def _parse_proximo(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        proximo = _parse_proximo(d.pop("proximo", UNSET))

        busca_saida = cls(
            url_pedida=url_pedida,
            total=total,
            devolvidos=devolvidos,
            inicio=inicio,
            registros=registros,
            proximo=proximo,
        )

        busca_saida.additional_properties = d
        return busca_saida

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
