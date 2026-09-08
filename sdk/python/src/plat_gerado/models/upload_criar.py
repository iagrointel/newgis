from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="UploadCriar")


@_attrs_define
class UploadCriar:
    """
    Attributes:
        nome (str):
        bytes_ (int):
        tipo_declarado (str):
        sha256 (None | str | Unset):
    """

    nome: str
    bytes_: int
    tipo_declarado: str
    sha256: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        bytes_ = self.bytes_

        tipo_declarado = self.tipo_declarado

        sha256: None | str | Unset
        if isinstance(self.sha256, Unset):
            sha256 = UNSET
        else:
            sha256 = self.sha256

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "bytes": bytes_,
                "tipo_declarado": tipo_declarado,
            }
        )
        if sha256 is not UNSET:
            field_dict["sha256"] = sha256

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        bytes_ = d.pop("bytes")

        tipo_declarado = d.pop("tipo_declarado")

        def _parse_sha256(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sha256 = _parse_sha256(d.pop("sha256", UNSET))

        upload_criar = cls(
            nome=nome,
            bytes_=bytes_,
            tipo_declarado=tipo_declarado,
            sha256=sha256,
        )

        return upload_criar
