from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.pasta_arvore_dono import PastaArvoreDono


T = TypeVar("T", bound="PastaArvore")


@_attrs_define
class PastaArvore:
    """
    Attributes:
        id (str):
        nome (str):
        pai_id (None | str):
        profundidade (int):
        ancestrais (list[str]):
        itens_visiveis (int):
        dono (PastaArvoreDono):
        criado_em (None | str):
        filhas (list[Any] | Unset):
    """

    id: str
    nome: str
    pai_id: None | str
    profundidade: int
    ancestrais: list[str]
    itens_visiveis: int
    dono: PastaArvoreDono
    criado_em: None | str
    filhas: list[Any] | Unset = UNSET
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

        filhas: list[Any] | Unset = UNSET
        if not isinstance(self.filhas, Unset):
            filhas = self.filhas

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
        if filhas is not UNSET:
            field_dict["filhas"] = filhas

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pasta_arvore_dono import PastaArvoreDono  # noqa: PLC0415

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

        dono = PastaArvoreDono.from_dict(d.pop("dono"))

        def _parse_criado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        criado_em = _parse_criado_em(d.pop("criado_em"))

        filhas = cast(list[Any], d.pop("filhas", UNSET))

        pasta_arvore = cls(
            id=id,
            nome=nome,
            pai_id=pai_id,
            profundidade=profundidade,
            ancestrais=ancestrais,
            itens_visiveis=itens_visiveis,
            dono=dono,
            criado_em=criado_em,
            filhas=filhas,
        )

        pasta_arvore.additional_properties = d
        return pasta_arvore

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
