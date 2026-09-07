from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PedidoGeocodificar")


@_attrs_define
class PedidoGeocodificar:
    """
    Attributes:
        endereco (None | str | Unset): linha única, ex.: 'Rua X, 123, Bairro, Município - UF'
        logradouro (None | str | Unset):
        numero (int | None | Unset):
        bairro (None | str | Unset):
        municipio (None | str | Unset):
        uf (None | str | Unset):
        cep (None | str | Unset):
        max_locations (int | Unset):  Default: 10.
    """

    endereco: None | str | Unset = UNSET
    logradouro: None | str | Unset = UNSET
    numero: int | None | Unset = UNSET
    bairro: None | str | Unset = UNSET
    municipio: None | str | Unset = UNSET
    uf: None | str | Unset = UNSET
    cep: None | str | Unset = UNSET
    max_locations: int | Unset = 10
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        endereco: None | str | Unset
        if isinstance(self.endereco, Unset):
            endereco = UNSET
        else:
            endereco = self.endereco

        logradouro: None | str | Unset
        if isinstance(self.logradouro, Unset):
            logradouro = UNSET
        else:
            logradouro = self.logradouro

        numero: int | None | Unset
        if isinstance(self.numero, Unset):
            numero = UNSET
        else:
            numero = self.numero

        bairro: None | str | Unset
        if isinstance(self.bairro, Unset):
            bairro = UNSET
        else:
            bairro = self.bairro

        municipio: None | str | Unset
        if isinstance(self.municipio, Unset):
            municipio = UNSET
        else:
            municipio = self.municipio

        uf: None | str | Unset
        if isinstance(self.uf, Unset):
            uf = UNSET
        else:
            uf = self.uf

        cep: None | str | Unset
        if isinstance(self.cep, Unset):
            cep = UNSET
        else:
            cep = self.cep

        max_locations = self.max_locations

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if endereco is not UNSET:
            field_dict["endereco"] = endereco
        if logradouro is not UNSET:
            field_dict["logradouro"] = logradouro
        if numero is not UNSET:
            field_dict["numero"] = numero
        if bairro is not UNSET:
            field_dict["bairro"] = bairro
        if municipio is not UNSET:
            field_dict["municipio"] = municipio
        if uf is not UNSET:
            field_dict["uf"] = uf
        if cep is not UNSET:
            field_dict["cep"] = cep
        if max_locations is not UNSET:
            field_dict["max_locations"] = max_locations

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_endereco(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        endereco = _parse_endereco(d.pop("endereco", UNSET))

        def _parse_logradouro(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        logradouro = _parse_logradouro(d.pop("logradouro", UNSET))

        def _parse_numero(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        numero = _parse_numero(d.pop("numero", UNSET))

        def _parse_bairro(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        bairro = _parse_bairro(d.pop("bairro", UNSET))

        def _parse_municipio(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        municipio = _parse_municipio(d.pop("municipio", UNSET))

        def _parse_uf(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        uf = _parse_uf(d.pop("uf", UNSET))

        def _parse_cep(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cep = _parse_cep(d.pop("cep", UNSET))

        max_locations = d.pop("max_locations", UNSET)

        pedido_geocodificar = cls(
            endereco=endereco,
            logradouro=logradouro,
            numero=numero,
            bairro=bairro,
            municipio=municipio,
            uf=uf,
            cep=cep,
            max_locations=max_locations,
        )

        pedido_geocodificar.additional_properties = d
        return pedido_geocodificar

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
