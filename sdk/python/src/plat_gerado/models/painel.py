from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.painel_acessos_por_dia_item import PainelAcessosPorDiaItem
    from ..models.painel_eventos_por_dia_item import PainelEventosPorDiaItem
    from ..models.painel_eventos_por_tipo_item import PainelEventosPorTipoItem
    from ..models.painel_janela import PainelJanela
    from ..models.painel_top_itens_item import PainelTopItensItem
    from ..models.painel_totais import PainelTotais


T = TypeVar("T", bound="Painel")


@_attrs_define
class Painel:
    """
    Attributes:
        janela (PainelJanela):
        totais (PainelTotais):
        top_itens (list[PainelTopItensItem]):
        eventos_por_dia (list[PainelEventosPorDiaItem]):
        eventos_por_tipo (list[PainelEventosPorTipoItem]):
        acessos_por_dia (list[PainelAcessosPorDiaItem]):
    """

    janela: PainelJanela
    totais: PainelTotais
    top_itens: list[PainelTopItensItem]
    eventos_por_dia: list[PainelEventosPorDiaItem]
    eventos_por_tipo: list[PainelEventosPorTipoItem]
    acessos_por_dia: list[PainelAcessosPorDiaItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        janela = self.janela.to_dict()

        totais = self.totais.to_dict()

        top_itens = []
        for top_itens_item_data in self.top_itens:
            top_itens_item = top_itens_item_data.to_dict()
            top_itens.append(top_itens_item)

        eventos_por_dia = []
        for eventos_por_dia_item_data in self.eventos_por_dia:
            eventos_por_dia_item = eventos_por_dia_item_data.to_dict()
            eventos_por_dia.append(eventos_por_dia_item)

        eventos_por_tipo = []
        for eventos_por_tipo_item_data in self.eventos_por_tipo:
            eventos_por_tipo_item = eventos_por_tipo_item_data.to_dict()
            eventos_por_tipo.append(eventos_por_tipo_item)

        acessos_por_dia = []
        for acessos_por_dia_item_data in self.acessos_por_dia:
            acessos_por_dia_item = acessos_por_dia_item_data.to_dict()
            acessos_por_dia.append(acessos_por_dia_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "janela": janela,
                "totais": totais,
                "top_itens": top_itens,
                "eventos_por_dia": eventos_por_dia,
                "eventos_por_tipo": eventos_por_tipo,
                "acessos_por_dia": acessos_por_dia,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.painel_acessos_por_dia_item import PainelAcessosPorDiaItem  # noqa: PLC0415
        from ..models.painel_eventos_por_dia_item import PainelEventosPorDiaItem  # noqa: PLC0415
        from ..models.painel_eventos_por_tipo_item import PainelEventosPorTipoItem  # noqa: PLC0415
        from ..models.painel_janela import PainelJanela  # noqa: PLC0415
        from ..models.painel_top_itens_item import PainelTopItensItem  # noqa: PLC0415
        from ..models.painel_totais import PainelTotais  # noqa: PLC0415

        d = dict(src_dict)
        janela = PainelJanela.from_dict(d.pop("janela"))

        totais = PainelTotais.from_dict(d.pop("totais"))

        top_itens = []
        _top_itens = d.pop("top_itens")
        for top_itens_item_data in _top_itens:
            top_itens_item = PainelTopItensItem.from_dict(top_itens_item_data)

            top_itens.append(top_itens_item)

        eventos_por_dia = []
        _eventos_por_dia = d.pop("eventos_por_dia")
        for eventos_por_dia_item_data in _eventos_por_dia:
            eventos_por_dia_item = PainelEventosPorDiaItem.from_dict(eventos_por_dia_item_data)

            eventos_por_dia.append(eventos_por_dia_item)

        eventos_por_tipo = []
        _eventos_por_tipo = d.pop("eventos_por_tipo")
        for eventos_por_tipo_item_data in _eventos_por_tipo:
            eventos_por_tipo_item = PainelEventosPorTipoItem.from_dict(eventos_por_tipo_item_data)

            eventos_por_tipo.append(eventos_por_tipo_item)

        acessos_por_dia = []
        _acessos_por_dia = d.pop("acessos_por_dia")
        for acessos_por_dia_item_data in _acessos_por_dia:
            acessos_por_dia_item = PainelAcessosPorDiaItem.from_dict(acessos_por_dia_item_data)

            acessos_por_dia.append(acessos_por_dia_item)

        painel = cls(
            janela=janela,
            totais=totais,
            top_itens=top_itens,
            eventos_por_dia=eventos_por_dia,
            eventos_por_tipo=eventos_por_tipo,
            acessos_por_dia=acessos_por_dia,
        )

        painel.additional_properties = d
        return painel

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
