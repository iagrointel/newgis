from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.modelo_entrada_amc_definicao import ModeloEntradaAmcDefinicao


T = TypeVar("T", bound="ModeloEntradaAmc")


@_attrs_define
class ModeloEntradaAmc:
    """
    Attributes:
        definicao (ModeloEntradaAmcDefinicao):
        nome (None | str | Unset):
    """

    definicao: ModeloEntradaAmcDefinicao
    nome: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        definicao = self.definicao.to_dict()

        nome: None | str | Unset
        if isinstance(self.nome, Unset):
            nome = UNSET
        else:
            nome = self.nome

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "definicao": definicao,
            }
        )
        if nome is not UNSET:
            field_dict["nome"] = nome

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.modelo_entrada_amc_definicao import ModeloEntradaAmcDefinicao  # noqa: PLC0415

        d = dict(src_dict)
        definicao = ModeloEntradaAmcDefinicao.from_dict(d.pop("definicao"))

        def _parse_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome = _parse_nome(d.pop("nome", UNSET))

        modelo_entrada_amc = cls(
            definicao=definicao,
            nome=nome,
        )

        modelo_entrada_amc.additional_properties = d
        return modelo_entrada_amc

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
