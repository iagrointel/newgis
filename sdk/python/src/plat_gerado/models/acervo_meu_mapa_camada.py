from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AcervoMeuMapaCamada")


@_attrs_define
class AcervoMeuMapaCamada:
    """Camada do acervo já adicionada pelo inquilino (legenda do mapa, item L6-01-c). `licenca_curada_tipo`
    é o valor CONGELADO no item no dia em que foi adicionado, não o de hoje: a legenda mostra a licença sob
    a qual a camada entrou no mapa.

        Attributes:
            item_id (str):
            titulo (str):
            fonte_id (None | str | Unset):
            licenca_curada_tipo (None | str | Unset):
            licenca (None | str | Unset):
            dominio (None | str | Unset):
            adicionado_em (None | str | Unset):
    """

    item_id: str
    titulo: str
    fonte_id: None | str | Unset = UNSET
    licenca_curada_tipo: None | str | Unset = UNSET
    licenca: None | str | Unset = UNSET
    dominio: None | str | Unset = UNSET
    adicionado_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        item_id = self.item_id

        titulo = self.titulo

        fonte_id: None | str | Unset
        if isinstance(self.fonte_id, Unset):
            fonte_id = UNSET
        else:
            fonte_id = self.fonte_id

        licenca_curada_tipo: None | str | Unset
        if isinstance(self.licenca_curada_tipo, Unset):
            licenca_curada_tipo = UNSET
        else:
            licenca_curada_tipo = self.licenca_curada_tipo

        licenca: None | str | Unset
        if isinstance(self.licenca, Unset):
            licenca = UNSET
        else:
            licenca = self.licenca

        dominio: None | str | Unset
        if isinstance(self.dominio, Unset):
            dominio = UNSET
        else:
            dominio = self.dominio

        adicionado_em: None | str | Unset
        if isinstance(self.adicionado_em, Unset):
            adicionado_em = UNSET
        else:
            adicionado_em = self.adicionado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "item_id": item_id,
                "titulo": titulo,
            }
        )
        if fonte_id is not UNSET:
            field_dict["fonte_id"] = fonte_id
        if licenca_curada_tipo is not UNSET:
            field_dict["licenca_curada_tipo"] = licenca_curada_tipo
        if licenca is not UNSET:
            field_dict["licenca"] = licenca
        if dominio is not UNSET:
            field_dict["dominio"] = dominio
        if adicionado_em is not UNSET:
            field_dict["adicionado_em"] = adicionado_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        item_id = d.pop("item_id")

        titulo = d.pop("titulo")

        def _parse_fonte_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        fonte_id = _parse_fonte_id(d.pop("fonte_id", UNSET))

        def _parse_licenca_curada_tipo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        licenca_curada_tipo = _parse_licenca_curada_tipo(d.pop("licenca_curada_tipo", UNSET))

        def _parse_licenca(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        licenca = _parse_licenca(d.pop("licenca", UNSET))

        def _parse_dominio(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dominio = _parse_dominio(d.pop("dominio", UNSET))

        def _parse_adicionado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        adicionado_em = _parse_adicionado_em(d.pop("adicionado_em", UNSET))

        acervo_meu_mapa_camada = cls(
            item_id=item_id,
            titulo=titulo,
            fonte_id=fonte_id,
            licenca_curada_tipo=licenca_curada_tipo,
            licenca=licenca,
            dominio=dominio,
            adicionado_em=adicionado_em,
        )

        acervo_meu_mapa_camada.additional_properties = d
        return acervo_meu_mapa_camada

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
