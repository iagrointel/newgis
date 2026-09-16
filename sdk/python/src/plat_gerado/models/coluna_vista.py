from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.coluna_vista_dominio_type_0 import ColunaVistaDominioType0


T = TypeVar("T", bound="ColunaVista")


@_attrs_define
class ColunaVista:
    """
    Attributes:
        nome (str):
        alias (None | str | Unset):
        oculta (bool | Unset):  Default: False.
        largura (int | None | Unset):
        dominio (ColunaVistaDominioType0 | None | Unset):
    """

    nome: str
    alias: None | str | Unset = UNSET
    oculta: bool | Unset = False
    largura: int | None | Unset = UNSET
    dominio: ColunaVistaDominioType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.coluna_vista_dominio_type_0 import ColunaVistaDominioType0  # noqa: PLC0415

        nome = self.nome

        alias: None | str | Unset
        if isinstance(self.alias, Unset):
            alias = UNSET
        else:
            alias = self.alias

        oculta = self.oculta

        largura: int | None | Unset
        if isinstance(self.largura, Unset):
            largura = UNSET
        else:
            largura = self.largura

        dominio: dict[str, Any] | None | Unset
        if isinstance(self.dominio, Unset):
            dominio = UNSET
        elif isinstance(self.dominio, ColunaVistaDominioType0):
            dominio = self.dominio.to_dict()
        else:
            dominio = self.dominio

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nome": nome,
            }
        )
        if alias is not UNSET:
            field_dict["alias"] = alias
        if oculta is not UNSET:
            field_dict["oculta"] = oculta
        if largura is not UNSET:
            field_dict["largura"] = largura
        if dominio is not UNSET:
            field_dict["dominio"] = dominio

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.coluna_vista_dominio_type_0 import ColunaVistaDominioType0  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        def _parse_alias(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        alias = _parse_alias(d.pop("alias", UNSET))

        oculta = d.pop("oculta", UNSET)

        def _parse_largura(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        largura = _parse_largura(d.pop("largura", UNSET))

        def _parse_dominio(data: object) -> ColunaVistaDominioType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                dominio_type_0 = ColunaVistaDominioType0.from_dict(data)

                return dominio_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ColunaVistaDominioType0 | None | Unset, data)

        dominio = _parse_dominio(d.pop("dominio", UNSET))

        coluna_vista = cls(
            nome=nome,
            alias=alias,
            oculta=oculta,
            largura=largura,
            dominio=dominio,
        )

        coluna_vista.additional_properties = d
        return coluna_vista

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
