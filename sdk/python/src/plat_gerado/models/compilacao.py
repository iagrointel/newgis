from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.compilacao_plat_construtor import CompilacaoPlatConstrutor


T = TypeVar("T", bound="Compilacao")


@_attrs_define
class Compilacao:
    """
    Attributes:
        plat_construtor (CompilacaoPlatConstrutor):
        id_base (str | Unset):  Default: 'camada'.
    """

    plat_construtor: CompilacaoPlatConstrutor
    id_base: str | Unset = "camada"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        plat_construtor = self.plat_construtor.to_dict()

        id_base = self.id_base

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "plat_construtor": plat_construtor,
            }
        )
        if id_base is not UNSET:
            field_dict["id_base"] = id_base

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.compilacao_plat_construtor import CompilacaoPlatConstrutor  # noqa: PLC0415

        d = dict(src_dict)
        plat_construtor = CompilacaoPlatConstrutor.from_dict(d.pop("plat_construtor"))

        id_base = d.pop("id_base", UNSET)

        compilacao = cls(
            plat_construtor=plat_construtor,
            id_base=id_base,
        )

        compilacao.additional_properties = d
        return compilacao

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
