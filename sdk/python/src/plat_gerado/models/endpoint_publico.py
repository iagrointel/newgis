from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="EndpointPublico")


@_attrs_define
class EndpointPublico:
    """
    Attributes:
        id (int):
        slug (str):
        orgao (str):
        nome (str):
        tipo (str):
        url (str):
        licenca (str):
        origem (str):
        fonte_id (None | str | Unset):
        vivo (bool | None | Unset):
        http (int | None | Unset):
        ms (int | None | Unset):
        motivo (None | str | Unset):
        testado_em (None | str | Unset):
        primeiro_ok_em (None | str | Unset):
        falhas_seguidas (int | Unset):  Default: 0.
    """

    id: int
    slug: str
    orgao: str
    nome: str
    tipo: str
    url: str
    licenca: str
    origem: str
    fonte_id: None | str | Unset = UNSET
    vivo: bool | None | Unset = UNSET
    http: int | None | Unset = UNSET
    ms: int | None | Unset = UNSET
    motivo: None | str | Unset = UNSET
    testado_em: None | str | Unset = UNSET
    primeiro_ok_em: None | str | Unset = UNSET
    falhas_seguidas: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        slug = self.slug

        orgao = self.orgao

        nome = self.nome

        tipo = self.tipo

        url = self.url

        licenca = self.licenca

        origem = self.origem

        fonte_id: None | str | Unset
        if isinstance(self.fonte_id, Unset):
            fonte_id = UNSET
        else:
            fonte_id = self.fonte_id

        vivo: bool | None | Unset
        if isinstance(self.vivo, Unset):
            vivo = UNSET
        else:
            vivo = self.vivo

        http: int | None | Unset
        if isinstance(self.http, Unset):
            http = UNSET
        else:
            http = self.http

        ms: int | None | Unset
        if isinstance(self.ms, Unset):
            ms = UNSET
        else:
            ms = self.ms

        motivo: None | str | Unset
        if isinstance(self.motivo, Unset):
            motivo = UNSET
        else:
            motivo = self.motivo

        testado_em: None | str | Unset
        if isinstance(self.testado_em, Unset):
            testado_em = UNSET
        else:
            testado_em = self.testado_em

        primeiro_ok_em: None | str | Unset
        if isinstance(self.primeiro_ok_em, Unset):
            primeiro_ok_em = UNSET
        else:
            primeiro_ok_em = self.primeiro_ok_em

        falhas_seguidas = self.falhas_seguidas

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "slug": slug,
                "orgao": orgao,
                "nome": nome,
                "tipo": tipo,
                "url": url,
                "licenca": licenca,
                "origem": origem,
            }
        )
        if fonte_id is not UNSET:
            field_dict["fonte_id"] = fonte_id
        if vivo is not UNSET:
            field_dict["vivo"] = vivo
        if http is not UNSET:
            field_dict["http"] = http
        if ms is not UNSET:
            field_dict["ms"] = ms
        if motivo is not UNSET:
            field_dict["motivo"] = motivo
        if testado_em is not UNSET:
            field_dict["testado_em"] = testado_em
        if primeiro_ok_em is not UNSET:
            field_dict["primeiro_ok_em"] = primeiro_ok_em
        if falhas_seguidas is not UNSET:
            field_dict["falhas_seguidas"] = falhas_seguidas

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        slug = d.pop("slug")

        orgao = d.pop("orgao")

        nome = d.pop("nome")

        tipo = d.pop("tipo")

        url = d.pop("url")

        licenca = d.pop("licenca")

        origem = d.pop("origem")

        def _parse_fonte_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        fonte_id = _parse_fonte_id(d.pop("fonte_id", UNSET))

        def _parse_vivo(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        vivo = _parse_vivo(d.pop("vivo", UNSET))

        def _parse_http(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        http = _parse_http(d.pop("http", UNSET))

        def _parse_ms(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ms = _parse_ms(d.pop("ms", UNSET))

        def _parse_motivo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        motivo = _parse_motivo(d.pop("motivo", UNSET))

        def _parse_testado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        testado_em = _parse_testado_em(d.pop("testado_em", UNSET))

        def _parse_primeiro_ok_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        primeiro_ok_em = _parse_primeiro_ok_em(d.pop("primeiro_ok_em", UNSET))

        falhas_seguidas = d.pop("falhas_seguidas", UNSET)

        endpoint_publico = cls(
            id=id,
            slug=slug,
            orgao=orgao,
            nome=nome,
            tipo=tipo,
            url=url,
            licenca=licenca,
            origem=origem,
            fonte_id=fonte_id,
            vivo=vivo,
            http=http,
            ms=ms,
            motivo=motivo,
            testado_em=testado_em,
            primeiro_ok_em=primeiro_ok_em,
            falhas_seguidas=falhas_seguidas,
        )

        endpoint_publico.additional_properties = d
        return endpoint_publico

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
