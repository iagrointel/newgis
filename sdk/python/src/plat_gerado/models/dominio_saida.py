from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.dominio_saida_valores_type_0_item import DominioSaidaValoresType0Item
    from ..models.dominio_saida_valores_type_1 import DominioSaidaValoresType1


T = TypeVar("T", bound="DominioSaida")


@_attrs_define
class DominioSaida:
    """
    Attributes:
        id (str):
        nome (str):
        tipo (str):
        tipo_campo (str):
        valores (DominioSaidaValoresType1 | list[DominioSaidaValoresType0Item]):
        descricao (None | str | Unset):
        criado_em (None | str | Unset):
        atualizado_em (None | str | Unset):
    """

    id: str
    nome: str
    tipo: str
    tipo_campo: str
    valores: DominioSaidaValoresType1 | list[DominioSaidaValoresType0Item]
    descricao: None | str | Unset = UNSET
    criado_em: None | str | Unset = UNSET
    atualizado_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        nome = self.nome

        tipo = self.tipo

        tipo_campo = self.tipo_campo

        valores: dict[str, Any] | list[dict[str, Any]]
        if isinstance(self.valores, list):
            valores = []
            for valores_type_0_item_data in self.valores:
                valores_type_0_item = valores_type_0_item_data.to_dict()
                valores.append(valores_type_0_item)

        else:
            valores = self.valores.to_dict()

        descricao: None | str | Unset
        if isinstance(self.descricao, Unset):
            descricao = UNSET
        else:
            descricao = self.descricao

        criado_em: None | str | Unset
        if isinstance(self.criado_em, Unset):
            criado_em = UNSET
        else:
            criado_em = self.criado_em

        atualizado_em: None | str | Unset
        if isinstance(self.atualizado_em, Unset):
            atualizado_em = UNSET
        else:
            atualizado_em = self.atualizado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nome": nome,
                "tipo": tipo,
                "tipo_campo": tipo_campo,
                "valores": valores,
            }
        )
        if descricao is not UNSET:
            field_dict["descricao"] = descricao
        if criado_em is not UNSET:
            field_dict["criado_em"] = criado_em
        if atualizado_em is not UNSET:
            field_dict["atualizado_em"] = atualizado_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.dominio_saida_valores_type_0_item import DominioSaidaValoresType0Item  # noqa: PLC0415
        from ..models.dominio_saida_valores_type_1 import DominioSaidaValoresType1  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        nome = d.pop("nome")

        tipo = d.pop("tipo")

        tipo_campo = d.pop("tipo_campo")

        def _parse_valores(data: object) -> DominioSaidaValoresType1 | list[DominioSaidaValoresType0Item]:
            try:
                if not isinstance(data, list):
                    raise TypeError()
                valores_type_0 = []
                _valores_type_0 = data
                for valores_type_0_item_data in _valores_type_0:
                    valores_type_0_item = DominioSaidaValoresType0Item.from_dict(valores_type_0_item_data)

                    valores_type_0.append(valores_type_0_item)

                return valores_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            valores_type_1 = DominioSaidaValoresType1.from_dict(data)

            return valores_type_1

        valores = _parse_valores(d.pop("valores"))

        def _parse_descricao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        descricao = _parse_descricao(d.pop("descricao", UNSET))

        def _parse_criado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        criado_em = _parse_criado_em(d.pop("criado_em", UNSET))

        def _parse_atualizado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        atualizado_em = _parse_atualizado_em(d.pop("atualizado_em", UNSET))

        dominio_saida = cls(
            id=id,
            nome=nome,
            tipo=tipo,
            tipo_campo=tipo_campo,
            valores=valores,
            descricao=descricao,
            criado_em=criado_em,
            atualizado_em=atualizado_em,
        )

        dominio_saida.additional_properties = d
        return dominio_saida

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
