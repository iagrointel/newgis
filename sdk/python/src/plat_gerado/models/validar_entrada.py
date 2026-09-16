from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.validar_entrada_definicao import ValidarEntradaDefinicao


T = TypeVar("T", bound="ValidarEntrada")


@_attrs_define
class ValidarEntrada:
    """
    Attributes:
        definicao (ValidarEntradaDefinicao):
    """

    definicao: ValidarEntradaDefinicao
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        definicao = self.definicao.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "definicao": definicao,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.validar_entrada_definicao import ValidarEntradaDefinicao  # noqa: PLC0415

        d = dict(src_dict)
        definicao = ValidarEntradaDefinicao.from_dict(d.pop("definicao"))

        validar_entrada = cls(
            definicao=definicao,
        )

        validar_entrada.additional_properties = d
        return validar_entrada

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
