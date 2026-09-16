from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.importacao_resultado_contagens import ImportacaoResultadoContagens


T = TypeVar("T", bound="ImportacaoResultado")


@_attrs_define
class ImportacaoResultado:
    """
    Attributes:
        rede_id (str):
        codigo (str):
        versao (str):
        esquema_versao (int):
        sha256 (str):
        bytes_ (int):
        contagens (ImportacaoResultadoContagens):
    """

    rede_id: str
    codigo: str
    versao: str
    esquema_versao: int
    sha256: str
    bytes_: int
    contagens: ImportacaoResultadoContagens
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rede_id = self.rede_id

        codigo = self.codigo

        versao = self.versao

        esquema_versao = self.esquema_versao

        sha256 = self.sha256

        bytes_ = self.bytes_

        contagens = self.contagens.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rede_id": rede_id,
                "codigo": codigo,
                "versao": versao,
                "esquema_versao": esquema_versao,
                "sha256": sha256,
                "bytes": bytes_,
                "contagens": contagens,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.importacao_resultado_contagens import ImportacaoResultadoContagens  # noqa: PLC0415

        d = dict(src_dict)
        rede_id = d.pop("rede_id")

        codigo = d.pop("codigo")

        versao = d.pop("versao")

        esquema_versao = d.pop("esquema_versao")

        sha256 = d.pop("sha256")

        bytes_ = d.pop("bytes")

        contagens = ImportacaoResultadoContagens.from_dict(d.pop("contagens"))

        importacao_resultado = cls(
            rede_id=rede_id,
            codigo=codigo,
            versao=versao,
            esquema_versao=esquema_versao,
            sha256=sha256,
            bytes_=bytes_,
            contagens=contagens,
        )

        importacao_resultado.additional_properties = d
        return importacao_resultado

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
