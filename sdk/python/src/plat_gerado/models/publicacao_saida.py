from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PublicacaoSaida")


@_attrs_define
class PublicacaoSaida:
    """
    Attributes:
        item_id (str):
        estado (str):
        portal (None | str | Unset):
        agol_geojson_item_id (None | str | Unset):
        agol_servico_item_id (None | str | Unset):
        servico_url (None | str | Unset):
        n_feicoes (int | None | Unset):
        mensagem (None | str | Unset):
        job_id (None | str | Unset):
        publicado_em (None | str | Unset):
        atualizado_em (None | str | Unset):
    """

    item_id: str
    estado: str
    portal: None | str | Unset = UNSET
    agol_geojson_item_id: None | str | Unset = UNSET
    agol_servico_item_id: None | str | Unset = UNSET
    servico_url: None | str | Unset = UNSET
    n_feicoes: int | None | Unset = UNSET
    mensagem: None | str | Unset = UNSET
    job_id: None | str | Unset = UNSET
    publicado_em: None | str | Unset = UNSET
    atualizado_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        item_id = self.item_id

        estado = self.estado

        portal: None | str | Unset
        if isinstance(self.portal, Unset):
            portal = UNSET
        else:
            portal = self.portal

        agol_geojson_item_id: None | str | Unset
        if isinstance(self.agol_geojson_item_id, Unset):
            agol_geojson_item_id = UNSET
        else:
            agol_geojson_item_id = self.agol_geojson_item_id

        agol_servico_item_id: None | str | Unset
        if isinstance(self.agol_servico_item_id, Unset):
            agol_servico_item_id = UNSET
        else:
            agol_servico_item_id = self.agol_servico_item_id

        servico_url: None | str | Unset
        if isinstance(self.servico_url, Unset):
            servico_url = UNSET
        else:
            servico_url = self.servico_url

        n_feicoes: int | None | Unset
        if isinstance(self.n_feicoes, Unset):
            n_feicoes = UNSET
        else:
            n_feicoes = self.n_feicoes

        mensagem: None | str | Unset
        if isinstance(self.mensagem, Unset):
            mensagem = UNSET
        else:
            mensagem = self.mensagem

        job_id: None | str | Unset
        if isinstance(self.job_id, Unset):
            job_id = UNSET
        else:
            job_id = self.job_id

        publicado_em: None | str | Unset
        if isinstance(self.publicado_em, Unset):
            publicado_em = UNSET
        else:
            publicado_em = self.publicado_em

        atualizado_em: None | str | Unset
        if isinstance(self.atualizado_em, Unset):
            atualizado_em = UNSET
        else:
            atualizado_em = self.atualizado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "item_id": item_id,
                "estado": estado,
            }
        )
        if portal is not UNSET:
            field_dict["portal"] = portal
        if agol_geojson_item_id is not UNSET:
            field_dict["agol_geojson_item_id"] = agol_geojson_item_id
        if agol_servico_item_id is not UNSET:
            field_dict["agol_servico_item_id"] = agol_servico_item_id
        if servico_url is not UNSET:
            field_dict["servico_url"] = servico_url
        if n_feicoes is not UNSET:
            field_dict["n_feicoes"] = n_feicoes
        if mensagem is not UNSET:
            field_dict["mensagem"] = mensagem
        if job_id is not UNSET:
            field_dict["job_id"] = job_id
        if publicado_em is not UNSET:
            field_dict["publicado_em"] = publicado_em
        if atualizado_em is not UNSET:
            field_dict["atualizado_em"] = atualizado_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        item_id = d.pop("item_id")

        estado = d.pop("estado")

        def _parse_portal(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        portal = _parse_portal(d.pop("portal", UNSET))

        def _parse_agol_geojson_item_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        agol_geojson_item_id = _parse_agol_geojson_item_id(d.pop("agol_geojson_item_id", UNSET))

        def _parse_agol_servico_item_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        agol_servico_item_id = _parse_agol_servico_item_id(d.pop("agol_servico_item_id", UNSET))

        def _parse_servico_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        servico_url = _parse_servico_url(d.pop("servico_url", UNSET))

        def _parse_n_feicoes(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        n_feicoes = _parse_n_feicoes(d.pop("n_feicoes", UNSET))

        def _parse_mensagem(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mensagem = _parse_mensagem(d.pop("mensagem", UNSET))

        def _parse_job_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        job_id = _parse_job_id(d.pop("job_id", UNSET))

        def _parse_publicado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        publicado_em = _parse_publicado_em(d.pop("publicado_em", UNSET))

        def _parse_atualizado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        atualizado_em = _parse_atualizado_em(d.pop("atualizado_em", UNSET))

        publicacao_saida = cls(
            item_id=item_id,
            estado=estado,
            portal=portal,
            agol_geojson_item_id=agol_geojson_item_id,
            agol_servico_item_id=agol_servico_item_id,
            servico_url=servico_url,
            n_feicoes=n_feicoes,
            mensagem=mensagem,
            job_id=job_id,
            publicado_em=publicado_em,
            atualizado_em=atualizado_em,
        )

        publicacao_saida.additional_properties = d
        return publicacao_saida

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
