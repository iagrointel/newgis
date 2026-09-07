from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="SMTPEntrada")


@_attrs_define
class SMTPEntrada:
    """PUT /api/org/smtp. `senha` ausente preserva a cifra atual; `senha=""` (string vazia) apaga a senha
    guardada sem apagar o resto; `host=""` some com o override do inquilino inteiro (volta a usar a
    instalação, se houver, ou o caminho manual).

        Attributes:
            host (str | Unset):  Default: ''.
            porta (int | Unset):  Default: 587.
            tls (bool | Unset):  Default: True.
            usuario (str | Unset):  Default: ''.
            senha (None | str | Unset):
            remetente (str | Unset):  Default: ''.
            rotulo (str | Unset):  Default: ''.
    """

    host: str | Unset = ""
    porta: int | Unset = 587
    tls: bool | Unset = True
    usuario: str | Unset = ""
    senha: None | str | Unset = UNSET
    remetente: str | Unset = ""
    rotulo: str | Unset = ""

    def to_dict(self) -> dict[str, Any]:
        host = self.host

        porta = self.porta

        tls = self.tls

        usuario = self.usuario

        senha: None | str | Unset
        if isinstance(self.senha, Unset):
            senha = UNSET
        else:
            senha = self.senha

        remetente = self.remetente

        rotulo = self.rotulo

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if host is not UNSET:
            field_dict["host"] = host
        if porta is not UNSET:
            field_dict["porta"] = porta
        if tls is not UNSET:
            field_dict["tls"] = tls
        if usuario is not UNSET:
            field_dict["usuario"] = usuario
        if senha is not UNSET:
            field_dict["senha"] = senha
        if remetente is not UNSET:
            field_dict["remetente"] = remetente
        if rotulo is not UNSET:
            field_dict["rotulo"] = rotulo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        host = d.pop("host", UNSET)

        porta = d.pop("porta", UNSET)

        tls = d.pop("tls", UNSET)

        usuario = d.pop("usuario", UNSET)

        def _parse_senha(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        senha = _parse_senha(d.pop("senha", UNSET))

        remetente = d.pop("remetente", UNSET)

        rotulo = d.pop("rotulo", UNSET)

        smtp_entrada = cls(
            host=host,
            porta=porta,
            tls=tls,
            usuario=usuario,
            senha=senha,
            remetente=remetente,
            rotulo=rotulo,
        )

        return smtp_entrada
