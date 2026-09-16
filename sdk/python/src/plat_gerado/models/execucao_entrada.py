from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..models.execucao_entrada_aprovacao_tipo import ExecucaoEntradaAprovacaoTipo

if TYPE_CHECKING:
    from ..models.fator_peso_entrada import FatorPesoEntrada


T = TypeVar("T", bound="ExecucaoEntrada")


@_attrs_define
class ExecucaoEntrada:
    """
    Attributes:
        resolucao_m (float):
        fatores (list[FatorPesoEntrada]):
        aprovacao_tipo (ExecucaoEntradaAprovacaoTipo):
        aprovacao_valor (float):
    """

    resolucao_m: float
    fatores: list[FatorPesoEntrada]
    aprovacao_tipo: ExecucaoEntradaAprovacaoTipo
    aprovacao_valor: float

    def to_dict(self) -> dict[str, Any]:
        resolucao_m = self.resolucao_m

        fatores = []
        for fatores_item_data in self.fatores:
            fatores_item = fatores_item_data.to_dict()
            fatores.append(fatores_item)

        aprovacao_tipo = self.aprovacao_tipo.value

        aprovacao_valor = self.aprovacao_valor

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "resolucao_m": resolucao_m,
                "fatores": fatores,
                "aprovacao_tipo": aprovacao_tipo,
                "aprovacao_valor": aprovacao_valor,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.fator_peso_entrada import FatorPesoEntrada  # noqa: PLC0415

        d = dict(src_dict)
        resolucao_m = d.pop("resolucao_m")

        fatores = []
        _fatores = d.pop("fatores")
        for fatores_item_data in _fatores:
            fatores_item = FatorPesoEntrada.from_dict(fatores_item_data)

            fatores.append(fatores_item)

        aprovacao_tipo = ExecucaoEntradaAprovacaoTipo(d.pop("aprovacao_tipo"))

        aprovacao_valor = d.pop("aprovacao_valor")

        execucao_entrada = cls(
            resolucao_m=resolucao_m,
            fatores=fatores,
            aprovacao_tipo=aprovacao_tipo,
            aprovacao_valor=aprovacao_valor,
        )

        return execucao_entrada
