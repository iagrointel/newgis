from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.pasta_dono import PastaDono


T = TypeVar("T", bound="Pasta")


@_attrs_define
class Pasta:
    """
    Attributes:
        id (str):
        nome (str):
        pai_id (None | str):
        profundidade (int):
        ancestrais (list[str]):
        itens_visiveis (int):
        dono (PastaDono):
        criado_em (None | str):
    """

    id: str
    nome: str
    pai_id: None | str
    profundidade: int
    ancestrais: list[str]
    itens_visiveis: int
    dono: PastaDono
    criado_em: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        nome = self.nome

        pai_id: None | str
        pai_id = self.pai_id

        profundidade = self.profundidade

        ancestrais = self.ancestrais

        itens_visiveis = self.itens_visiveis

        dono = self.dono.to_dict()

        criado_em: None | str
        criado_em = self.criado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nome": nome,
                "pai_id": pai_id,
                "profundidade": profundidade,
                "ancestrais": ancestrais,
                "itens_visiveis": itens_visiveis,
                "dono": dono,
                "criado_em": criado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pasta_dono import PastaDono  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        nome = d.pop("nome")

        def _parse_pai_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        pai_id = _parse_pai_id(d.pop("pai_id"))

        profundidade = d.pop("profundidade")

        ancestrais = cast(list[str], d.pop("ancestrais"))

        itens_visiveis = d.pop("itens_visiveis")

        dono = PastaDono.from_dict(d.pop("dono"))

        def _parse_criado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        criado_em = _parse_criado_em(d.pop("criado_em"))

        pasta = cls(
            id=id,
            nome=nome,
            pai_id=pai_id,
            profundidade=profundidade,
            ancestrais=ancestrais,
            itens_visiveis=itens_visiveis,
            dono=dono,
            criado_em=criado_em,
        )

        pasta.additional_properties = d
        return pasta

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
