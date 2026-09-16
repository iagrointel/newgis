from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.pedido_similaridade_metrica import PedidoSimilaridadeMetrica
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.pedido_similaridade_unidades import PedidoSimilaridadeUnidades


T = TypeVar("T", bound="PedidoSimilaridade")


@_attrs_define
class PedidoSimilaridade:
    """
    Attributes:
        unidades (PedidoSimilaridadeUnidades): {unidade_id: {campo: valor|null}} — a matriz fator×unidade já extraída
            (execução do motor AMC, upload, ou qualquer outra fonte).
        referencias (list[str]): ids de unidade que 'deram certo' (1-N).
        campos (list[str] | None | Unset): subconjunto de fatores a comparar (escolha de campos); omitido = todos os
            vistos.
        metrica (PedidoSimilaridadeMetrica | Unset):  Default: PedidoSimilaridadeMetrica.COSSENO.
    """

    unidades: PedidoSimilaridadeUnidades
    referencias: list[str]
    campos: list[str] | None | Unset = UNSET
    metrica: PedidoSimilaridadeMetrica | Unset = PedidoSimilaridadeMetrica.COSSENO
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        unidades = self.unidades.to_dict()

        referencias = self.referencias

        campos: list[str] | None | Unset
        if isinstance(self.campos, Unset):
            campos = UNSET
        elif isinstance(self.campos, list):
            campos = self.campos

        else:
            campos = self.campos

        metrica: str | Unset = UNSET
        if not isinstance(self.metrica, Unset):
            metrica = self.metrica.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "unidades": unidades,
                "referencias": referencias,
            }
        )
        if campos is not UNSET:
            field_dict["campos"] = campos
        if metrica is not UNSET:
            field_dict["metrica"] = metrica

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pedido_similaridade_unidades import PedidoSimilaridadeUnidades  # noqa: PLC0415

        d = dict(src_dict)
        unidades = PedidoSimilaridadeUnidades.from_dict(d.pop("unidades"))

        referencias = cast(list[str], d.pop("referencias"))

        def _parse_campos(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                campos_type_0 = cast(list[str], data)

                return campos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        campos = _parse_campos(d.pop("campos", UNSET))

        _metrica = d.pop("metrica", UNSET)
        metrica: PedidoSimilaridadeMetrica | Unset
        if isinstance(_metrica, Unset):
            metrica = UNSET
        else:
            metrica = PedidoSimilaridadeMetrica(_metrica)

        pedido_similaridade = cls(
            unidades=unidades,
            referencias=referencias,
            campos=campos,
            metrica=metrica,
        )

        pedido_similaridade.additional_properties = d
        return pedido_similaridade

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
