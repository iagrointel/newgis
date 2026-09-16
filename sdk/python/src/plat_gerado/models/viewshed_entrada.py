from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.viewshed_entrada_modo import ViewshedEntradaModo
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.salvar_item_entrada import SalvarItemEntrada
    from ..models.terreno import Terreno


T = TypeVar("T", bound="ViewshedEntrada")


@_attrs_define
class ViewshedEntrada:
    """
    Attributes:
        terreno (Terreno): Grade de alturas do terreno, em SRID projetado (metros).
        observador (list[float]):
        altura_observador_m (float | Unset):  Default: 2.0.
        altura_alvo_m (float | Unset): altura do objeto a ver (gdal_viewshed -tz) Default: 0.0.
        distancia_max_m (float | None | Unset): gdal_viewshed -md; o raster sai recortado à janela
        coef_curvatura (float | Unset): gdal_viewshed -cc; 0.85714 = refração atmosférica padrão Default: 0.85714.
        modo (ViewshedEntradaModo | Unset):  Default: ViewshedEntradaModo.NORMAL.
        visivel_valor (int | Unset):  Default: 255.
        invisivel_valor (int | Unset):  Default: 128.
        fora_de_alcance_valor (int | Unset):  Default: 0.
        salvar_item (None | SalvarItemEntrada | Unset):
    """

    terreno: Terreno
    observador: list[float]
    altura_observador_m: float | Unset = 2.0
    altura_alvo_m: float | Unset = 0.0
    distancia_max_m: float | None | Unset = UNSET
    coef_curvatura: float | Unset = 0.85714
    modo: ViewshedEntradaModo | Unset = ViewshedEntradaModo.NORMAL
    visivel_valor: int | Unset = 255
    invisivel_valor: int | Unset = 128
    fora_de_alcance_valor: int | Unset = 0
    salvar_item: None | SalvarItemEntrada | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.salvar_item_entrada import SalvarItemEntrada  # noqa: PLC0415

        terreno = self.terreno.to_dict()

        observador = []
        for observador_item_data in self.observador:
            observador_item: float
            observador_item = observador_item_data
            observador.append(observador_item)

        altura_observador_m = self.altura_observador_m

        altura_alvo_m = self.altura_alvo_m

        distancia_max_m: float | None | Unset
        if isinstance(self.distancia_max_m, Unset):
            distancia_max_m = UNSET
        else:
            distancia_max_m = self.distancia_max_m

        coef_curvatura = self.coef_curvatura

        modo: str | Unset = UNSET
        if not isinstance(self.modo, Unset):
            modo = self.modo.value

        visivel_valor = self.visivel_valor

        invisivel_valor = self.invisivel_valor

        fora_de_alcance_valor = self.fora_de_alcance_valor

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
            }
        )
        if altura_observador_m is not UNSET:
            field_dict["altura_observador_m"] = altura_observador_m
        if altura_alvo_m is not UNSET:
            field_dict["altura_alvo_m"] = altura_alvo_m
        if distancia_max_m is not UNSET:
            field_dict["distancia_max_m"] = distancia_max_m
        if coef_curvatura is not UNSET:
            field_dict["coef_curvatura"] = coef_curvatura
        if modo is not UNSET:
            field_dict["modo"] = modo
        if visivel_valor is not UNSET:
            field_dict["visivel_valor"] = visivel_valor
        if invisivel_valor is not UNSET:
            field_dict["invisivel_valor"] = invisivel_valor
        if fora_de_alcance_valor is not UNSET:
            field_dict["fora_de_alcance_valor"] = fora_de_alcance_valor
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

        altura_observador_m = d.pop("altura_observador_m", UNSET)

        altura_alvo_m = d.pop("altura_alvo_m", UNSET)

        def _parse_distancia_max_m(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        distancia_max_m = _parse_distancia_max_m(d.pop("distancia_max_m", UNSET))

        coef_curvatura = d.pop("coef_curvatura", UNSET)

        _modo = d.pop("modo", UNSET)
        modo: ViewshedEntradaModo | Unset
        if isinstance(_modo, Unset):
            modo = UNSET
        else:
            modo = ViewshedEntradaModo(_modo)

        visivel_valor = d.pop("visivel_valor", UNSET)

        invisivel_valor = d.pop("invisivel_valor", UNSET)

        fora_de_alcance_valor = d.pop("fora_de_alcance_valor", UNSET)

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

        viewshed_entrada = cls(
            terreno=terreno,
            observador=observador,
            altura_observador_m=altura_observador_m,
            altura_alvo_m=altura_alvo_m,
            distancia_max_m=distancia_max_m,
            coef_curvatura=coef_curvatura,
            modo=modo,
            visivel_valor=visivel_valor,
            invisivel_valor=invisivel_valor,
            fora_de_alcance_valor=fora_de_alcance_valor,
            salvar_item=salvar_item,
        )

        return viewshed_entrada
