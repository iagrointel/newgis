from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.conflito_atual_type_0 import ConflitoAtualType0


T = TypeVar("T", bound="Conflito")


@_attrs_define
class Conflito:
    """
    Attributes:
        camada_id (str):
        id (str):
        operacao (str):
        resolucao (str):
        versao_cliente (int | None | Unset):
        versao_servidor (int | None | Unset):
        atual (ConflitoAtualType0 | None | Unset):
    """

    camada_id: str
    id: str
    operacao: str
    resolucao: str
    versao_cliente: int | None | Unset = UNSET
    versao_servidor: int | None | Unset = UNSET
    atual: ConflitoAtualType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.conflito_atual_type_0 import ConflitoAtualType0  # noqa: PLC0415

        camada_id = self.camada_id

        id = self.id

        operacao = self.operacao

        resolucao = self.resolucao

        versao_cliente: int | None | Unset
        if isinstance(self.versao_cliente, Unset):
            versao_cliente = UNSET
        else:
            versao_cliente = self.versao_cliente

        versao_servidor: int | None | Unset
        if isinstance(self.versao_servidor, Unset):
            versao_servidor = UNSET
        else:
            versao_servidor = self.versao_servidor

        atual: dict[str, Any] | None | Unset
        if isinstance(self.atual, Unset):
            atual = UNSET
        elif isinstance(self.atual, ConflitoAtualType0):
            atual = self.atual.to_dict()
        else:
            atual = self.atual

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "camada_id": camada_id,
                "id": id,
                "operacao": operacao,
                "resolucao": resolucao,
            }
        )
        if versao_cliente is not UNSET:
            field_dict["versao_cliente"] = versao_cliente
        if versao_servidor is not UNSET:
            field_dict["versao_servidor"] = versao_servidor
        if atual is not UNSET:
            field_dict["atual"] = atual

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conflito_atual_type_0 import ConflitoAtualType0  # noqa: PLC0415

        d = dict(src_dict)
        camada_id = d.pop("camada_id")

        id = d.pop("id")

        operacao = d.pop("operacao")

        resolucao = d.pop("resolucao")

        def _parse_versao_cliente(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        versao_cliente = _parse_versao_cliente(d.pop("versao_cliente", UNSET))

        def _parse_versao_servidor(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        versao_servidor = _parse_versao_servidor(d.pop("versao_servidor", UNSET))

        def _parse_atual(data: object) -> ConflitoAtualType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                atual_type_0 = ConflitoAtualType0.from_dict(data)

                return atual_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConflitoAtualType0 | None | Unset, data)

        atual = _parse_atual(d.pop("atual", UNSET))

        conflito = cls(
            camada_id=camada_id,
            id=id,
            operacao=operacao,
            resolucao=resolucao,
            versao_cliente=versao_cliente,
            versao_servidor=versao_servidor,
            atual=atual,
        )

        conflito.additional_properties = d
        return conflito

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
