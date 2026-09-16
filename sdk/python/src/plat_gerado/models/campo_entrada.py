from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.campo_entrada_dominio_type_0_item import CampoEntradaDominioType0Item


T = TypeVar("T", bound="CampoEntrada")


@_attrs_define
class CampoEntrada:
    """
    Attributes:
        nome (str):
        tipo (str):
        tamanho (int | None | Unset):
        alias (None | str | Unset):
        obrigatorio (bool | Unset):  Default: False.
        padrao (None | str | Unset):
        dominio (list[CampoEntradaDominioType0Item] | None | Unset):
        indice (bool | Unset):  Default: False.
    """

    nome: str
    tipo: str
    tamanho: int | None | Unset = UNSET
    alias: None | str | Unset = UNSET
    obrigatorio: bool | Unset = False
    padrao: None | str | Unset = UNSET
    dominio: list[CampoEntradaDominioType0Item] | None | Unset = UNSET
    indice: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        tipo = self.tipo

        tamanho: int | None | Unset
        if isinstance(self.tamanho, Unset):
            tamanho = UNSET
        else:
            tamanho = self.tamanho

        alias: None | str | Unset
        if isinstance(self.alias, Unset):
            alias = UNSET
        else:
            alias = self.alias

        obrigatorio = self.obrigatorio

        padrao: None | str | Unset
        if isinstance(self.padrao, Unset):
            padrao = UNSET
        else:
            padrao = self.padrao

        dominio: list[dict[str, Any]] | None | Unset
        if isinstance(self.dominio, Unset):
            dominio = UNSET
        elif isinstance(self.dominio, list):
            dominio = []
            for dominio_type_0_item_data in self.dominio:
                dominio_type_0_item = dominio_type_0_item_data.to_dict()
                dominio.append(dominio_type_0_item)

        else:
            dominio = self.dominio

        indice = self.indice

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "tipo": tipo,
            }
        )
        if tamanho is not UNSET:
            field_dict["tamanho"] = tamanho
        if alias is not UNSET:
            field_dict["alias"] = alias
        if obrigatorio is not UNSET:
            field_dict["obrigatorio"] = obrigatorio
        if padrao is not UNSET:
            field_dict["padrao"] = padrao
        if dominio is not UNSET:
            field_dict["dominio"] = dominio
        if indice is not UNSET:
            field_dict["indice"] = indice

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.campo_entrada_dominio_type_0_item import CampoEntradaDominioType0Item  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        tipo = d.pop("tipo")

        def _parse_tamanho(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        tamanho = _parse_tamanho(d.pop("tamanho", UNSET))

        def _parse_alias(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        alias = _parse_alias(d.pop("alias", UNSET))

        obrigatorio = d.pop("obrigatorio", UNSET)

        def _parse_padrao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        padrao = _parse_padrao(d.pop("padrao", UNSET))

        def _parse_dominio(data: object) -> list[CampoEntradaDominioType0Item] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                dominio_type_0 = []
                _dominio_type_0 = data
                for dominio_type_0_item_data in _dominio_type_0:
                    dominio_type_0_item = CampoEntradaDominioType0Item.from_dict(dominio_type_0_item_data)

                    dominio_type_0.append(dominio_type_0_item)

                return dominio_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[CampoEntradaDominioType0Item] | None | Unset, data)

        dominio = _parse_dominio(d.pop("dominio", UNSET))

        indice = d.pop("indice", UNSET)

        campo_entrada = cls(
            nome=nome,
            tipo=tipo,
            tamanho=tamanho,
            alias=alias,
            obrigatorio=obrigatorio,
            padrao=padrao,
            dominio=dominio,
            indice=indice,
        )

        return campo_entrada
