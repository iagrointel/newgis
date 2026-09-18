from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="BlocoTexto")


@_attrs_define
class BlocoTexto:
    """
    Attributes:
        tipo (Literal['texto']):
        texto (str):
        titulo (str | Unset):  Default: ''.
    """

    tipo: Literal["texto"]
    texto: str
    titulo: str | Unset = ""

    def to_dict(self) -> dict[str, Any]:
        tipo = self.tipo

        texto = self.texto

        titulo = self.titulo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "tipo": tipo,
                "texto": texto,
            }
        )
        if titulo is not UNSET:
            field_dict["titulo"] = titulo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tipo = cast(Literal["texto"], d.pop("tipo"))
        if tipo != "texto":
            raise ValueError(f"tipo must match const 'texto', got '{tipo}'")

        texto = d.pop("texto")

        titulo = d.pop("titulo", UNSET)

        bloco_texto = cls(
            tipo=tipo,
            texto=texto,
            titulo=titulo,
        )

        return bloco_texto
