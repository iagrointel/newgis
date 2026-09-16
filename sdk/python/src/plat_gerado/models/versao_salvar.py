from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.versao_salvar_desenho import VersaoSalvarDesenho


T = TypeVar("T", bound="VersaoSalvar")


@_attrs_define
class VersaoSalvar:
    """
    Attributes:
        desenho (VersaoSalvarDesenho):
    """

    desenho: VersaoSalvarDesenho

    def to_dict(self) -> dict[str, Any]:
        desenho = self.desenho.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "desenho": desenho,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.versao_salvar_desenho import VersaoSalvarDesenho  # noqa: PLC0415

        d = dict(src_dict)
        desenho = VersaoSalvarDesenho.from_dict(d.pop("desenho"))

        versao_salvar = cls(
            desenho=desenho,
        )

        return versao_salvar
