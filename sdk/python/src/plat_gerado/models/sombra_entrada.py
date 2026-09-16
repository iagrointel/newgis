from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.salvar_item_entrada import SalvarItemEntrada
    from ..models.solido_entrada import SolidoEntrada


T = TypeVar("T", bound="SombraEntrada")


@_attrs_define
class SombraEntrada:
    """
    Attributes:
        srid (int): SIRGAS 2000 UTM sul (31965-31985), a mesma faixa do terreno
        data_hora (str): instante ISO 8601 com fuso (ex.: 2026-12-21T12:00:00-03:00)
        solidos (list[SolidoEntrada]):
        salvar_item (None | SalvarItemEntrada | Unset):
    """

    srid: int
    data_hora: str
    solidos: list[SolidoEntrada]
    salvar_item: None | SalvarItemEntrada | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.salvar_item_entrada import SalvarItemEntrada  # noqa: PLC0415

        srid = self.srid

        data_hora = self.data_hora

        solidos = []
        for solidos_item_data in self.solidos:
            solidos_item = solidos_item_data.to_dict()
            solidos.append(solidos_item)

        salvar_item: dict[str, Any] | None | Unset
        if isinstance(self.salvar_item, Unset):
            salvar_item = UNSET
        elif isinstance(self.salvar_item, SalvarItemEntrada):
            salvar_item = self.salvar_item.to_dict()
        else:
            salvar_item = self.salvar_item

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "srid": srid,
                "data_hora": data_hora,
                "solidos": solidos,
            }
        )
        if salvar_item is not UNSET:
            field_dict["salvar_item"] = salvar_item

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.salvar_item_entrada import SalvarItemEntrada  # noqa: PLC0415
        from ..models.solido_entrada import SolidoEntrada  # noqa: PLC0415

        d = dict(src_dict)
        srid = d.pop("srid")

        data_hora = d.pop("data_hora")

        solidos = []
        _solidos = d.pop("solidos")
        for solidos_item_data in _solidos:
            solidos_item = SolidoEntrada.from_dict(solidos_item_data)

            solidos.append(solidos_item)

        def _parse_salvar_item(data: object) -> None | SalvarItemEntrada | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                salvar_item_type_0 = SalvarItemEntrada.from_dict(data)

                return salvar_item_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SalvarItemEntrada | Unset, data)

        salvar_item = _parse_salvar_item(d.pop("salvar_item", UNSET))

        sombra_entrada = cls(
            srid=srid,
            data_hora=data_hora,
            solidos=solidos,
            salvar_item=salvar_item,
        )

        return sombra_entrada
