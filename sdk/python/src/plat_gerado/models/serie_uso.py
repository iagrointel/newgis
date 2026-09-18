from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.agora import Agora
    from ..models.cotas import Cotas
    from ..models.ponto_uso import PontoUso


T = TypeVar("T", bound="SerieUso")


@_attrs_define
class SerieUso:
    """
    Attributes:
        inquilino (str):
        dias (int):
        pontos (list[PontoUso]):
        cotas (Cotas):
        agora (Agora):
        ultimo_medido_em (None | str):
    """

    inquilino: str
    dias: int
    pontos: list[PontoUso]
    cotas: Cotas
    agora: Agora
    ultimo_medido_em: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        inquilino = self.inquilino

        dias = self.dias

        pontos = []
        for pontos_item_data in self.pontos:
            pontos_item = pontos_item_data.to_dict()
            pontos.append(pontos_item)

        cotas = self.cotas.to_dict()

        agora = self.agora.to_dict()

        ultimo_medido_em: None | str
        ultimo_medido_em = self.ultimo_medido_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "inquilino": inquilino,
                "dias": dias,
                "pontos": pontos,
                "cotas": cotas,
                "agora": agora,
                "ultimo_medido_em": ultimo_medido_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agora import Agora  # noqa: PLC0415
        from ..models.cotas import Cotas  # noqa: PLC0415
        from ..models.ponto_uso import PontoUso  # noqa: PLC0415

        d = dict(src_dict)
        inquilino = d.pop("inquilino")

        dias = d.pop("dias")

        pontos = []
        _pontos = d.pop("pontos")
        for pontos_item_data in _pontos:
            pontos_item = PontoUso.from_dict(pontos_item_data)

            pontos.append(pontos_item)

        cotas = Cotas.from_dict(d.pop("cotas"))

        agora = Agora.from_dict(d.pop("agora"))

        def _parse_ultimo_medido_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        ultimo_medido_em = _parse_ultimo_medido_em(d.pop("ultimo_medido_em"))

        serie_uso = cls(
            inquilino=inquilino,
            dias=dias,
            pontos=pontos,
            cotas=cotas,
            agora=agora,
            ultimo_medido_em=ultimo_medido_em,
        )

        serie_uso.additional_properties = d
        return serie_uso

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
