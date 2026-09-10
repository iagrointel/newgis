from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.membro_usuario import MembroUsuario


T = TypeVar("T", bound="Membro")


@_attrs_define
class Membro:
    """
    Attributes:
        usuario (MembroUsuario):
        papel (str):
        estado (str):
        criado_em (None | str):
    """

    usuario: MembroUsuario
    papel: str
    estado: str
    criado_em: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        usuario = self.usuario.to_dict()

        papel = self.papel

        estado = self.estado

        criado_em: None | str
        criado_em = self.criado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "usuario": usuario,
                "papel": papel,
                "estado": estado,
                "criado_em": criado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.membro_usuario import MembroUsuario  # noqa: PLC0415

        d = dict(src_dict)
        usuario = MembroUsuario.from_dict(d.pop("usuario"))

        papel = d.pop("papel")

        estado = d.pop("estado")

        def _parse_criado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        criado_em = _parse_criado_em(d.pop("criado_em"))

        membro = cls(
            usuario=usuario,
            papel=papel,
            estado=estado,
            criado_em=criado_em,
        )

        membro.additional_properties = d
        return membro

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
