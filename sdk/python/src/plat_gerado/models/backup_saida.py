from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="BackupSaida")


@_attrs_define
class BackupSaida:
    """
    Attributes:
        id (int):
        job_id (None | str):
        esquema (str):
        sha256 (str):
        bytes_ (int):
        tabelas (int):
        tempo_dump_s (float):
        origem (str):
        criado_em (str):
    """

    id: int
    job_id: None | str
    esquema: str
    sha256: str
    bytes_: int
    tabelas: int
    tempo_dump_s: float
    origem: str
    criado_em: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        job_id: None | str
        job_id = self.job_id

        esquema = self.esquema

        sha256 = self.sha256

        bytes_ = self.bytes_

        tabelas = self.tabelas

        tempo_dump_s = self.tempo_dump_s

        origem = self.origem

        criado_em = self.criado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "job_id": job_id,
                "esquema": esquema,
                "sha256": sha256,
                "bytes": bytes_,
                "tabelas": tabelas,
                "tempo_dump_s": tempo_dump_s,
                "origem": origem,
                "criado_em": criado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        def _parse_job_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        job_id = _parse_job_id(d.pop("job_id"))

        esquema = d.pop("esquema")

        sha256 = d.pop("sha256")

        bytes_ = d.pop("bytes")

        tabelas = d.pop("tabelas")

        tempo_dump_s = d.pop("tempo_dump_s")

        origem = d.pop("origem")

        criado_em = d.pop("criado_em")

        backup_saida = cls(
            id=id,
            job_id=job_id,
            esquema=esquema,
            sha256=sha256,
            bytes_=bytes_,
            tabelas=tabelas,
            tempo_dump_s=tempo_dump_s,
            origem=origem,
            criado_em=criado_em,
        )

        backup_saida.additional_properties = d
        return backup_saida

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
