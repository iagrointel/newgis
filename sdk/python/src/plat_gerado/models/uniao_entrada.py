from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.uniao_entrada_atributos_type_0 import UniaoEntradaAtributosType0
    from ..models.uniao_entrada_versoes import UniaoEntradaVersoes


T = TypeVar("T", bound="UniaoEntrada")


@_attrs_define
class UniaoEntrada:
    """
    Attributes:
        ids (list[str]):
        versoes (UniaoEntradaVersoes):
        atributos (None | UniaoEntradaAtributosType0 | Unset):
    """

    ids: list[str]
    versoes: UniaoEntradaVersoes
    atributos: None | UniaoEntradaAtributosType0 | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.uniao_entrada_atributos_type_0 import UniaoEntradaAtributosType0  # noqa: PLC0415

        ids = self.ids

        versoes = self.versoes.to_dict()

        atributos: dict[str, Any] | None | Unset
        if isinstance(self.atributos, Unset):
            atributos = UNSET
        elif isinstance(self.atributos, UniaoEntradaAtributosType0):
            atributos = self.atributos.to_dict()
        else:
            atributos = self.atributos

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "ids": ids,
                "versoes": versoes,
            }
        )
        if atributos is not UNSET:
            field_dict["atributos"] = atributos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.uniao_entrada_atributos_type_0 import UniaoEntradaAtributosType0  # noqa: PLC0415
        from ..models.uniao_entrada_versoes import UniaoEntradaVersoes  # noqa: PLC0415

        d = dict(src_dict)
        ids = cast(list[str], d.pop("ids"))

        versoes = UniaoEntradaVersoes.from_dict(d.pop("versoes"))

        def _parse_atributos(data: object) -> None | UniaoEntradaAtributosType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                atributos_type_0 = UniaoEntradaAtributosType0.from_dict(data)

                return atributos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | UniaoEntradaAtributosType0 | Unset, data)

        atributos = _parse_atributos(d.pop("atributos", UNSET))

        uniao_entrada = cls(
            ids=ids,
            versoes=versoes,
            atributos=atributos,
        )

        return uniao_entrada
