from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AcervoExecucao")


@_attrs_define
class AcervoExecucao:
    """
    Attributes:
        id (int):
        iniciada_em (str):
        concluida_em (None | str | Unset):
        duracao_ms (int | None | Unset):
        camadas_expostas (int | Unset):  Default: 0.
        camadas_verificadas (int | Unset):  Default: 0.
        camadas_nao_contadas (int | Unset):  Default: 0.
        endpoints_testados (int | Unset):  Default: 0.
        endpoints_responderam (int | Unset):  Default: 0.
        mudancas (int | Unset):  Default: 0.
    """

    id: int
    iniciada_em: str
    concluida_em: None | str | Unset = UNSET
    duracao_ms: int | None | Unset = UNSET
    camadas_expostas: int | Unset = 0
    camadas_verificadas: int | Unset = 0
    camadas_nao_contadas: int | Unset = 0
    endpoints_testados: int | Unset = 0
    endpoints_responderam: int | Unset = 0
    mudancas: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        iniciada_em = self.iniciada_em

        concluida_em: None | str | Unset
        if isinstance(self.concluida_em, Unset):
            concluida_em = UNSET
        else:
            concluida_em = self.concluida_em

        duracao_ms: int | None | Unset
        if isinstance(self.duracao_ms, Unset):
            duracao_ms = UNSET
        else:
            duracao_ms = self.duracao_ms

        camadas_expostas = self.camadas_expostas

        camadas_verificadas = self.camadas_verificadas

        camadas_nao_contadas = self.camadas_nao_contadas

        endpoints_testados = self.endpoints_testados

        endpoints_responderam = self.endpoints_responderam

        mudancas = self.mudancas

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "iniciada_em": iniciada_em,
            }
        )
        if concluida_em is not UNSET:
            field_dict["concluida_em"] = concluida_em
        if duracao_ms is not UNSET:
            field_dict["duracao_ms"] = duracao_ms
        if camadas_expostas is not UNSET:
            field_dict["camadas_expostas"] = camadas_expostas
        if camadas_verificadas is not UNSET:
            field_dict["camadas_verificadas"] = camadas_verificadas
        if camadas_nao_contadas is not UNSET:
            field_dict["camadas_nao_contadas"] = camadas_nao_contadas
        if endpoints_testados is not UNSET:
            field_dict["endpoints_testados"] = endpoints_testados
        if endpoints_responderam is not UNSET:
            field_dict["endpoints_responderam"] = endpoints_responderam
        if mudancas is not UNSET:
            field_dict["mudancas"] = mudancas

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        iniciada_em = d.pop("iniciada_em")

        def _parse_concluida_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        concluida_em = _parse_concluida_em(d.pop("concluida_em", UNSET))

        def _parse_duracao_ms(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        duracao_ms = _parse_duracao_ms(d.pop("duracao_ms", UNSET))

        camadas_expostas = d.pop("camadas_expostas", UNSET)

        camadas_verificadas = d.pop("camadas_verificadas", UNSET)

        camadas_nao_contadas = d.pop("camadas_nao_contadas", UNSET)

        endpoints_testados = d.pop("endpoints_testados", UNSET)

        endpoints_responderam = d.pop("endpoints_responderam", UNSET)

        mudancas = d.pop("mudancas", UNSET)

        acervo_execucao = cls(
            id=id,
            iniciada_em=iniciada_em,
            concluida_em=concluida_em,
            duracao_ms=duracao_ms,
            camadas_expostas=camadas_expostas,
            camadas_verificadas=camadas_verificadas,
            camadas_nao_contadas=camadas_nao_contadas,
            endpoints_testados=endpoints_testados,
            endpoints_responderam=endpoints_responderam,
            mudancas=mudancas,
        )

        acervo_execucao.additional_properties = d
        return acervo_execucao

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
