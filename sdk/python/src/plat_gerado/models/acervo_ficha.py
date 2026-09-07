from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.acervo_endpoint import AcervoEndpoint


T = TypeVar("T", bound="AcervoFicha")


@_attrs_define
class AcervoFicha:
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
        url (None | str | Unset):
        url_http (None | str | Unset):
        url_conferida_em (None | str | Unset):
        data_dado (None | str | Unset):
        data_acesso (None | str | Unset):
        script_gerador (None | str | Unset):
        sha256 (None | str | Unset):
        comando_reexecucao (None | str | Unset):
        metodo (None | str | Unset):
        confianca (None | str | Unset):
        limites (None | str | Unset):
        bytes_ (int | None | Unset):
        procedencia_campos (int | None | Unset):
        procedencia_campos_possiveis (int | None | Unset):
        atualizado_em (None | str | Unset):
        endpoints (list[AcervoEndpoint] | Unset):
        endpoints_total (int | Unset):  Default: 0.
        endpoints_confirmados_vivos (int | Unset):  Default: 0.
        completude_texto (None | str | Unset):
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
    url: None | str | Unset = UNSET
    url_http: None | str | Unset = UNSET
    url_conferida_em: None | str | Unset = UNSET
    data_dado: None | str | Unset = UNSET
    data_acesso: None | str | Unset = UNSET
    script_gerador: None | str | Unset = UNSET
    sha256: None | str | Unset = UNSET
    comando_reexecucao: None | str | Unset = UNSET
    metodo: None | str | Unset = UNSET
    confianca: None | str | Unset = UNSET
    limites: None | str | Unset = UNSET
    bytes_: int | None | Unset = UNSET
    procedencia_campos: int | None | Unset = UNSET
    procedencia_campos_possiveis: int | None | Unset = UNSET
    atualizado_em: None | str | Unset = UNSET
    endpoints: list[AcervoEndpoint] | Unset = UNSET
    endpoints_total: int | Unset = 0
    endpoints_confirmados_vivos: int | Unset = 0
    completude_texto: None | str | Unset = UNSET
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

        url: None | str | Unset
        if isinstance(self.url, Unset):
            url = UNSET
        else:
            url = self.url

        url_http: None | str | Unset
        if isinstance(self.url_http, Unset):
            url_http = UNSET
        else:
            url_http = self.url_http

        url_conferida_em: None | str | Unset
        if isinstance(self.url_conferida_em, Unset):
            url_conferida_em = UNSET
        else:
            url_conferida_em = self.url_conferida_em

        data_dado: None | str | Unset
        if isinstance(self.data_dado, Unset):
            data_dado = UNSET
        else:
            data_dado = self.data_dado

        data_acesso: None | str | Unset
        if isinstance(self.data_acesso, Unset):
            data_acesso = UNSET
        else:
            data_acesso = self.data_acesso

        script_gerador: None | str | Unset
        if isinstance(self.script_gerador, Unset):
            script_gerador = UNSET
        else:
            script_gerador = self.script_gerador

        sha256: None | str | Unset
        if isinstance(self.sha256, Unset):
            sha256 = UNSET
        else:
            sha256 = self.sha256

        comando_reexecucao: None | str | Unset
        if isinstance(self.comando_reexecucao, Unset):
            comando_reexecucao = UNSET
        else:
            comando_reexecucao = self.comando_reexecucao

        metodo: None | str | Unset
        if isinstance(self.metodo, Unset):
            metodo = UNSET
        else:
            metodo = self.metodo

        confianca: None | str | Unset
        if isinstance(self.confianca, Unset):
            confianca = UNSET
        else:
            confianca = self.confianca

        limites: None | str | Unset
        if isinstance(self.limites, Unset):
            limites = UNSET
        else:
            limites = self.limites

        bytes_: int | None | Unset
        if isinstance(self.bytes_, Unset):
            bytes_ = UNSET
        else:
            bytes_ = self.bytes_

        procedencia_campos: int | None | Unset
        if isinstance(self.procedencia_campos, Unset):
            procedencia_campos = UNSET
        else:
            procedencia_campos = self.procedencia_campos

        procedencia_campos_possiveis: int | None | Unset
        if isinstance(self.procedencia_campos_possiveis, Unset):
            procedencia_campos_possiveis = UNSET
        else:
            procedencia_campos_possiveis = self.procedencia_campos_possiveis

        atualizado_em: None | str | Unset
        if isinstance(self.atualizado_em, Unset):
            atualizado_em = UNSET
        else:
            atualizado_em = self.atualizado_em

        endpoints: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.endpoints, Unset):
            endpoints = []
            for endpoints_item_data in self.endpoints:
                endpoints_item = endpoints_item_data.to_dict()
                endpoints.append(endpoints_item)

        endpoints_total = self.endpoints_total

        endpoints_confirmados_vivos = self.endpoints_confirmados_vivos

        completude_texto: None | str | Unset
        if isinstance(self.completude_texto, Unset):
            completude_texto = UNSET
        else:
            completude_texto = self.completude_texto

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
        if url is not UNSET:
            field_dict["url"] = url
        if url_http is not UNSET:
            field_dict["url_http"] = url_http
        if url_conferida_em is not UNSET:
            field_dict["url_conferida_em"] = url_conferida_em
        if data_dado is not UNSET:
            field_dict["data_dado"] = data_dado
        if data_acesso is not UNSET:
            field_dict["data_acesso"] = data_acesso
        if script_gerador is not UNSET:
            field_dict["script_gerador"] = script_gerador
        if sha256 is not UNSET:
            field_dict["sha256"] = sha256
        if comando_reexecucao is not UNSET:
            field_dict["comando_reexecucao"] = comando_reexecucao
        if metodo is not UNSET:
            field_dict["metodo"] = metodo
        if confianca is not UNSET:
            field_dict["confianca"] = confianca
        if limites is not UNSET:
            field_dict["limites"] = limites
        if bytes_ is not UNSET:
            field_dict["bytes"] = bytes_
        if procedencia_campos is not UNSET:
            field_dict["procedencia_campos"] = procedencia_campos
        if procedencia_campos_possiveis is not UNSET:
            field_dict["procedencia_campos_possiveis"] = procedencia_campos_possiveis
        if atualizado_em is not UNSET:
            field_dict["atualizado_em"] = atualizado_em
        if endpoints is not UNSET:
            field_dict["endpoints"] = endpoints
        if endpoints_total is not UNSET:
            field_dict["endpoints_total"] = endpoints_total
        if endpoints_confirmados_vivos is not UNSET:
            field_dict["endpoints_confirmados_vivos"] = endpoints_confirmados_vivos
        if completude_texto is not UNSET:
            field_dict["completude_texto"] = completude_texto

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.acervo_endpoint import AcervoEndpoint  # noqa: PLC0415

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

        def _parse_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        url = _parse_url(d.pop("url", UNSET))

        def _parse_url_http(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        url_http = _parse_url_http(d.pop("url_http", UNSET))

        def _parse_url_conferida_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        url_conferida_em = _parse_url_conferida_em(d.pop("url_conferida_em", UNSET))

        def _parse_data_dado(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        data_dado = _parse_data_dado(d.pop("data_dado", UNSET))

        def _parse_data_acesso(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        data_acesso = _parse_data_acesso(d.pop("data_acesso", UNSET))

        def _parse_script_gerador(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        script_gerador = _parse_script_gerador(d.pop("script_gerador", UNSET))

        def _parse_sha256(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sha256 = _parse_sha256(d.pop("sha256", UNSET))

        def _parse_comando_reexecucao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        comando_reexecucao = _parse_comando_reexecucao(d.pop("comando_reexecucao", UNSET))

        def _parse_metodo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        metodo = _parse_metodo(d.pop("metodo", UNSET))

        def _parse_confianca(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        confianca = _parse_confianca(d.pop("confianca", UNSET))

        def _parse_limites(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        limites = _parse_limites(d.pop("limites", UNSET))

        def _parse_bytes_(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        bytes_ = _parse_bytes_(d.pop("bytes", UNSET))

        def _parse_procedencia_campos(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        procedencia_campos = _parse_procedencia_campos(d.pop("procedencia_campos", UNSET))

        def _parse_procedencia_campos_possiveis(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        procedencia_campos_possiveis = _parse_procedencia_campos_possiveis(d.pop("procedencia_campos_possiveis", UNSET))

        def _parse_atualizado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        atualizado_em = _parse_atualizado_em(d.pop("atualizado_em", UNSET))

        _endpoints = d.pop("endpoints", UNSET)
        endpoints: list[AcervoEndpoint] | Unset = UNSET
        if _endpoints is not UNSET:
            endpoints = []
            for endpoints_item_data in _endpoints:
                endpoints_item = AcervoEndpoint.from_dict(endpoints_item_data)

                endpoints.append(endpoints_item)

        endpoints_total = d.pop("endpoints_total", UNSET)

        endpoints_confirmados_vivos = d.pop("endpoints_confirmados_vivos", UNSET)

        def _parse_completude_texto(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        completude_texto = _parse_completude_texto(d.pop("completude_texto", UNSET))

        acervo_ficha = cls(
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
            url=url,
            url_http=url_http,
            url_conferida_em=url_conferida_em,
            data_dado=data_dado,
            data_acesso=data_acesso,
            script_gerador=script_gerador,
            sha256=sha256,
            comando_reexecucao=comando_reexecucao,
            metodo=metodo,
            confianca=confianca,
            limites=limites,
            bytes_=bytes_,
            procedencia_campos=procedencia_campos,
            procedencia_campos_possiveis=procedencia_campos_possiveis,
            atualizado_em=atualizado_em,
            endpoints=endpoints,
            endpoints_total=endpoints_total,
            endpoints_confirmados_vivos=endpoints_confirmados_vivos,
            completude_texto=completude_texto,
        )

        acervo_ficha.additional_properties = d
        return acervo_ficha

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
