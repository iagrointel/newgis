from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.salvar_item_entrada import SalvarItemEntrada
    from ..models.terreno import Terreno


T = TypeVar("T", bound="PerfilEntrada")


@_attrs_define
class PerfilEntrada:
    """
    Attributes:
        terreno (Terreno): Grade de alturas do terreno, em SRID projetado (metros).
        ponto_a (list[float]):
        ponto_b (list[float]):
        n_amostras (int):
        salvar_item (None | SalvarItemEntrada | Unset):
    """

    terreno: Terreno
    ponto_a: list[float]
    ponto_b: list[float]
    n_amostras: int
    salvar_item: None | SalvarItemEntrada | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.salvar_item_entrada import SalvarItemEntrada  # noqa: PLC0415

        terreno = self.terreno.to_dict()

        ponto_a = []
        for ponto_a_item_data in self.ponto_a:
            ponto_a_item: float
            ponto_a_item = ponto_a_item_data
            ponto_a.append(ponto_a_item)

        ponto_b = []
        for ponto_b_item_data in self.ponto_b:
            ponto_b_item: float
            ponto_b_item = ponto_b_item_data
            ponto_b.append(ponto_b_item)

        n_amostras = self.n_amostras

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
                "terreno": terreno,
                "ponto_a": ponto_a,
                "ponto_b": ponto_b,
                "n_amostras": n_amostras,
            }
        )
        if salvar_item is not UNSET:
            field_dict["salvar_item"] = salvar_item

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.salvar_item_entrada import SalvarItemEntrada  # noqa: PLC0415
        from ..models.terreno import Terreno  # noqa: PLC0415

        d = dict(src_dict)
        terreno = Terreno.from_dict(d.pop("terreno"))

        ponto_a = []
        _ponto_a = d.pop("ponto_a")
        for ponto_a_item_data in _ponto_a:

            def _parse_ponto_a_item(data: object) -> float:
                return cast(float, data)

            ponto_a_item = _parse_ponto_a_item(ponto_a_item_data)

            ponto_a.append(ponto_a_item)

        ponto_b = []
        _ponto_b = d.pop("ponto_b")
        for ponto_b_item_data in _ponto_b:

            def _parse_ponto_b_item(data: object) -> float:
                return cast(float, data)

            ponto_b_item = _parse_ponto_b_item(ponto_b_item_data)

            ponto_b.append(ponto_b_item)

        n_amostras = d.pop("n_amostras")

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

        perfil_entrada = cls(
            terreno=terreno,
            ponto_a=ponto_a,
            ponto_b=ponto_b,
            n_amostras=n_amostras,
            salvar_item=salvar_item,
        )

        return perfil_entrada
