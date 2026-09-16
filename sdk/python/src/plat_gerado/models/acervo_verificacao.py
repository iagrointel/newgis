from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AcervoVerificacao")


@_attrs_define
class AcervoVerificacao:
    """
    Attributes:
        verificada_em (str):
        contagem_estado (str):
        hash_estado (str):
        linhas_exatas (int | None | Unset):
        linhas_anteriores (int | None | Unset):
        variacao_pct (float | None | Unset):
        mudanca_relevante (bool | Unset):  Default: False.
        hash_valor (None | str | Unset):
        duracao_ms (int | Unset):  Default: 0.
        execucao_id (int | None | Unset):
    """

    verificada_em: str
    contagem_estado: str
    hash_estado: str
    linhas_exatas: int | None | Unset = UNSET
    linhas_anteriores: int | None | Unset = UNSET
    variacao_pct: float | None | Unset = UNSET
    mudanca_relevante: bool | Unset = False
    hash_valor: None | str | Unset = UNSET
    duracao_ms: int | Unset = 0
    execucao_id: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        verificada_em = self.verificada_em

        contagem_estado = self.contagem_estado

        hash_estado = self.hash_estado

        linhas_exatas: int | None | Unset
        if isinstance(self.linhas_exatas, Unset):
            linhas_exatas = UNSET
        else:
            linhas_exatas = self.linhas_exatas

        linhas_anteriores: int | None | Unset
        if isinstance(self.linhas_anteriores, Unset):
            linhas_anteriores = UNSET
        else:
            linhas_anteriores = self.linhas_anteriores

        variacao_pct: float | None | Unset
        if isinstance(self.variacao_pct, Unset):
            variacao_pct = UNSET
        else:
            variacao_pct = self.variacao_pct

        mudanca_relevante = self.mudanca_relevante

        hash_valor: None | str | Unset
        if isinstance(self.hash_valor, Unset):
            hash_valor = UNSET
        else:
            hash_valor = self.hash_valor

        duracao_ms = self.duracao_ms

        execucao_id: int | None | Unset
        if isinstance(self.execucao_id, Unset):
            execucao_id = UNSET
        else:
            execucao_id = self.execucao_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "verificada_em": verificada_em,
                "contagem_estado": contagem_estado,
                "hash_estado": hash_estado,
            }
        )
        if linhas_exatas is not UNSET:
            field_dict["linhas_exatas"] = linhas_exatas
        if linhas_anteriores is not UNSET:
            field_dict["linhas_anteriores"] = linhas_anteriores
        if variacao_pct is not UNSET:
            field_dict["variacao_pct"] = variacao_pct
        if mudanca_relevante is not UNSET:
            field_dict["mudanca_relevante"] = mudanca_relevante
        if hash_valor is not UNSET:
            field_dict["hash_valor"] = hash_valor
        if duracao_ms is not UNSET:
            field_dict["duracao_ms"] = duracao_ms
        if execucao_id is not UNSET:
            field_dict["execucao_id"] = execucao_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        verificada_em = d.pop("verificada_em")

        contagem_estado = d.pop("contagem_estado")

        hash_estado = d.pop("hash_estado")

        def _parse_linhas_exatas(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        linhas_exatas = _parse_linhas_exatas(d.pop("linhas_exatas", UNSET))

        def _parse_linhas_anteriores(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        linhas_anteriores = _parse_linhas_anteriores(d.pop("linhas_anteriores", UNSET))

        def _parse_variacao_pct(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        variacao_pct = _parse_variacao_pct(d.pop("variacao_pct", UNSET))

        mudanca_relevante = d.pop("mudanca_relevante", UNSET)

        def _parse_hash_valor(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        hash_valor = _parse_hash_valor(d.pop("hash_valor", UNSET))

        duracao_ms = d.pop("duracao_ms", UNSET)

        def _parse_execucao_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        execucao_id = _parse_execucao_id(d.pop("execucao_id", UNSET))

        acervo_verificacao = cls(
            verificada_em=verificada_em,
            contagem_estado=contagem_estado,
            hash_estado=hash_estado,
            linhas_exatas=linhas_exatas,
            linhas_anteriores=linhas_anteriores,
            variacao_pct=variacao_pct,
            mudanca_relevante=mudanca_relevante,
            hash_valor=hash_valor,
            duracao_ms=duracao_ms,
            execucao_id=execucao_id,
        )

        acervo_verificacao.additional_properties = d
        return acervo_verificacao

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
