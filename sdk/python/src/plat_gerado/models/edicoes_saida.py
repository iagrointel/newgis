from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.resultado_feicao import ResultadoFeicao


T = TypeVar("T", bound="EdicoesSaida")


@_attrs_define
class EdicoesSaida:
    """
    Attributes:
        modo (str):
        adicionar (list[ResultadoFeicao]):
        atualizar (list[ResultadoFeicao]):
        apagar (list[ResultadoFeicao]):
        avisos (list[str] | Unset):
    """

    modo: str
    adicionar: list[ResultadoFeicao]
    atualizar: list[ResultadoFeicao]
    apagar: list[ResultadoFeicao]
    avisos: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        modo = self.modo

        adicionar = []
        for adicionar_item_data in self.adicionar:
            adicionar_item = adicionar_item_data.to_dict()
            adicionar.append(adicionar_item)

        atualizar = []
        for atualizar_item_data in self.atualizar:
            atualizar_item = atualizar_item_data.to_dict()
            atualizar.append(atualizar_item)

        apagar = []
        for apagar_item_data in self.apagar:
            apagar_item = apagar_item_data.to_dict()
            apagar.append(apagar_item)

        avisos: list[str] | Unset = UNSET
        if not isinstance(self.avisos, Unset):
            avisos = self.avisos

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "modo": modo,
                "adicionar": adicionar,
                "atualizar": atualizar,
                "apagar": apagar,
            }
        )
        if avisos is not UNSET:
            field_dict["avisos"] = avisos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.resultado_feicao import ResultadoFeicao  # noqa: PLC0415

        d = dict(src_dict)
        modo = d.pop("modo")

        adicionar = []
        _adicionar = d.pop("adicionar")
        for adicionar_item_data in _adicionar:
            adicionar_item = ResultadoFeicao.from_dict(adicionar_item_data)

            adicionar.append(adicionar_item)

        atualizar = []
        _atualizar = d.pop("atualizar")
        for atualizar_item_data in _atualizar:
            atualizar_item = ResultadoFeicao.from_dict(atualizar_item_data)

            atualizar.append(atualizar_item)

        apagar = []
        _apagar = d.pop("apagar")
        for apagar_item_data in _apagar:
            apagar_item = ResultadoFeicao.from_dict(apagar_item_data)

            apagar.append(apagar_item)

        avisos = cast(list[str], d.pop("avisos", UNSET))

        edicoes_saida = cls(
            modo=modo,
            adicionar=adicionar,
            atualizar=atualizar,
            apagar=apagar,
            avisos=avisos,
        )

        edicoes_saida.additional_properties = d
        return edicoes_saida

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
