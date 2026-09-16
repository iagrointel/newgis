from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="CriarEntrada")


@_attrs_define
class CriarEntrada:
    """
    Attributes:
        url (str):
        identificador (str):
        tipos (list[str] | None | Unset): subconjunto de wms/wfs/wmts; padrão = todos
    """

    url: str
    identificador: str
    tipos: list[str] | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        url = self.url

        identificador = self.identificador

        tipos: list[str] | None | Unset
        if isinstance(self.tipos, Unset):
            tipos = UNSET
        elif isinstance(self.tipos, list):
            tipos = self.tipos

        else:
            tipos = self.tipos

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "url": url,
                "identificador": identificador,
            }
        )
        if tipos is not UNSET:
            field_dict["tipos"] = tipos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        url = d.pop("url")

        identificador = d.pop("identificador")

        def _parse_tipos(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                tipos_type_0 = cast(list[str], data)

                return tipos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        tipos = _parse_tipos(d.pop("tipos", UNSET))

        criar_entrada = cls(
            url=url,
            identificador=identificador,
            tipos=tipos,
        )

        return criar_entrada
