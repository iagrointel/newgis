from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AcervoCamadaPublicada")


@_attrs_define
class AcervoCamadaPublicada:
    """Uma view de `plat_acervo` (item L6-01-b). `assinada` é deste inquilino: a RLS de
    plat.acervo_assinatura já recorta o LEFT JOIN, então nunca vaza a assinatura de outro.

        Attributes:
            view_nome (str):
            acervo_camada_id (str):
            fonte_id (str):
            schema_origem (str):
            tabela_origem (str):
            coluna_geom (str):
            srid (int):
            colunas (list[str]):
            assinada (bool):
            linhas_exatas (int | None | Unset):
            tipo_geom (None | str | Unset):
    """

    view_nome: str
    acervo_camada_id: str
    fonte_id: str
    schema_origem: str
    tabela_origem: str
    coluna_geom: str
    srid: int
    colunas: list[str]
    assinada: bool
    linhas_exatas: int | None | Unset = UNSET
    tipo_geom: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        view_nome = self.view_nome

        acervo_camada_id = self.acervo_camada_id

        fonte_id = self.fonte_id

        schema_origem = self.schema_origem

        tabela_origem = self.tabela_origem

        coluna_geom = self.coluna_geom

        srid = self.srid

        colunas = self.colunas

        assinada = self.assinada

        linhas_exatas: int | None | Unset
        if isinstance(self.linhas_exatas, Unset):
            linhas_exatas = UNSET
        else:
            linhas_exatas = self.linhas_exatas

        tipo_geom: None | str | Unset
        if isinstance(self.tipo_geom, Unset):
            tipo_geom = UNSET
        else:
            tipo_geom = self.tipo_geom

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "view_nome": view_nome,
                "acervo_camada_id": acervo_camada_id,
                "fonte_id": fonte_id,
                "schema_origem": schema_origem,
                "tabela_origem": tabela_origem,
                "coluna_geom": coluna_geom,
                "srid": srid,
                "colunas": colunas,
                "assinada": assinada,
            }
        )
        if linhas_exatas is not UNSET:
            field_dict["linhas_exatas"] = linhas_exatas
        if tipo_geom is not UNSET:
            field_dict["tipo_geom"] = tipo_geom

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        view_nome = d.pop("view_nome")

        acervo_camada_id = d.pop("acervo_camada_id")

        fonte_id = d.pop("fonte_id")

        schema_origem = d.pop("schema_origem")

        tabela_origem = d.pop("tabela_origem")

        coluna_geom = d.pop("coluna_geom")

        srid = d.pop("srid")

        colunas = cast(list[str], d.pop("colunas"))

        assinada = d.pop("assinada")

        def _parse_linhas_exatas(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        linhas_exatas = _parse_linhas_exatas(d.pop("linhas_exatas", UNSET))

        def _parse_tipo_geom(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tipo_geom = _parse_tipo_geom(d.pop("tipo_geom", UNSET))

        acervo_camada_publicada = cls(
            view_nome=view_nome,
            acervo_camada_id=acervo_camada_id,
            fonte_id=fonte_id,
            schema_origem=schema_origem,
            tabela_origem=tabela_origem,
            coluna_geom=coluna_geom,
            srid=srid,
            colunas=colunas,
            assinada=assinada,
            linhas_exatas=linhas_exatas,
            tipo_geom=tipo_geom,
        )

        acervo_camada_publicada.additional_properties = d
        return acervo_camada_publicada

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
