from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.item_dono import ItemDono


T = TypeVar("T", bound="Item")


@_attrs_define
class Item:
    """
    Attributes:
        id (str):
        tipo (str):
        familia (str):
        titulo (str):
        tags (list[str]):
        dono (ItemDono):
        acesso (str):
        protegido (bool):
        pontuacao (int):
        versao_atual (int):
    """

    id: str
    tipo: str
    familia: str
    titulo: str
    tags: list[str]
    dono: ItemDono
    acesso: str
    protegido: bool
    pontuacao: int
    versao_atual: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        tipo = self.tipo

        familia = self.familia

        titulo = self.titulo

        tags = self.tags

        dono = self.dono.to_dict()

        acesso = self.acesso

        protegido = self.protegido

        pontuacao = self.pontuacao

        versao_atual = self.versao_atual

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "tipo": tipo,
                "familia": familia,
                "titulo": titulo,
                "tags": tags,
                "dono": dono,
                "acesso": acesso,
                "protegido": protegido,
                "pontuacao": pontuacao,
                "versao_atual": versao_atual,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.item_dono import ItemDono  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        tipo = d.pop("tipo")

        familia = d.pop("familia")

        titulo = d.pop("titulo")

        tags = cast(list[str], d.pop("tags"))

        dono = ItemDono.from_dict(d.pop("dono"))

        acesso = d.pop("acesso")

        protegido = d.pop("protegido")

        pontuacao = d.pop("pontuacao")

        versao_atual = d.pop("versao_atual")

        item = cls(
            id=id,
            tipo=tipo,
            familia=familia,
            titulo=titulo,
            tags=tags,
            dono=dono,
            acesso=acesso,
            protegido=protegido,
            pontuacao=pontuacao,
            versao_atual=versao_atual,
        )

        item.additional_properties = d
        return item

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
