from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Controlador")


@_attrs_define
class Controlador:
    """
    Attributes:
        id (str):
        nome (str):
        papel (str):
        origem (str):
        subrede_id (str):
        subrede (str):
        tier (str):
        tier_nome (str):
        tier_tipo (str):
        tier_ordem (int):
        feicao_id (None | str):
        terminal (int | None):
        tipo_id (None | str):
        grupo (None | str):
        tipo_chave (None | str):
        tipo_nome (None | str):
        no_id (None | str):
        lon (float):
        lat (float):
    """

    id: str
    nome: str
    papel: str
    origem: str
    subrede_id: str
    subrede: str
    tier: str
    tier_nome: str
    tier_tipo: str
    tier_ordem: int
    feicao_id: None | str
    terminal: int | None
    tipo_id: None | str
    grupo: None | str
    tipo_chave: None | str
    tipo_nome: None | str
    no_id: None | str
    lon: float
    lat: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        nome = self.nome

        papel = self.papel

        origem = self.origem

        subrede_id = self.subrede_id

        subrede = self.subrede

        tier = self.tier

        tier_nome = self.tier_nome

        tier_tipo = self.tier_tipo

        tier_ordem = self.tier_ordem

        feicao_id: None | str
        feicao_id = self.feicao_id

        terminal: int | None
        terminal = self.terminal

        tipo_id: None | str
        tipo_id = self.tipo_id

        grupo: None | str
        grupo = self.grupo

        tipo_chave: None | str
        tipo_chave = self.tipo_chave

        tipo_nome: None | str
        tipo_nome = self.tipo_nome

        no_id: None | str
        no_id = self.no_id

        lon = self.lon

        lat = self.lat

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nome": nome,
                "papel": papel,
                "origem": origem,
                "subrede_id": subrede_id,
                "subrede": subrede,
                "tier": tier,
                "tier_nome": tier_nome,
                "tier_tipo": tier_tipo,
                "tier_ordem": tier_ordem,
                "feicao_id": feicao_id,
                "terminal": terminal,
                "tipo_id": tipo_id,
                "grupo": grupo,
                "tipo_chave": tipo_chave,
                "tipo_nome": tipo_nome,
                "no_id": no_id,
                "lon": lon,
                "lat": lat,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        nome = d.pop("nome")

        papel = d.pop("papel")

        origem = d.pop("origem")

        subrede_id = d.pop("subrede_id")

        subrede = d.pop("subrede")

        tier = d.pop("tier")

        tier_nome = d.pop("tier_nome")

        tier_tipo = d.pop("tier_tipo")

        tier_ordem = d.pop("tier_ordem")

        def _parse_feicao_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        feicao_id = _parse_feicao_id(d.pop("feicao_id"))

        def _parse_terminal(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        terminal = _parse_terminal(d.pop("terminal"))

        def _parse_tipo_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        tipo_id = _parse_tipo_id(d.pop("tipo_id"))

        def _parse_grupo(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        grupo = _parse_grupo(d.pop("grupo"))

        def _parse_tipo_chave(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        tipo_chave = _parse_tipo_chave(d.pop("tipo_chave"))

        def _parse_tipo_nome(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        tipo_nome = _parse_tipo_nome(d.pop("tipo_nome"))

        def _parse_no_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        no_id = _parse_no_id(d.pop("no_id"))

        lon = d.pop("lon")

        lat = d.pop("lat")

        controlador = cls(
            id=id,
            nome=nome,
            papel=papel,
            origem=origem,
            subrede_id=subrede_id,
            subrede=subrede,
            tier=tier,
            tier_nome=tier_nome,
            tier_tipo=tier_tipo,
            tier_ordem=tier_ordem,
            feicao_id=feicao_id,
            terminal=terminal,
            tipo_id=tipo_id,
            grupo=grupo,
            tipo_chave=tipo_chave,
            tipo_nome=tipo_nome,
            no_id=no_id,
            lon=lon,
            lat=lat,
        )

        controlador.additional_properties = d
        return controlador

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
