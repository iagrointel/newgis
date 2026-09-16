from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AcervoMudanca")


@_attrs_define
class AcervoMudanca:
    """
    Attributes:
        acervo_camada_id (str):
        fonte_id (str):
        schema_nome (str):
        tabela (str):
        verificada_em (str):
        linhas_anteriores (int | None | Unset):
        linhas_exatas (int | None | Unset):
        variacao_pct (float | None | Unset):
        execucao_id (int | None | Unset):
    """

    acervo_camada_id: str
    fonte_id: str
    schema_nome: str
    tabela: str
    verificada_em: str
    linhas_anteriores: int | None | Unset = UNSET
    linhas_exatas: int | None | Unset = UNSET
    variacao_pct: float | None | Unset = UNSET
    execucao_id: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        acervo_camada_id = self.acervo_camada_id

        fonte_id = self.fonte_id

        schema_nome = self.schema_nome

        tabela = self.tabela

        verificada_em = self.verificada_em

        linhas_anteriores: int | None | Unset
        if isinstance(self.linhas_anteriores, Unset):
            linhas_anteriores = UNSET
        else:
            linhas_anteriores = self.linhas_anteriores

        linhas_exatas: int | None | Unset
        if isinstance(self.linhas_exatas, Unset):
            linhas_exatas = UNSET
        else:
            linhas_exatas = self.linhas_exatas

        variacao_pct: float | None | Unset
        if isinstance(self.variacao_pct, Unset):
            variacao_pct = UNSET
        else:
            variacao_pct = self.variacao_pct

        execucao_id: int | None | Unset
        if isinstance(self.execucao_id, Unset):
            execucao_id = UNSET
        else:
            execucao_id = self.execucao_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "acervo_camada_id": acervo_camada_id,
                "fonte_id": fonte_id,
                "schema_nome": schema_nome,
                "tabela": tabela,
                "verificada_em": verificada_em,
            }
        )
        if linhas_anteriores is not UNSET:
            field_dict["linhas_anteriores"] = linhas_anteriores
        if linhas_exatas is not UNSET:
            field_dict["linhas_exatas"] = linhas_exatas
        if variacao_pct is not UNSET:
            field_dict["variacao_pct"] = variacao_pct
        if execucao_id is not UNSET:
            field_dict["execucao_id"] = execucao_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        acervo_camada_id = d.pop("acervo_camada_id")

        fonte_id = d.pop("fonte_id")

        schema_nome = d.pop("schema_nome")

        tabela = d.pop("tabela")

        verificada_em = d.pop("verificada_em")

        def _parse_linhas_anteriores(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        linhas_anteriores = _parse_linhas_anteriores(d.pop("linhas_anteriores", UNSET))

        def _parse_linhas_exatas(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        linhas_exatas = _parse_linhas_exatas(d.pop("linhas_exatas", UNSET))

        def _parse_variacao_pct(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        variacao_pct = _parse_variacao_pct(d.pop("variacao_pct", UNSET))

        def _parse_execucao_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        execucao_id = _parse_execucao_id(d.pop("execucao_id", UNSET))

        acervo_mudanca = cls(
            acervo_camada_id=acervo_camada_id,
            fonte_id=fonte_id,
            schema_nome=schema_nome,
            tabela=tabela,
            verificada_em=verificada_em,
            linhas_anteriores=linhas_anteriores,
            linhas_exatas=linhas_exatas,
            variacao_pct=variacao_pct,
            execucao_id=execucao_id,
        )

        acervo_mudanca.additional_properties = d
        return acervo_mudanca

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
