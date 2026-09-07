from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ImportarGrupoEntrada")


@_attrs_define
class ImportarGrupoEntrada:
    """
    Attributes:
        grupo_dn (str):
        perfil (str):
        atributo_membro (str | Unset):  Default: 'member'.
        atributo_login (str | Unset):  Default: 'uid'.
    """

    grupo_dn: str
    perfil: str
    atributo_membro: str | Unset = "member"
    atributo_login: str | Unset = "uid"

    def to_dict(self) -> dict[str, Any]:
        grupo_dn = self.grupo_dn

        perfil = self.perfil

        atributo_membro = self.atributo_membro

        atributo_login = self.atributo_login

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "grupo_dn": grupo_dn,
                "perfil": perfil,
            }
        )
        if atributo_membro is not UNSET:
            field_dict["atributo_membro"] = atributo_membro
        if atributo_login is not UNSET:
            field_dict["atributo_login"] = atributo_login

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        grupo_dn = d.pop("grupo_dn")

        perfil = d.pop("perfil")

        atributo_membro = d.pop("atributo_membro", UNSET)

        atributo_login = d.pop("atributo_login", UNSET)

        importar_grupo_entrada = cls(
            grupo_dn=grupo_dn,
            perfil=perfil,
            atributo_membro=atributo_membro,
            atributo_login=atributo_login,
        )

        return importar_grupo_entrada
