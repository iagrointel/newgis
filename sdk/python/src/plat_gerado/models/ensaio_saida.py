from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="EnsaioSaida")


@_attrs_define
class EnsaioSaida:
    """
    Attributes:
        id (int):
        backup_id (int | None):
        job_id (None | str):
        esquema (str):
        schema_ensaio (None | str):
        tabelas (int):
        linhas (int):
        objetos_conferidos (int):
        ok (bool):
        mensagem (None | str):
        duracao_drill_s (float):
        origem (str):
        criado_em (str):
    """

    id: int
    backup_id: int | None
    job_id: None | str
    esquema: str
    schema_ensaio: None | str
    tabelas: int
    linhas: int
    objetos_conferidos: int
    ok: bool
    mensagem: None | str
    duracao_drill_s: float
    origem: str
    criado_em: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        backup_id: int | None
        backup_id = self.backup_id

        job_id: None | str
        job_id = self.job_id

        esquema = self.esquema

        schema_ensaio: None | str
        schema_ensaio = self.schema_ensaio

        tabelas = self.tabelas

        linhas = self.linhas

        objetos_conferidos = self.objetos_conferidos

        ok = self.ok

        mensagem: None | str
        mensagem = self.mensagem

        duracao_drill_s = self.duracao_drill_s

        origem = self.origem

        criado_em = self.criado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "backup_id": backup_id,
                "job_id": job_id,
                "esquema": esquema,
                "schema_ensaio": schema_ensaio,
                "tabelas": tabelas,
                "linhas": linhas,
                "objetos_conferidos": objetos_conferidos,
                "ok": ok,
                "mensagem": mensagem,
                "duracao_drill_s": duracao_drill_s,
                "origem": origem,
                "criado_em": criado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        def _parse_backup_id(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        backup_id = _parse_backup_id(d.pop("backup_id"))

        def _parse_job_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        job_id = _parse_job_id(d.pop("job_id"))

        esquema = d.pop("esquema")

        def _parse_schema_ensaio(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        schema_ensaio = _parse_schema_ensaio(d.pop("schema_ensaio"))

        tabelas = d.pop("tabelas")

        linhas = d.pop("linhas")

        objetos_conferidos = d.pop("objetos_conferidos")

        ok = d.pop("ok")

        def _parse_mensagem(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        mensagem = _parse_mensagem(d.pop("mensagem"))

        duracao_drill_s = d.pop("duracao_drill_s")

        origem = d.pop("origem")

        criado_em = d.pop("criado_em")

        ensaio_saida = cls(
            id=id,
            backup_id=backup_id,
            job_id=job_id,
            esquema=esquema,
            schema_ensaio=schema_ensaio,
            tabelas=tabelas,
            linhas=linhas,
            objetos_conferidos=objetos_conferidos,
            ok=ok,
            mensagem=mensagem,
            duracao_drill_s=duracao_drill_s,
            origem=origem,
            criado_em=criado_em,
        )

        ensaio_saida.additional_properties = d
        return ensaio_saida

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
