from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.tema_entrada_tema_type_0 import TemaEntradaTemaType0


T = TypeVar("T", bound="TemaEntrada")


@_attrs_define
class TemaEntrada:
    """
    Attributes:
        tema (None | TemaEntradaTemaType0): definição de tema (tokens) ou null para remover
    """

    tema: None | TemaEntradaTemaType0

    def to_dict(self) -> dict[str, Any]:
        from ..models.tema_entrada_tema_type_0 import TemaEntradaTemaType0  # noqa: PLC0415

        tema: dict[str, Any] | None
        if isinstance(self.tema, TemaEntradaTemaType0):
            tema = self.tema.to_dict()
        else:
            tema = self.tema

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "tema": tema,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tema_entrada_tema_type_0 import TemaEntradaTemaType0  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_tema(data: object) -> None | TemaEntradaTemaType0:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                tema_type_0 = TemaEntradaTemaType0.from_dict(data)

                return tema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TemaEntradaTemaType0, data)

        tema = _parse_tema(d.pop("tema"))

        tema_entrada = cls(
            tema=tema,
        )

        return tema_entrada
