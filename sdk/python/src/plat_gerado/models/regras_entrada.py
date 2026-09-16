from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.campo_virtual_entrada import CampoVirtualEntrada
    from ..models.regra_entrada import RegraEntrada


T = TypeVar("T", bound="RegrasEntrada")


@_attrs_define
class RegrasEntrada:
    """
    Attributes:
        regras (list[RegraEntrada] | Unset):
        campos_virtuais (list[CampoVirtualEntrada] | Unset):
    """

    regras: list[RegraEntrada] | Unset = UNSET
    campos_virtuais: list[CampoVirtualEntrada] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        regras: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.regras, Unset):
            regras = []
            for regras_item_data in self.regras:
                regras_item = regras_item_data.to_dict()
                regras.append(regras_item)

        campos_virtuais: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.campos_virtuais, Unset):
            campos_virtuais = []
            for campos_virtuais_item_data in self.campos_virtuais:
                campos_virtuais_item = campos_virtuais_item_data.to_dict()
                campos_virtuais.append(campos_virtuais_item)

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if regras is not UNSET:
            field_dict["regras"] = regras
        if campos_virtuais is not UNSET:
            field_dict["campos_virtuais"] = campos_virtuais

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.campo_virtual_entrada import CampoVirtualEntrada  # noqa: PLC0415
        from ..models.regra_entrada import RegraEntrada  # noqa: PLC0415

        d = dict(src_dict)
        _regras = d.pop("regras", UNSET)
        regras: list[RegraEntrada] | Unset = UNSET
        if _regras is not UNSET:
            regras = []
            for regras_item_data in _regras:
                regras_item = RegraEntrada.from_dict(regras_item_data)

                regras.append(regras_item)

        _campos_virtuais = d.pop("campos_virtuais", UNSET)
        campos_virtuais: list[CampoVirtualEntrada] | Unset = UNSET
        if _campos_virtuais is not UNSET:
            campos_virtuais = []
            for campos_virtuais_item_data in _campos_virtuais:
                campos_virtuais_item = CampoVirtualEntrada.from_dict(campos_virtuais_item_data)

                campos_virtuais.append(campos_virtuais_item)

        regras_entrada = cls(
            regras=regras,
            campos_virtuais=campos_virtuais,
        )

        return regras_entrada
