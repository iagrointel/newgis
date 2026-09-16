from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.salvar_item_entrada import SalvarItemEntrada
    from ..models.terreno import Terreno


T = TypeVar("T", bound="VisadaEntrada")


@_attrs_define
class VisadaEntrada:
    """
    Attributes:
        terreno (Terreno): Grade de alturas do terreno, em SRID projetado (metros).
        observador (list[float]):
        alvo (list[float]):
        altura_observador_m (float | Unset): altura do observador SOBRE o terreno; negativa = abaixo (422) Default: 2.0.
        altura_alvo_m (float | Unset):  Default: 0.0.
        passo_m (float | None | Unset): passo máximo da amostragem; padrão = metade da célula
        salvar_item (None | SalvarItemEntrada | Unset):
    """

    terreno: Terreno
    observador: list[float]
    alvo: list[float]
    altura_observador_m: float | Unset = 2.0
    altura_alvo_m: float | Unset = 0.0
    passo_m: float | None | Unset = UNSET
    salvar_item: None | SalvarItemEntrada | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.salvar_item_entrada import SalvarItemEntrada  # noqa: PLC0415

        terreno = self.terreno.to_dict()

        observador = []
        for observador_item_data in self.observador:
            observador_item: float
            observador_item = observador_item_data
            observador.append(observador_item)

        alvo = []
        for alvo_item_data in self.alvo:
            alvo_item: float
            alvo_item = alvo_item_data
            alvo.append(alvo_item)

        altura_observador_m = self.altura_observador_m

        altura_alvo_m = self.altura_alvo_m

        passo_m: float | None | Unset
        if isinstance(self.passo_m, Unset):
            passo_m = UNSET
        else:
            passo_m = self.passo_m

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
                "observador": observador,
                "alvo": alvo,
            }
        )
        if altura_observador_m is not UNSET:
            field_dict["altura_observador_m"] = altura_observador_m
        if altura_alvo_m is not UNSET:
            field_dict["altura_alvo_m"] = altura_alvo_m
        if passo_m is not UNSET:
            field_dict["passo_m"] = passo_m
        if salvar_item is not UNSET:
            field_dict["salvar_item"] = salvar_item

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.salvar_item_entrada import SalvarItemEntrada  # noqa: PLC0415
        from ..models.terreno import Terreno  # noqa: PLC0415

        d = dict(src_dict)
        terreno = Terreno.from_dict(d.pop("terreno"))

        observador = []
        _observador = d.pop("observador")
        for observador_item_data in _observador:

            def _parse_observador_item(data: object) -> float:
                return cast(float, data)

            observador_item = _parse_observador_item(observador_item_data)

            observador.append(observador_item)

        alvo = []
        _alvo = d.pop("alvo")
        for alvo_item_data in _alvo:

            def _parse_alvo_item(data: object) -> float:
                return cast(float, data)

            alvo_item = _parse_alvo_item(alvo_item_data)

            alvo.append(alvo_item)

        altura_observador_m = d.pop("altura_observador_m", UNSET)

        altura_alvo_m = d.pop("altura_alvo_m", UNSET)

        def _parse_passo_m(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        passo_m = _parse_passo_m(d.pop("passo_m", UNSET))

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

        visada_entrada = cls(
            terreno=terreno,
            observador=observador,
            alvo=alvo,
            altura_observador_m=altura_observador_m,
            altura_alvo_m=altura_alvo_m,
            passo_m=passo_m,
            salvar_item=salvar_item,
        )

        return visada_entrada
