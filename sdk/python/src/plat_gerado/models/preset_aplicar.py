from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

T = TypeVar("T", bound="PresetAplicar")


@_attrs_define
class PresetAplicar:
    """Matriz de fatores (unidade × fator, escala 0-100, `null` = sem dado) na ordem de
    `ids_fatores`. Tudo que é escolha do modelo (peso, veto, combinador, política) vem do PRESET —
    a chamada só traz dado.

        Attributes:
            fatores (list[list[Any]]):
            ids_fatores (list[str]):
    """

    fatores: list[list[Any]]
    ids_fatores: list[str]

    def to_dict(self) -> dict[str, Any]:
        fatores = []
        for fatores_item_data in self.fatores:
            fatores_item = fatores_item_data

            fatores.append(fatores_item)

        ids_fatores = self.ids_fatores

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "fatores": fatores,
                "ids_fatores": ids_fatores,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        fatores = []
        _fatores = d.pop("fatores")
        for fatores_item_data in _fatores:
            fatores_item = cast(list[Any], fatores_item_data)

            fatores.append(fatores_item)

        ids_fatores = cast(list[str], d.pop("ids_fatores"))

        preset_aplicar = cls(
            fatores=fatores,
            ids_fatores=ids_fatores,
        )

        return preset_aplicar
