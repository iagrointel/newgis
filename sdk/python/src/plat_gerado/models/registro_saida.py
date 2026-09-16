from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.servico_saida import ServicoSaida


T = TypeVar("T", bound="RegistroSaida")


@_attrs_define
class RegistroSaida:
    """
    Attributes:
        palavras_chave (list[str]):
        restricoes (list[str]):
        servicos (list[ServicoSaida]):
        sem_servico (bool):
        avisos (list[str]):
        identificador (None | str | Unset):
        titulo (None | str | Unset):
        resumo (None | str | Unset):
        organizacao (None | str | Unset):
        data_do_dado (None | str | Unset):
        data_metadado (None | str | Unset):
        bbox (list[float] | None | Unset):
        licenca (None | str | Unset):
        frequencia (None | str | Unset):
    """

    palavras_chave: list[str]
    restricoes: list[str]
    servicos: list[ServicoSaida]
    sem_servico: bool
    avisos: list[str]
    identificador: None | str | Unset = UNSET
    titulo: None | str | Unset = UNSET
    resumo: None | str | Unset = UNSET
    organizacao: None | str | Unset = UNSET
    data_do_dado: None | str | Unset = UNSET
    data_metadado: None | str | Unset = UNSET
    bbox: list[float] | None | Unset = UNSET
    licenca: None | str | Unset = UNSET
    frequencia: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        palavras_chave = self.palavras_chave

        restricoes = self.restricoes

        servicos = []
        for servicos_item_data in self.servicos:
            servicos_item = servicos_item_data.to_dict()
            servicos.append(servicos_item)

        sem_servico = self.sem_servico

        avisos = self.avisos

        identificador: None | str | Unset
        if isinstance(self.identificador, Unset):
            identificador = UNSET
        else:
            identificador = self.identificador

        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        resumo: None | str | Unset
        if isinstance(self.resumo, Unset):
            resumo = UNSET
        else:
            resumo = self.resumo

        organizacao: None | str | Unset
        if isinstance(self.organizacao, Unset):
            organizacao = UNSET
        else:
            organizacao = self.organizacao

        data_do_dado: None | str | Unset
        if isinstance(self.data_do_dado, Unset):
            data_do_dado = UNSET
        else:
            data_do_dado = self.data_do_dado

        data_metadado: None | str | Unset
        if isinstance(self.data_metadado, Unset):
            data_metadado = UNSET
        else:
            data_metadado = self.data_metadado

        bbox: list[float] | None | Unset
        if isinstance(self.bbox, Unset):
            bbox = UNSET
        elif isinstance(self.bbox, list):
            bbox = self.bbox

        else:
            bbox = self.bbox

        licenca: None | str | Unset
        if isinstance(self.licenca, Unset):
            licenca = UNSET
        else:
            licenca = self.licenca

        frequencia: None | str | Unset
        if isinstance(self.frequencia, Unset):
            frequencia = UNSET
        else:
            frequencia = self.frequencia

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "palavras_chave": palavras_chave,
                "restricoes": restricoes,
                "servicos": servicos,
                "sem_servico": sem_servico,
                "avisos": avisos,
            }
        )
        if identificador is not UNSET:
            field_dict["identificador"] = identificador
        if titulo is not UNSET:
            field_dict["titulo"] = titulo
        if resumo is not UNSET:
            field_dict["resumo"] = resumo
        if organizacao is not UNSET:
            field_dict["organizacao"] = organizacao
        if data_do_dado is not UNSET:
            field_dict["data_do_dado"] = data_do_dado
        if data_metadado is not UNSET:
            field_dict["data_metadado"] = data_metadado
        if bbox is not UNSET:
            field_dict["bbox"] = bbox
        if licenca is not UNSET:
            field_dict["licenca"] = licenca
        if frequencia is not UNSET:
            field_dict["frequencia"] = frequencia

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.servico_saida import ServicoSaida  # noqa: PLC0415

        d = dict(src_dict)
        palavras_chave = cast(list[str], d.pop("palavras_chave"))

        restricoes = cast(list[str], d.pop("restricoes"))

        servicos = []
        _servicos = d.pop("servicos")
        for servicos_item_data in _servicos:
            servicos_item = ServicoSaida.from_dict(servicos_item_data)

            servicos.append(servicos_item)

        sem_servico = d.pop("sem_servico")

        avisos = cast(list[str], d.pop("avisos"))

        def _parse_identificador(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        identificador = _parse_identificador(d.pop("identificador", UNSET))

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        def _parse_resumo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resumo = _parse_resumo(d.pop("resumo", UNSET))

        def _parse_organizacao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        organizacao = _parse_organizacao(d.pop("organizacao", UNSET))

        def _parse_data_do_dado(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        data_do_dado = _parse_data_do_dado(d.pop("data_do_dado", UNSET))

        def _parse_data_metadado(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        data_metadado = _parse_data_metadado(d.pop("data_metadado", UNSET))

        def _parse_bbox(data: object) -> list[float] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                bbox_type_0 = cast(list[float], data)

                return bbox_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[float] | None | Unset, data)

        bbox = _parse_bbox(d.pop("bbox", UNSET))

        def _parse_licenca(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        licenca = _parse_licenca(d.pop("licenca", UNSET))

        def _parse_frequencia(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        frequencia = _parse_frequencia(d.pop("frequencia", UNSET))

        registro_saida = cls(
            palavras_chave=palavras_chave,
            restricoes=restricoes,
            servicos=servicos,
            sem_servico=sem_servico,
            avisos=avisos,
            identificador=identificador,
            titulo=titulo,
            resumo=resumo,
            organizacao=organizacao,
            data_do_dado=data_do_dado,
            data_metadado=data_metadado,
            bbox=bbox,
            licenca=licenca,
            frequencia=frequencia,
        )

        registro_saida.additional_properties = d
        return registro_saida

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
