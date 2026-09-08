from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AcervoEndpoint")


@_attrs_define
class AcervoEndpoint:
    """
    Attributes:
        url (str):
        vivo (bool):
        origem (None | str | Unset):
        http (None | str | Unset):
        content_type (None | str | Unset):
        bytes_ (int | None | Unset):
        ms (int | None | Unset):
        testado_em (None | str | Unset):
        confirmado (bool | None | Unset):
    """

    url: str
    vivo: bool
    origem: None | str | Unset = UNSET
    http: None | str | Unset = UNSET
    content_type: None | str | Unset = UNSET
    bytes_: int | None | Unset = UNSET
    ms: int | None | Unset = UNSET
    testado_em: None | str | Unset = UNSET
    confirmado: bool | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        url = self.url

        vivo = self.vivo

        origem: None | str | Unset
        if isinstance(self.origem, Unset):
            origem = UNSET
        else:
            origem = self.origem

        http: None | str | Unset
        if isinstance(self.http, Unset):
            http = UNSET
        else:
            http = self.http

        content_type: None | str | Unset
        if isinstance(self.content_type, Unset):
            content_type = UNSET
        else:
            content_type = self.content_type

        bytes_: int | None | Unset
        if isinstance(self.bytes_, Unset):
            bytes_ = UNSET
        else:
            bytes_ = self.bytes_

        ms: int | None | Unset
        if isinstance(self.ms, Unset):
            ms = UNSET
        else:
            ms = self.ms

        testado_em: None | str | Unset
        if isinstance(self.testado_em, Unset):
            testado_em = UNSET
        else:
            testado_em = self.testado_em

        confirmado: bool | None | Unset
        if isinstance(self.confirmado, Unset):
            confirmado = UNSET
        else:
            confirmado = self.confirmado

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "url": url,
                "vivo": vivo,
            }
        )
        if origem is not UNSET:
            field_dict["origem"] = origem
        if http is not UNSET:
            field_dict["http"] = http
        if content_type is not UNSET:
            field_dict["content_type"] = content_type
        if bytes_ is not UNSET:
            field_dict["bytes"] = bytes_
        if ms is not UNSET:
            field_dict["ms"] = ms
        if testado_em is not UNSET:
            field_dict["testado_em"] = testado_em
        if confirmado is not UNSET:
            field_dict["confirmado"] = confirmado

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        url = d.pop("url")

        vivo = d.pop("vivo")

        def _parse_origem(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        origem = _parse_origem(d.pop("origem", UNSET))

        def _parse_http(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        http = _parse_http(d.pop("http", UNSET))

        def _parse_content_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        content_type = _parse_content_type(d.pop("content_type", UNSET))

        def _parse_bytes_(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        bytes_ = _parse_bytes_(d.pop("bytes", UNSET))

        def _parse_ms(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ms = _parse_ms(d.pop("ms", UNSET))

        def _parse_testado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        testado_em = _parse_testado_em(d.pop("testado_em", UNSET))

        def _parse_confirmado(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        confirmado = _parse_confirmado(d.pop("confirmado", UNSET))

        acervo_endpoint = cls(
            url=url,
            vivo=vivo,
            origem=origem,
            http=http,
            content_type=content_type,
            bytes_=bytes_,
            ms=ms,
            testado_em=testado_em,
            confirmado=confirmado,
        )

        acervo_endpoint.additional_properties = d
        return acervo_endpoint

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
