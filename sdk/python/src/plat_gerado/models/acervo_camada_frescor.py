from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AcervoCamadaFrescor")


@_attrs_define
class AcervoCamadaFrescor:
    """Uma camada do registro com o estado de verificação. `linhas_exatas` é NULL quando a contagem não coube
    no prazo de 25 s — a tela escreve "não contado no prazo", nunca zero, e `reltuples` não aparece aqui.

        Attributes:
            acervo_camada_id (str):
            fonte_id (str):
            schema_nome (str):
            tabela (str):
            estado (str):
            fonte_nome (None | str | Unset):
            fonte_dominio (None | str | Unset):
            fonte_licenca (None | str | Unset):
            fonte_frescor (None | str | Unset):
            proxima_verificacao (None | str | Unset):
            verificada_em (None | str | Unset):
            contagem_estado (None | str | Unset):
            linhas_exatas (int | None | Unset):
            linhas_anteriores (int | None | Unset):
            variacao_pct (float | None | Unset):
            mudanca_relevante (bool | None | Unset):
            hash_estado (None | str | Unset):
            endpoints_testados (int | Unset):  Default: 0.
            endpoints_mortos (int | Unset):  Default: 0.
            endpoint_morto (bool | Unset):  Default: False.
            prazo_da_fonte_vencido (bool | Unset):  Default: False.
            nunca_verificada (bool | Unset):  Default: True.
            verificacao_antiga (bool | Unset):  Default: False.
            verificacao_vencida (bool | Unset):  Default: False.
            motivo_vencida (None | str | Unset):
    """

    acervo_camada_id: str
    fonte_id: str
    schema_nome: str
    tabela: str
    estado: str
    fonte_nome: None | str | Unset = UNSET
    fonte_dominio: None | str | Unset = UNSET
    fonte_licenca: None | str | Unset = UNSET
    fonte_frescor: None | str | Unset = UNSET
    proxima_verificacao: None | str | Unset = UNSET
    verificada_em: None | str | Unset = UNSET
    contagem_estado: None | str | Unset = UNSET
    linhas_exatas: int | None | Unset = UNSET
    linhas_anteriores: int | None | Unset = UNSET
    variacao_pct: float | None | Unset = UNSET
    mudanca_relevante: bool | None | Unset = UNSET
    hash_estado: None | str | Unset = UNSET
    endpoints_testados: int | Unset = 0
    endpoints_mortos: int | Unset = 0
    endpoint_morto: bool | Unset = False
    prazo_da_fonte_vencido: bool | Unset = False
    nunca_verificada: bool | Unset = True
    verificacao_antiga: bool | Unset = False
    verificacao_vencida: bool | Unset = False
    motivo_vencida: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        acervo_camada_id = self.acervo_camada_id

        fonte_id = self.fonte_id

        schema_nome = self.schema_nome

        tabela = self.tabela

        estado = self.estado

        fonte_nome: None | str | Unset
        if isinstance(self.fonte_nome, Unset):
            fonte_nome = UNSET
        else:
            fonte_nome = self.fonte_nome

        fonte_dominio: None | str | Unset
        if isinstance(self.fonte_dominio, Unset):
            fonte_dominio = UNSET
        else:
            fonte_dominio = self.fonte_dominio

        fonte_licenca: None | str | Unset
        if isinstance(self.fonte_licenca, Unset):
            fonte_licenca = UNSET
        else:
            fonte_licenca = self.fonte_licenca

        fonte_frescor: None | str | Unset
        if isinstance(self.fonte_frescor, Unset):
            fonte_frescor = UNSET
        else:
            fonte_frescor = self.fonte_frescor

        proxima_verificacao: None | str | Unset
        if isinstance(self.proxima_verificacao, Unset):
            proxima_verificacao = UNSET
        else:
            proxima_verificacao = self.proxima_verificacao

        verificada_em: None | str | Unset
        if isinstance(self.verificada_em, Unset):
            verificada_em = UNSET
        else:
            verificada_em = self.verificada_em

        contagem_estado: None | str | Unset
        if isinstance(self.contagem_estado, Unset):
            contagem_estado = UNSET
        else:
            contagem_estado = self.contagem_estado

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

        mudanca_relevante: bool | None | Unset
        if isinstance(self.mudanca_relevante, Unset):
            mudanca_relevante = UNSET
        else:
            mudanca_relevante = self.mudanca_relevante

        hash_estado: None | str | Unset
        if isinstance(self.hash_estado, Unset):
            hash_estado = UNSET
        else:
            hash_estado = self.hash_estado

        endpoints_testados = self.endpoints_testados

        endpoints_mortos = self.endpoints_mortos

        endpoint_morto = self.endpoint_morto

        prazo_da_fonte_vencido = self.prazo_da_fonte_vencido

        nunca_verificada = self.nunca_verificada

        verificacao_antiga = self.verificacao_antiga

        verificacao_vencida = self.verificacao_vencida

        motivo_vencida: None | str | Unset
        if isinstance(self.motivo_vencida, Unset):
            motivo_vencida = UNSET
        else:
            motivo_vencida = self.motivo_vencida

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "acervo_camada_id": acervo_camada_id,
                "fonte_id": fonte_id,
                "schema_nome": schema_nome,
                "tabela": tabela,
                "estado": estado,
            }
        )
        if fonte_nome is not UNSET:
            field_dict["fonte_nome"] = fonte_nome
        if fonte_dominio is not UNSET:
            field_dict["fonte_dominio"] = fonte_dominio
        if fonte_licenca is not UNSET:
            field_dict["fonte_licenca"] = fonte_licenca
        if fonte_frescor is not UNSET:
            field_dict["fonte_frescor"] = fonte_frescor
        if proxima_verificacao is not UNSET:
            field_dict["proxima_verificacao"] = proxima_verificacao
        if verificada_em is not UNSET:
            field_dict["verificada_em"] = verificada_em
        if contagem_estado is not UNSET:
            field_dict["contagem_estado"] = contagem_estado
        if linhas_exatas is not UNSET:
            field_dict["linhas_exatas"] = linhas_exatas
        if linhas_anteriores is not UNSET:
            field_dict["linhas_anteriores"] = linhas_anteriores
        if variacao_pct is not UNSET:
            field_dict["variacao_pct"] = variacao_pct
        if mudanca_relevante is not UNSET:
            field_dict["mudanca_relevante"] = mudanca_relevante
        if hash_estado is not UNSET:
            field_dict["hash_estado"] = hash_estado
        if endpoints_testados is not UNSET:
            field_dict["endpoints_testados"] = endpoints_testados
        if endpoints_mortos is not UNSET:
            field_dict["endpoints_mortos"] = endpoints_mortos
        if endpoint_morto is not UNSET:
            field_dict["endpoint_morto"] = endpoint_morto
        if prazo_da_fonte_vencido is not UNSET:
            field_dict["prazo_da_fonte_vencido"] = prazo_da_fonte_vencido
        if nunca_verificada is not UNSET:
            field_dict["nunca_verificada"] = nunca_verificada
        if verificacao_antiga is not UNSET:
            field_dict["verificacao_antiga"] = verificacao_antiga
        if verificacao_vencida is not UNSET:
            field_dict["verificacao_vencida"] = verificacao_vencida
        if motivo_vencida is not UNSET:
            field_dict["motivo_vencida"] = motivo_vencida

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        acervo_camada_id = d.pop("acervo_camada_id")

        fonte_id = d.pop("fonte_id")

        schema_nome = d.pop("schema_nome")

        tabela = d.pop("tabela")

        estado = d.pop("estado")

        def _parse_fonte_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        fonte_nome = _parse_fonte_nome(d.pop("fonte_nome", UNSET))

        def _parse_fonte_dominio(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        fonte_dominio = _parse_fonte_dominio(d.pop("fonte_dominio", UNSET))

        def _parse_fonte_licenca(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        fonte_licenca = _parse_fonte_licenca(d.pop("fonte_licenca", UNSET))

        def _parse_fonte_frescor(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        fonte_frescor = _parse_fonte_frescor(d.pop("fonte_frescor", UNSET))

        def _parse_proxima_verificacao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        proxima_verificacao = _parse_proxima_verificacao(d.pop("proxima_verificacao", UNSET))

        def _parse_verificada_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        verificada_em = _parse_verificada_em(d.pop("verificada_em", UNSET))

        def _parse_contagem_estado(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        contagem_estado = _parse_contagem_estado(d.pop("contagem_estado", UNSET))

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

        def _parse_mudanca_relevante(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        mudanca_relevante = _parse_mudanca_relevante(d.pop("mudanca_relevante", UNSET))

        def _parse_hash_estado(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        hash_estado = _parse_hash_estado(d.pop("hash_estado", UNSET))

        endpoints_testados = d.pop("endpoints_testados", UNSET)

        endpoints_mortos = d.pop("endpoints_mortos", UNSET)

        endpoint_morto = d.pop("endpoint_morto", UNSET)

        prazo_da_fonte_vencido = d.pop("prazo_da_fonte_vencido", UNSET)

        nunca_verificada = d.pop("nunca_verificada", UNSET)

        verificacao_antiga = d.pop("verificacao_antiga", UNSET)

        verificacao_vencida = d.pop("verificacao_vencida", UNSET)

        def _parse_motivo_vencida(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        motivo_vencida = _parse_motivo_vencida(d.pop("motivo_vencida", UNSET))

        acervo_camada_frescor = cls(
            acervo_camada_id=acervo_camada_id,
            fonte_id=fonte_id,
            schema_nome=schema_nome,
            tabela=tabela,
            estado=estado,
            fonte_nome=fonte_nome,
            fonte_dominio=fonte_dominio,
            fonte_licenca=fonte_licenca,
            fonte_frescor=fonte_frescor,
            proxima_verificacao=proxima_verificacao,
            verificada_em=verificada_em,
            contagem_estado=contagem_estado,
            linhas_exatas=linhas_exatas,
            linhas_anteriores=linhas_anteriores,
            variacao_pct=variacao_pct,
            mudanca_relevante=mudanca_relevante,
            hash_estado=hash_estado,
            endpoints_testados=endpoints_testados,
            endpoints_mortos=endpoints_mortos,
            endpoint_morto=endpoint_morto,
            prazo_da_fonte_vencido=prazo_da_fonte_vencido,
            nunca_verificada=nunca_verificada,
            verificacao_antiga=verificacao_antiga,
            verificacao_vencida=verificacao_vencida,
            motivo_vencida=motivo_vencida,
        )

        acervo_camada_frescor.additional_properties = d
        return acervo_camada_frescor

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
