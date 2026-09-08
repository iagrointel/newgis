from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.inquilino_criado_admin import InquilinoCriadoAdmin


T = TypeVar("T", bound="InquilinoCriado")


@_attrs_define
class InquilinoCriado:
    """
    Attributes:
        id (int):
        slug (str):
        admin (InquilinoCriadoAdmin):
        senha_temporaria (str):
    """

    id: int
    slug: str
    admin: InquilinoCriadoAdmin
    senha_temporaria: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        slug = self.slug

        admin = self.admin.to_dict()

        senha_temporaria = self.senha_temporaria

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "slug": slug,
                "admin": admin,
                "senha_temporaria": senha_temporaria,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.inquilino_criado_admin import InquilinoCriadoAdmin  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        slug = d.pop("slug")

        admin = InquilinoCriadoAdmin.from_dict(d.pop("admin"))

        senha_temporaria = d.pop("senha_temporaria")

        inquilino_criado = cls(
            id=id,
            slug=slug,
            admin=admin,
            senha_temporaria=senha_temporaria,
        )

        inquilino_criado.additional_properties = d
        return inquilino_criado

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
