from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.pedido_criterios_feicao_camadas import PedidoCriteriosFeicaoCamadas
    from ..models.pedido_criterios_feicao_criterios_item import PedidoCriteriosFeicaoCriteriosItem
    from ..models.pedido_criterios_feicao_feicoes_item import PedidoCriteriosFeicaoFeicoesItem


T = TypeVar("T", bound="PedidoCriteriosFeicao")


@_attrs_define
class PedidoCriteriosFeicao:
    """
    Attributes:
        feicoes (list[PedidoCriteriosFeicaoFeicoesItem]): Feições do usuário em GeoJSON (EPSG:4326), cada uma com
            'geometry', 'properties' e um id estável em 'id' ou em properties.id.
        criterios (list[PedidoCriteriosFeicaoCriteriosItem]): Critérios sobre a feição: tipo (atributo, contagem_raio,
            contagem_dentro, distancia_mais_proxima), influência (positiva, inversa, ideal), peso e, quando for o caso,
            campo, camada, raio_m, alvo/alcance, minimo/maximo e faixa_inclusao.
        camadas (PedidoCriteriosFeicaoCamadas | Unset): {nome: [Feature, ...]} — as camadas de apoio citadas pelos
            critérios de raio, contenção e distância (tipicamente pontos).
        combinador (str | Unset):  Default: 'soma_ponderada'.
        politica_ausente (str | Unset):  Default: 'excluir'.
        srid_trabalho (int | None | Unset): CRS métrico de trabalho; omitido = zona UTM SIRGAS 2000 do centróide das
            feições.
    """

    feicoes: list[PedidoCriteriosFeicaoFeicoesItem]
    criterios: list[PedidoCriteriosFeicaoCriteriosItem]
    camadas: PedidoCriteriosFeicaoCamadas | Unset = UNSET
    combinador: str | Unset = "soma_ponderada"
    politica_ausente: str | Unset = "excluir"
    srid_trabalho: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        feicoes = []
        for feicoes_item_data in self.feicoes:
            feicoes_item = feicoes_item_data.to_dict()
            feicoes.append(feicoes_item)

        criterios = []
        for criterios_item_data in self.criterios:
            criterios_item = criterios_item_data.to_dict()
            criterios.append(criterios_item)

        camadas: dict[str, Any] | Unset = UNSET
        if not isinstance(self.camadas, Unset):
            camadas = self.camadas.to_dict()

        combinador = self.combinador

        politica_ausente = self.politica_ausente

        srid_trabalho: int | None | Unset
        if isinstance(self.srid_trabalho, Unset):
            srid_trabalho = UNSET
        else:
            srid_trabalho = self.srid_trabalho

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "feicoes": feicoes,
                "criterios": criterios,
            }
        )
        if camadas is not UNSET:
            field_dict["camadas"] = camadas
        if combinador is not UNSET:
            field_dict["combinador"] = combinador
        if politica_ausente is not UNSET:
            field_dict["politica_ausente"] = politica_ausente
        if srid_trabalho is not UNSET:
            field_dict["srid_trabalho"] = srid_trabalho

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pedido_criterios_feicao_camadas import PedidoCriteriosFeicaoCamadas  # noqa: PLC0415
        from ..models.pedido_criterios_feicao_criterios_item import PedidoCriteriosFeicaoCriteriosItem  # noqa: PLC0415
        from ..models.pedido_criterios_feicao_feicoes_item import PedidoCriteriosFeicaoFeicoesItem  # noqa: PLC0415

        d = dict(src_dict)
        feicoes = []
        _feicoes = d.pop("feicoes")
        for feicoes_item_data in _feicoes:
            feicoes_item = PedidoCriteriosFeicaoFeicoesItem.from_dict(feicoes_item_data)

            feicoes.append(feicoes_item)

        criterios = []
        _criterios = d.pop("criterios")
        for criterios_item_data in _criterios:
            criterios_item = PedidoCriteriosFeicaoCriteriosItem.from_dict(criterios_item_data)

            criterios.append(criterios_item)

        _camadas = d.pop("camadas", UNSET)
        camadas: PedidoCriteriosFeicaoCamadas | Unset
        if isinstance(_camadas, Unset):
            camadas = UNSET
        else:
            camadas = PedidoCriteriosFeicaoCamadas.from_dict(_camadas)

        combinador = d.pop("combinador", UNSET)

        politica_ausente = d.pop("politica_ausente", UNSET)

        def _parse_srid_trabalho(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        srid_trabalho = _parse_srid_trabalho(d.pop("srid_trabalho", UNSET))

        pedido_criterios_feicao = cls(
            feicoes=feicoes,
            criterios=criterios,
            camadas=camadas,
            combinador=combinador,
            politica_ausente=politica_ausente,
            srid_trabalho=srid_trabalho,
        )

        pedido_criterios_feicao.additional_properties = d
        return pedido_criterios_feicao

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
