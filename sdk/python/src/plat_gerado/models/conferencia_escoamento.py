from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.conferencia_escoamento_problemas_item import ConferenciaEscoamentoProblemasItem


T = TypeVar("T", bound="ConferenciaEscoamento")


@_attrs_define
class ConferenciaEscoamento:
    """Resposta da conferência de escoamento por gravidade. `alterou_a_rede` é sempre falso: a conferência
    nomeia a divergência e nunca inverte o trecho.

        Attributes:
            total (int):
            sob_pressao (int):
            conferidos (int):
            conformes (int):
            com_testemunha_nas_estruturas (int):
            percentual_concordancia (float | None):
            alterou_a_rede (bool):
            problemas (list[ConferenciaEscoamentoProblemasItem]):
    """

    total: int
    sob_pressao: int
    conferidos: int
    conformes: int
    com_testemunha_nas_estruturas: int
    percentual_concordancia: float | None
    alterou_a_rede: bool
    problemas: list[ConferenciaEscoamentoProblemasItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total = self.total

        sob_pressao = self.sob_pressao

        conferidos = self.conferidos

        conformes = self.conformes

        com_testemunha_nas_estruturas = self.com_testemunha_nas_estruturas

        percentual_concordancia: float | None
        percentual_concordancia = self.percentual_concordancia

        alterou_a_rede = self.alterou_a_rede

        problemas = []
        for problemas_item_data in self.problemas:
            problemas_item = problemas_item_data.to_dict()
            problemas.append(problemas_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total": total,
                "sob_pressao": sob_pressao,
                "conferidos": conferidos,
                "conformes": conformes,
                "com_testemunha_nas_estruturas": com_testemunha_nas_estruturas,
                "percentual_concordancia": percentual_concordancia,
                "alterou_a_rede": alterou_a_rede,
                "problemas": problemas,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conferencia_escoamento_problemas_item import ConferenciaEscoamentoProblemasItem  # noqa: PLC0415

        d = dict(src_dict)
        total = d.pop("total")

        sob_pressao = d.pop("sob_pressao")

        conferidos = d.pop("conferidos")

        conformes = d.pop("conformes")

        com_testemunha_nas_estruturas = d.pop("com_testemunha_nas_estruturas")

        def _parse_percentual_concordancia(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        percentual_concordancia = _parse_percentual_concordancia(d.pop("percentual_concordancia"))

        alterou_a_rede = d.pop("alterou_a_rede")

        problemas = []
        _problemas = d.pop("problemas")
        for problemas_item_data in _problemas:
            problemas_item = ConferenciaEscoamentoProblemasItem.from_dict(problemas_item_data)

            problemas.append(problemas_item)

        conferencia_escoamento = cls(
            total=total,
            sob_pressao=sob_pressao,
            conferidos=conferidos,
            conformes=conformes,
            com_testemunha_nas_estruturas=com_testemunha_nas_estruturas,
            percentual_concordancia=percentual_concordancia,
            alterou_a_rede=alterou_a_rede,
            problemas=problemas,
        )

        conferencia_escoamento.additional_properties = d
        return conferencia_escoamento

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
