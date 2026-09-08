from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.tipo_item_esquema import TipoItemEsquema


T = TypeVar("T", bound="TipoItem")


@_attrs_define
class TipoItem:
    """
    Attributes:
        nome (str):
        familia (str):
        rotulo (str):
        descricao (str):
        esquema (TipoItemEsquema):
        esquema_versao (int):
        icone (str):
        modulo_front (str):
        abre_em (list[str]):
        tem_dado_fisico (bool):
        linha_dona (str):
    """

    nome: str
    familia: str
    rotulo: str
    descricao: str
    esquema: TipoItemEsquema
    esquema_versao: int
    icone: str
    modulo_front: str
    abre_em: list[str]
    tem_dado_fisico: bool
    linha_dona: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        familia = self.familia

        rotulo = self.rotulo

        descricao = self.descricao

        esquema = self.esquema.to_dict()

        esquema_versao = self.esquema_versao

        icone = self.icone

        modulo_front = self.modulo_front

        abre_em = self.abre_em

        tem_dado_fisico = self.tem_dado_fisico

        linha_dona = self.linha_dona

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nome": nome,
                "familia": familia,
                "rotulo": rotulo,
                "descricao": descricao,
                "esquema": esquema,
                "esquema_versao": esquema_versao,
                "icone": icone,
                "modulo_front": modulo_front,
                "abre_em": abre_em,
                "tem_dado_fisico": tem_dado_fisico,
                "linha_dona": linha_dona,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tipo_item_esquema import TipoItemEsquema  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        familia = d.pop("familia")

        rotulo = d.pop("rotulo")

        descricao = d.pop("descricao")

        esquema = TipoItemEsquema.from_dict(d.pop("esquema"))

        esquema_versao = d.pop("esquema_versao")

        icone = d.pop("icone")

        modulo_front = d.pop("modulo_front")

        abre_em = cast(list[str], d.pop("abre_em"))

        tem_dado_fisico = d.pop("tem_dado_fisico")

        linha_dona = d.pop("linha_dona")

        tipo_item = cls(
            nome=nome,
            familia=familia,
            rotulo=rotulo,
            descricao=descricao,
            esquema=esquema,
            esquema_versao=esquema_versao,
            icone=icone,
            modulo_front=modulo_front,
            abre_em=abre_em,
            tem_dado_fisico=tem_dado_fisico,
            linha_dona=linha_dona,
        )

        tipo_item.additional_properties = d
        return tipo_item

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
