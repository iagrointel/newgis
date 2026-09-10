from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.tipo_job_parametros_schema import TipoJobParametrosSchema


T = TypeVar("T", bound="TipoJob")


@_attrs_define
class TipoJob:
    """
    Attributes:
        nome (str):
        descricao (str):
        pesado (bool):
        memoria_mb (int):
        timeout_s (int):
        tentativas (int):
        executor (str):
        versao (int):
        perfil_minimo (str):
        parametros_schema (TipoJobParametrosSchema):
    """

    nome: str
    descricao: str
    pesado: bool
    memoria_mb: int
    timeout_s: int
    tentativas: int
    executor: str
    versao: int
    perfil_minimo: str
    parametros_schema: TipoJobParametrosSchema
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        descricao = self.descricao

        pesado = self.pesado

        memoria_mb = self.memoria_mb

        timeout_s = self.timeout_s

        tentativas = self.tentativas

        executor = self.executor

        versao = self.versao

        perfil_minimo = self.perfil_minimo

        parametros_schema = self.parametros_schema.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nome": nome,
                "descricao": descricao,
                "pesado": pesado,
                "memoria_mb": memoria_mb,
                "timeout_s": timeout_s,
                "tentativas": tentativas,
                "executor": executor,
                "versao": versao,
                "perfil_minimo": perfil_minimo,
                "parametros_schema": parametros_schema,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tipo_job_parametros_schema import TipoJobParametrosSchema  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        descricao = d.pop("descricao")

        pesado = d.pop("pesado")

        memoria_mb = d.pop("memoria_mb")

        timeout_s = d.pop("timeout_s")

        tentativas = d.pop("tentativas")

        executor = d.pop("executor")

        versao = d.pop("versao")

        perfil_minimo = d.pop("perfil_minimo")

        parametros_schema = TipoJobParametrosSchema.from_dict(d.pop("parametros_schema"))

        tipo_job = cls(
            nome=nome,
            descricao=descricao,
            pesado=pesado,
            memoria_mb=memoria_mb,
            timeout_s=timeout_s,
            tentativas=tentativas,
            executor=executor,
            versao=versao,
            perfil_minimo=perfil_minimo,
            parametros_schema=parametros_schema,
        )

        tipo_job.additional_properties = d
        return tipo_job

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
