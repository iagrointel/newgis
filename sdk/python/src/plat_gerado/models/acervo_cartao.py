from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AcervoCartao")


@_attrs_define
class AcervoCartao:
    """
    Attributes:
        fonte_id (str):
        nome (str):
        dominio (str):
        licenca (str):
        numero_tabelas (int):
        registros_estimados (int):
        orgao (None | str | Unset):
        frescor (None | str | Unset):
        procedencia_pontuacao (float | None | Unset):
        proxima_verificacao (None | str | Unset):
        risco_pii (bool | Unset):  Default: False.
        risco_pii_motivo (None | str | Unset):
    """

    fonte_id: str
    nome: str
    dominio: str
    licenca: str
    numero_tabelas: int
    registros_estimados: int
    orgao: None | str | Unset = UNSET
    frescor: None | str | Unset = UNSET
    procedencia_pontuacao: float | None | Unset = UNSET
    proxima_verificacao: None | str | Unset = UNSET
    risco_pii: bool | Unset = False
    risco_pii_motivo: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        fonte_id = self.fonte_id

        nome = self.nome

        dominio = self.dominio

        licenca = self.licenca

        numero_tabelas = self.numero_tabelas

        registros_estimados = self.registros_estimados

        orgao: None | str | Unset
        if isinstance(self.orgao, Unset):
            orgao = UNSET
        else:
            orgao = self.orgao

        frescor: None | str | Unset
        if isinstance(self.frescor, Unset):
            frescor = UNSET
        else:
            frescor = self.frescor

        procedencia_pontuacao: float | None | Unset
        if isinstance(self.procedencia_pontuacao, Unset):
            procedencia_pontuacao = UNSET
        else:
            procedencia_pontuacao = self.procedencia_pontuacao

        proxima_verificacao: None | str | Unset
        if isinstance(self.proxima_verificacao, Unset):
            proxima_verificacao = UNSET
        else:
            proxima_verificacao = self.proxima_verificacao

        risco_pii = self.risco_pii

        risco_pii_motivo: None | str | Unset
        if isinstance(self.risco_pii_motivo, Unset):
            risco_pii_motivo = UNSET
        else:
            risco_pii_motivo = self.risco_pii_motivo

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "fonte_id": fonte_id,
                "nome": nome,
                "dominio": dominio,
                "licenca": licenca,
                "numero_tabelas": numero_tabelas,
                "registros_estimados": registros_estimados,
            }
        )
        if orgao is not UNSET:
            field_dict["orgao"] = orgao
        if frescor is not UNSET:
            field_dict["frescor"] = frescor
        if procedencia_pontuacao is not UNSET:
            field_dict["procedencia_pontuacao"] = procedencia_pontuacao
        if proxima_verificacao is not UNSET:
            field_dict["proxima_verificacao"] = proxima_verificacao
        if risco_pii is not UNSET:
            field_dict["risco_pii"] = risco_pii
        if risco_pii_motivo is not UNSET:
            field_dict["risco_pii_motivo"] = risco_pii_motivo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        fonte_id = d.pop("fonte_id")

        nome = d.pop("nome")

        dominio = d.pop("dominio")

        licenca = d.pop("licenca")

        numero_tabelas = d.pop("numero_tabelas")

        registros_estimados = d.pop("registros_estimados")

        def _parse_orgao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        orgao = _parse_orgao(d.pop("orgao", UNSET))

        def _parse_frescor(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        frescor = _parse_frescor(d.pop("frescor", UNSET))

        def _parse_procedencia_pontuacao(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        procedencia_pontuacao = _parse_procedencia_pontuacao(d.pop("procedencia_pontuacao", UNSET))

        def _parse_proxima_verificacao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        proxima_verificacao = _parse_proxima_verificacao(d.pop("proxima_verificacao", UNSET))

        risco_pii = d.pop("risco_pii", UNSET)

        def _parse_risco_pii_motivo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        risco_pii_motivo = _parse_risco_pii_motivo(d.pop("risco_pii_motivo", UNSET))

        acervo_cartao = cls(
            fonte_id=fonte_id,
            nome=nome,
            dominio=dominio,
            licenca=licenca,
            numero_tabelas=numero_tabelas,
            registros_estimados=registros_estimados,
            orgao=orgao,
            frescor=frescor,
            procedencia_pontuacao=procedencia_pontuacao,
            proxima_verificacao=proxima_verificacao,
            risco_pii=risco_pii,
            risco_pii_motivo=risco_pii_motivo,
        )

        acervo_cartao.additional_properties = d
        return acervo_cartao

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
