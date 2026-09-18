from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="PontoUso")


@_attrs_define
class PontoUso:
    """
    Attributes:
        dia (str):
        bytes_banco (int):
        bytes_bucket (int):
        bytes_total (int):
        itens (int):
        itens_lixeira (int):
        usuarios_total (int):
        usuarios_ativos_30d (int):
        jobs (int):
        job_tempo_ms (int):
        requisicoes (int):
        bytes_servidos (int):
        medido_em (None | str):
    """

    dia: str
    bytes_banco: int
    bytes_bucket: int
    bytes_total: int
    itens: int
    itens_lixeira: int
    usuarios_total: int
    usuarios_ativos_30d: int
    jobs: int
    job_tempo_ms: int
    requisicoes: int
    bytes_servidos: int
    medido_em: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        dia = self.dia

        bytes_banco = self.bytes_banco

        bytes_bucket = self.bytes_bucket

        bytes_total = self.bytes_total

        itens = self.itens

        itens_lixeira = self.itens_lixeira

        usuarios_total = self.usuarios_total

        usuarios_ativos_30d = self.usuarios_ativos_30d

        jobs = self.jobs

        job_tempo_ms = self.job_tempo_ms

        requisicoes = self.requisicoes

        bytes_servidos = self.bytes_servidos

        medido_em: None | str
        medido_em = self.medido_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "dia": dia,
                "bytes_banco": bytes_banco,
                "bytes_bucket": bytes_bucket,
                "bytes_total": bytes_total,
                "itens": itens,
                "itens_lixeira": itens_lixeira,
                "usuarios_total": usuarios_total,
                "usuarios_ativos_30d": usuarios_ativos_30d,
                "jobs": jobs,
                "job_tempo_ms": job_tempo_ms,
                "requisicoes": requisicoes,
                "bytes_servidos": bytes_servidos,
                "medido_em": medido_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        dia = d.pop("dia")

        bytes_banco = d.pop("bytes_banco")

        bytes_bucket = d.pop("bytes_bucket")

        bytes_total = d.pop("bytes_total")

        itens = d.pop("itens")

        itens_lixeira = d.pop("itens_lixeira")

        usuarios_total = d.pop("usuarios_total")

        usuarios_ativos_30d = d.pop("usuarios_ativos_30d")

        jobs = d.pop("jobs")

        job_tempo_ms = d.pop("job_tempo_ms")

        requisicoes = d.pop("requisicoes")

        bytes_servidos = d.pop("bytes_servidos")

        def _parse_medido_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        medido_em = _parse_medido_em(d.pop("medido_em"))

        ponto_uso = cls(
            dia=dia,
            bytes_banco=bytes_banco,
            bytes_bucket=bytes_bucket,
            bytes_total=bytes_total,
            itens=itens,
            itens_lixeira=itens_lixeira,
            usuarios_total=usuarios_total,
            usuarios_ativos_30d=usuarios_ativos_30d,
            jobs=jobs,
            job_tempo_ms=job_tempo_ms,
            requisicoes=requisicoes,
            bytes_servidos=bytes_servidos,
            medido_em=medido_em,
        )

        ponto_uso.additional_properties = d
        return ponto_uso

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
