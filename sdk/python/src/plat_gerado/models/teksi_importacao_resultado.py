from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.teksi_importacao_resultado_avisos_item import TeksiImportacaoResultadoAvisosItem
    from ..models.teksi_importacao_resultado_contagens import TeksiImportacaoResultadoContagens
    from ..models.teksi_importacao_resultado_gravadas import TeksiImportacaoResultadoGravadas
    from ..models.teksi_importacao_resultado_recusadas_item import TeksiImportacaoResultadoRecusadasItem


T = TypeVar("T", bound="TeksiImportacaoResultado")


@_attrs_define
class TeksiImportacaoResultado:
    """
    Attributes:
        rede_id (str):
        sha256 (str):
        bytes_ (int):
        contagens (TeksiImportacaoResultadoContagens):
        gravadas (TeksiImportacaoResultadoGravadas):
        recusadas (list[TeksiImportacaoResultadoRecusadasItem]):
        avisos (list[TeksiImportacaoResultadoAvisosItem]):
    """

    rede_id: str
    sha256: str
    bytes_: int
    contagens: TeksiImportacaoResultadoContagens
    gravadas: TeksiImportacaoResultadoGravadas
    recusadas: list[TeksiImportacaoResultadoRecusadasItem]
    avisos: list[TeksiImportacaoResultadoAvisosItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rede_id = self.rede_id

        sha256 = self.sha256

        bytes_ = self.bytes_

        contagens = self.contagens.to_dict()

        gravadas = self.gravadas.to_dict()

        recusadas = []
        for recusadas_item_data in self.recusadas:
            recusadas_item = recusadas_item_data.to_dict()
            recusadas.append(recusadas_item)

        avisos = []
        for avisos_item_data in self.avisos:
            avisos_item = avisos_item_data.to_dict()
            avisos.append(avisos_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rede_id": rede_id,
                "sha256": sha256,
                "bytes": bytes_,
                "contagens": contagens,
                "gravadas": gravadas,
                "recusadas": recusadas,
                "avisos": avisos,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.teksi_importacao_resultado_avisos_item import TeksiImportacaoResultadoAvisosItem  # noqa: PLC0415
        from ..models.teksi_importacao_resultado_contagens import TeksiImportacaoResultadoContagens  # noqa: PLC0415
        from ..models.teksi_importacao_resultado_gravadas import TeksiImportacaoResultadoGravadas  # noqa: PLC0415
        from ..models.teksi_importacao_resultado_recusadas_item import (
            TeksiImportacaoResultadoRecusadasItem,  # noqa: PLC0415
        )

        d = dict(src_dict)
        rede_id = d.pop("rede_id")

        sha256 = d.pop("sha256")

        bytes_ = d.pop("bytes")

        contagens = TeksiImportacaoResultadoContagens.from_dict(d.pop("contagens"))

        gravadas = TeksiImportacaoResultadoGravadas.from_dict(d.pop("gravadas"))

        recusadas = []
        _recusadas = d.pop("recusadas")
        for recusadas_item_data in _recusadas:
            recusadas_item = TeksiImportacaoResultadoRecusadasItem.from_dict(recusadas_item_data)

            recusadas.append(recusadas_item)

        avisos = []
        _avisos = d.pop("avisos")
        for avisos_item_data in _avisos:
            avisos_item = TeksiImportacaoResultadoAvisosItem.from_dict(avisos_item_data)

            avisos.append(avisos_item)

        teksi_importacao_resultado = cls(
            rede_id=rede_id,
            sha256=sha256,
            bytes_=bytes_,
            contagens=contagens,
            gravadas=gravadas,
            recusadas=recusadas,
            avisos=avisos,
        )

        teksi_importacao_resultado.additional_properties = d
        return teksi_importacao_resultado

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
