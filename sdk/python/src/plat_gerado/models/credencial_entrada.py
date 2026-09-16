from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="CredencialEntrada")


@_attrs_define
class CredencialEntrada:
    """PUT /api/agol/credencial (mesmo desenho de `app.conexao.modelos.ConexaoEditar`): `credencial` ausente
    (None) preserva a cifra já guardada, só atualizando portal/usuario/rotulo; `remover_credencial=true` apaga
    a credencial cifrada (e o `tipo`) sem apagar portal/usuario/rotulo. Quando `credencial` é informada,
    `tipo` é obrigatório ('senha', pareada com `usuario`, ou 'token', de longa duração, sem usuário).

        Attributes:
            portal (str | Unset):  Default: 'https://www.arcgis.com'.
            usuario (str | Unset):  Default: ''.
            tipo (None | str | Unset):
            credencial (None | str | Unset):
            remover_credencial (bool | Unset):  Default: False.
            rotulo (str | Unset):  Default: ''.
    """

    portal: str | Unset = "https://www.arcgis.com"
    usuario: str | Unset = ""
    tipo: None | str | Unset = UNSET
    credencial: None | str | Unset = UNSET
    remover_credencial: bool | Unset = False
    rotulo: str | Unset = ""

    def to_dict(self) -> dict[str, Any]:
        portal = self.portal

        usuario = self.usuario

        tipo: None | str | Unset
        if isinstance(self.tipo, Unset):
            tipo = UNSET
        else:
            tipo = self.tipo

        credencial: None | str | Unset
        if isinstance(self.credencial, Unset):
            credencial = UNSET
        else:
            credencial = self.credencial

        remover_credencial = self.remover_credencial

        rotulo = self.rotulo

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if portal is not UNSET:
            field_dict["portal"] = portal
        if usuario is not UNSET:
            field_dict["usuario"] = usuario
        if tipo is not UNSET:
            field_dict["tipo"] = tipo
        if credencial is not UNSET:
            field_dict["credencial"] = credencial
        if remover_credencial is not UNSET:
            field_dict["remover_credencial"] = remover_credencial
        if rotulo is not UNSET:
            field_dict["rotulo"] = rotulo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        portal = d.pop("portal", UNSET)

        usuario = d.pop("usuario", UNSET)

        def _parse_tipo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tipo = _parse_tipo(d.pop("tipo", UNSET))

        def _parse_credencial(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        credencial = _parse_credencial(d.pop("credencial", UNSET))

        remover_credencial = d.pop("remover_credencial", UNSET)

        rotulo = d.pop("rotulo", UNSET)

        credencial_entrada = cls(
            portal=portal,
            usuario=usuario,
            tipo=tipo,
            credencial=credencial,
            remover_credencial=remover_credencial,
            rotulo=rotulo,
        )

        return credencial_entrada
