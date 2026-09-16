from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.mudanca_servidor import MudancaServidor


T = TypeVar("T", bound="CamadaBaixada")


@_attrs_define
class CamadaBaixada:
    """
    Attributes:
        camada_id (str):
        nome_gpkg (str):
        desde (int):
        ate (int):
        truncado (bool | Unset):  Default: False.
        mudancas (list[MudancaServidor] | Unset):
    """

    camada_id: str
    nome_gpkg: str
    desde: int
    ate: int
    truncado: bool | Unset = False
    mudancas: list[MudancaServidor] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        camada_id = self.camada_id

        nome_gpkg = self.nome_gpkg

        desde = self.desde

        ate = self.ate

        truncado = self.truncado

        mudancas: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.mudancas, Unset):
            mudancas = []
            for mudancas_item_data in self.mudancas:
                mudancas_item = mudancas_item_data.to_dict()
                mudancas.append(mudancas_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "camada_id": camada_id,
                "nome_gpkg": nome_gpkg,
                "desde": desde,
                "ate": ate,
            }
        )
        if truncado is not UNSET:
            field_dict["truncado"] = truncado
        if mudancas is not UNSET:
            field_dict["mudancas"] = mudancas

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mudanca_servidor import MudancaServidor  # noqa: PLC0415

        d = dict(src_dict)
        camada_id = d.pop("camada_id")

        nome_gpkg = d.pop("nome_gpkg")

        desde = d.pop("desde")

        ate = d.pop("ate")

        truncado = d.pop("truncado", UNSET)

        _mudancas = d.pop("mudancas", UNSET)
        mudancas: list[MudancaServidor] | Unset = UNSET
        if _mudancas is not UNSET:
            mudancas = []
            for mudancas_item_data in _mudancas:
                mudancas_item = MudancaServidor.from_dict(mudancas_item_data)

                mudancas.append(mudancas_item)

        camada_baixada = cls(
            camada_id=camada_id,
            nome_gpkg=nome_gpkg,
            desde=desde,
            ate=ate,
            truncado=truncado,
            mudancas=mudancas,
        )

        camada_baixada.additional_properties = d
        return camada_baixada

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
