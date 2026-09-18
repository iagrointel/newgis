from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="FichaEntrada")


@_attrs_define
class FichaEntrada:
    """
    Attributes:
        plataforma (str):
        instrumentos (list[str]):
        gsd (float):
        data_aquisicao (str):
        fornecedor (str):
        licenca (str):
        fonte (str):
        constelacao (None | str | Unset):
        data_aquisicao_fim (None | str | Unset):
        nuvem_pct (float | None | Unset):
        angulo_off_nadir (float | None | Unset):
        angulo_incidencia (float | None | Unset):
        angulo_azimute (float | None | Unset):
        sol_azimute (float | None | Unset):
        sol_elevacao (float | None | Unset):
        orbita_estado (None | str | Unset):
        orbita_relativa (int | None | Unset):
        orbita_absoluta (int | None | Unset):
        atribuicao (None | str | Unset):
        observacao (None | str | Unset):
    """

    plataforma: str
    instrumentos: list[str]
    gsd: float
    data_aquisicao: str
    fornecedor: str
    licenca: str
    fonte: str
    constelacao: None | str | Unset = UNSET
    data_aquisicao_fim: None | str | Unset = UNSET
    nuvem_pct: float | None | Unset = UNSET
    angulo_off_nadir: float | None | Unset = UNSET
    angulo_incidencia: float | None | Unset = UNSET
    angulo_azimute: float | None | Unset = UNSET
    sol_azimute: float | None | Unset = UNSET
    sol_elevacao: float | None | Unset = UNSET
    orbita_estado: None | str | Unset = UNSET
    orbita_relativa: int | None | Unset = UNSET
    orbita_absoluta: int | None | Unset = UNSET
    atribuicao: None | str | Unset = UNSET
    observacao: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        plataforma = self.plataforma

        instrumentos = self.instrumentos

        gsd = self.gsd

        data_aquisicao = self.data_aquisicao

        fornecedor = self.fornecedor

        licenca = self.licenca

        fonte = self.fonte

        constelacao: None | str | Unset
        if isinstance(self.constelacao, Unset):
            constelacao = UNSET
        else:
            constelacao = self.constelacao

        data_aquisicao_fim: None | str | Unset
        if isinstance(self.data_aquisicao_fim, Unset):
            data_aquisicao_fim = UNSET
        else:
            data_aquisicao_fim = self.data_aquisicao_fim

        nuvem_pct: float | None | Unset
        if isinstance(self.nuvem_pct, Unset):
            nuvem_pct = UNSET
        else:
            nuvem_pct = self.nuvem_pct

        angulo_off_nadir: float | None | Unset
        if isinstance(self.angulo_off_nadir, Unset):
            angulo_off_nadir = UNSET
        else:
            angulo_off_nadir = self.angulo_off_nadir

        angulo_incidencia: float | None | Unset
        if isinstance(self.angulo_incidencia, Unset):
            angulo_incidencia = UNSET
        else:
            angulo_incidencia = self.angulo_incidencia

        angulo_azimute: float | None | Unset
        if isinstance(self.angulo_azimute, Unset):
            angulo_azimute = UNSET
        else:
            angulo_azimute = self.angulo_azimute

        sol_azimute: float | None | Unset
        if isinstance(self.sol_azimute, Unset):
            sol_azimute = UNSET
        else:
            sol_azimute = self.sol_azimute

        sol_elevacao: float | None | Unset
        if isinstance(self.sol_elevacao, Unset):
            sol_elevacao = UNSET
        else:
            sol_elevacao = self.sol_elevacao

        orbita_estado: None | str | Unset
        if isinstance(self.orbita_estado, Unset):
            orbita_estado = UNSET
        else:
            orbita_estado = self.orbita_estado

        orbita_relativa: int | None | Unset
        if isinstance(self.orbita_relativa, Unset):
            orbita_relativa = UNSET
        else:
            orbita_relativa = self.orbita_relativa

        orbita_absoluta: int | None | Unset
        if isinstance(self.orbita_absoluta, Unset):
            orbita_absoluta = UNSET
        else:
            orbita_absoluta = self.orbita_absoluta

        atribuicao: None | str | Unset
        if isinstance(self.atribuicao, Unset):
            atribuicao = UNSET
        else:
            atribuicao = self.atribuicao

        observacao: None | str | Unset
        if isinstance(self.observacao, Unset):
            observacao = UNSET
        else:
            observacao = self.observacao

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "plataforma": plataforma,
                "instrumentos": instrumentos,
                "gsd": gsd,
                "data_aquisicao": data_aquisicao,
                "fornecedor": fornecedor,
                "licenca": licenca,
                "fonte": fonte,
            }
        )
        if constelacao is not UNSET:
            field_dict["constelacao"] = constelacao
        if data_aquisicao_fim is not UNSET:
            field_dict["data_aquisicao_fim"] = data_aquisicao_fim
        if nuvem_pct is not UNSET:
            field_dict["nuvem_pct"] = nuvem_pct
        if angulo_off_nadir is not UNSET:
            field_dict["angulo_off_nadir"] = angulo_off_nadir
        if angulo_incidencia is not UNSET:
            field_dict["angulo_incidencia"] = angulo_incidencia
        if angulo_azimute is not UNSET:
            field_dict["angulo_azimute"] = angulo_azimute
        if sol_azimute is not UNSET:
            field_dict["sol_azimute"] = sol_azimute
        if sol_elevacao is not UNSET:
            field_dict["sol_elevacao"] = sol_elevacao
        if orbita_estado is not UNSET:
            field_dict["orbita_estado"] = orbita_estado
        if orbita_relativa is not UNSET:
            field_dict["orbita_relativa"] = orbita_relativa
        if orbita_absoluta is not UNSET:
            field_dict["orbita_absoluta"] = orbita_absoluta
        if atribuicao is not UNSET:
            field_dict["atribuicao"] = atribuicao
        if observacao is not UNSET:
            field_dict["observacao"] = observacao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        plataforma = d.pop("plataforma")

        instrumentos = cast(list[str], d.pop("instrumentos"))

        gsd = d.pop("gsd")

        data_aquisicao = d.pop("data_aquisicao")

        fornecedor = d.pop("fornecedor")

        licenca = d.pop("licenca")

        fonte = d.pop("fonte")

        def _parse_constelacao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        constelacao = _parse_constelacao(d.pop("constelacao", UNSET))

        def _parse_data_aquisicao_fim(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        data_aquisicao_fim = _parse_data_aquisicao_fim(d.pop("data_aquisicao_fim", UNSET))

        def _parse_nuvem_pct(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        nuvem_pct = _parse_nuvem_pct(d.pop("nuvem_pct", UNSET))

        def _parse_angulo_off_nadir(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        angulo_off_nadir = _parse_angulo_off_nadir(d.pop("angulo_off_nadir", UNSET))

        def _parse_angulo_incidencia(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        angulo_incidencia = _parse_angulo_incidencia(d.pop("angulo_incidencia", UNSET))

        def _parse_angulo_azimute(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        angulo_azimute = _parse_angulo_azimute(d.pop("angulo_azimute", UNSET))

        def _parse_sol_azimute(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        sol_azimute = _parse_sol_azimute(d.pop("sol_azimute", UNSET))

        def _parse_sol_elevacao(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        sol_elevacao = _parse_sol_elevacao(d.pop("sol_elevacao", UNSET))

        def _parse_orbita_estado(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        orbita_estado = _parse_orbita_estado(d.pop("orbita_estado", UNSET))

        def _parse_orbita_relativa(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        orbita_relativa = _parse_orbita_relativa(d.pop("orbita_relativa", UNSET))

        def _parse_orbita_absoluta(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        orbita_absoluta = _parse_orbita_absoluta(d.pop("orbita_absoluta", UNSET))

        def _parse_atribuicao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        atribuicao = _parse_atribuicao(d.pop("atribuicao", UNSET))

        def _parse_observacao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        observacao = _parse_observacao(d.pop("observacao", UNSET))

        ficha_entrada = cls(
            plataforma=plataforma,
            instrumentos=instrumentos,
            gsd=gsd,
            data_aquisicao=data_aquisicao,
            fornecedor=fornecedor,
            licenca=licenca,
            fonte=fonte,
            constelacao=constelacao,
            data_aquisicao_fim=data_aquisicao_fim,
            nuvem_pct=nuvem_pct,
            angulo_off_nadir=angulo_off_nadir,
            angulo_incidencia=angulo_incidencia,
            angulo_azimute=angulo_azimute,
            sol_azimute=sol_azimute,
            sol_elevacao=sol_elevacao,
            orbita_estado=orbita_estado,
            orbita_relativa=orbita_relativa,
            orbita_absoluta=orbita_absoluta,
            atribuicao=atribuicao,
            observacao=observacao,
        )

        return ficha_entrada
