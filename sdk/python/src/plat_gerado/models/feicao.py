from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.feicao_atributos import FeicaoAtributos


T = TypeVar("T", bound="Feicao")


@_attrs_define
class Feicao:
    """
    Attributes:
        id (str):
        tipo_id (str):
        fase_bitmask (int | None):
        atributos (FeicaoAtributos):
        criado_em (str):
    """

    id: str
    tipo_id: str
    fase_bitmask: int | None
    atributos: FeicaoAtributos
    criado_em: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        tipo_id = self.tipo_id

        fase_bitmask: int | None
        fase_bitmask = self.fase_bitmask

        atributos = self.atributos.to_dict()

        criado_em = self.criado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "tipo_id": tipo_id,
                "fase_bitmask": fase_bitmask,
                "atributos": atributos,
                "criado_em": criado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.feicao_atributos import FeicaoAtributos  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        tipo_id = d.pop("tipo_id")

        def _parse_fase_bitmask(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        fase_bitmask = _parse_fase_bitmask(d.pop("fase_bitmask"))

        atributos = FeicaoAtributos.from_dict(d.pop("atributos"))

        criado_em = d.pop("criado_em")

        feicao = cls(
            id=id,
            tipo_id=tipo_id,
            fase_bitmask=fase_bitmask,
            atributos=atributos,
            criado_em=criado_em,
        )

        feicao.additional_properties = d
        return feicao

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
