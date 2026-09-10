from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.usuario_papel_type_0 import UsuarioPapelType0


T = TypeVar("T", bound="Usuario")


@_attrs_define
class Usuario:
    """
    Attributes:
        id (int):
        login (str):
        nome (str):
        perfil (str):
        ativo (bool):
        origem (str):
        papel (None | Unset | UsuarioPapelType0):
        ultimo_login (None | str | Unset):
        criado_em (None | str | Unset):
        email (None | str | Unset):
        superadmin (bool | None | Unset):
        totp_ativo (bool | None | Unset):
        trocar_senha (bool | None | Unset):
        bloqueado_ate (None | str | Unset):
        ultimo_ip (None | str | Unset):
        codigos_recuperacao_restantes (int | None | Unset):
    """

    id: int
    login: str
    nome: str
    perfil: str
    ativo: bool
    origem: str
    papel: None | Unset | UsuarioPapelType0 = UNSET
    ultimo_login: None | str | Unset = UNSET
    criado_em: None | str | Unset = UNSET
    email: None | str | Unset = UNSET
    superadmin: bool | None | Unset = UNSET
    totp_ativo: bool | None | Unset = UNSET
    trocar_senha: bool | None | Unset = UNSET
    bloqueado_ate: None | str | Unset = UNSET
    ultimo_ip: None | str | Unset = UNSET
    codigos_recuperacao_restantes: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.usuario_papel_type_0 import UsuarioPapelType0  # noqa: PLC0415

        id = self.id

        login = self.login

        nome = self.nome

        perfil = self.perfil

        ativo = self.ativo

        origem = self.origem

        papel: dict[str, Any] | None | Unset
        if isinstance(self.papel, Unset):
            papel = UNSET
        elif isinstance(self.papel, UsuarioPapelType0):
            papel = self.papel.to_dict()
        else:
            papel = self.papel

        ultimo_login: None | str | Unset
        if isinstance(self.ultimo_login, Unset):
            ultimo_login = UNSET
        else:
            ultimo_login = self.ultimo_login

        criado_em: None | str | Unset
        if isinstance(self.criado_em, Unset):
            criado_em = UNSET
        else:
            criado_em = self.criado_em

        email: None | str | Unset
        if isinstance(self.email, Unset):
            email = UNSET
        else:
            email = self.email

        superadmin: bool | None | Unset
        if isinstance(self.superadmin, Unset):
            superadmin = UNSET
        else:
            superadmin = self.superadmin

        totp_ativo: bool | None | Unset
        if isinstance(self.totp_ativo, Unset):
            totp_ativo = UNSET
        else:
            totp_ativo = self.totp_ativo

        trocar_senha: bool | None | Unset
        if isinstance(self.trocar_senha, Unset):
            trocar_senha = UNSET
        else:
            trocar_senha = self.trocar_senha

        bloqueado_ate: None | str | Unset
        if isinstance(self.bloqueado_ate, Unset):
            bloqueado_ate = UNSET
        else:
            bloqueado_ate = self.bloqueado_ate

        ultimo_ip: None | str | Unset
        if isinstance(self.ultimo_ip, Unset):
            ultimo_ip = UNSET
        else:
            ultimo_ip = self.ultimo_ip

        codigos_recuperacao_restantes: int | None | Unset
        if isinstance(self.codigos_recuperacao_restantes, Unset):
            codigos_recuperacao_restantes = UNSET
        else:
            codigos_recuperacao_restantes = self.codigos_recuperacao_restantes

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "login": login,
                "nome": nome,
                "perfil": perfil,
                "ativo": ativo,
                "origem": origem,
            }
        )
        if papel is not UNSET:
            field_dict["papel"] = papel
        if ultimo_login is not UNSET:
            field_dict["ultimo_login"] = ultimo_login
        if criado_em is not UNSET:
            field_dict["criado_em"] = criado_em
        if email is not UNSET:
            field_dict["email"] = email
        if superadmin is not UNSET:
            field_dict["superadmin"] = superadmin
        if totp_ativo is not UNSET:
            field_dict["totp_ativo"] = totp_ativo
        if trocar_senha is not UNSET:
            field_dict["trocar_senha"] = trocar_senha
        if bloqueado_ate is not UNSET:
            field_dict["bloqueado_ate"] = bloqueado_ate
        if ultimo_ip is not UNSET:
            field_dict["ultimo_ip"] = ultimo_ip
        if codigos_recuperacao_restantes is not UNSET:
            field_dict["codigos_recuperacao_restantes"] = codigos_recuperacao_restantes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.usuario_papel_type_0 import UsuarioPapelType0  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        login = d.pop("login")

        nome = d.pop("nome")

        perfil = d.pop("perfil")

        ativo = d.pop("ativo")

        origem = d.pop("origem")

        def _parse_papel(data: object) -> None | Unset | UsuarioPapelType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                papel_type_0 = UsuarioPapelType0.from_dict(data)

                return papel_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsuarioPapelType0, data)

        papel = _parse_papel(d.pop("papel", UNSET))

        def _parse_ultimo_login(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ultimo_login = _parse_ultimo_login(d.pop("ultimo_login", UNSET))

        def _parse_criado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        criado_em = _parse_criado_em(d.pop("criado_em", UNSET))

        def _parse_email(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        email = _parse_email(d.pop("email", UNSET))

        def _parse_superadmin(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        superadmin = _parse_superadmin(d.pop("superadmin", UNSET))

        def _parse_totp_ativo(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        totp_ativo = _parse_totp_ativo(d.pop("totp_ativo", UNSET))

        def _parse_trocar_senha(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        trocar_senha = _parse_trocar_senha(d.pop("trocar_senha", UNSET))

        def _parse_bloqueado_ate(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        bloqueado_ate = _parse_bloqueado_ate(d.pop("bloqueado_ate", UNSET))

        def _parse_ultimo_ip(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ultimo_ip = _parse_ultimo_ip(d.pop("ultimo_ip", UNSET))

        def _parse_codigos_recuperacao_restantes(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        codigos_recuperacao_restantes = _parse_codigos_recuperacao_restantes(
            d.pop("codigos_recuperacao_restantes", UNSET)
        )

        usuario = cls(
            id=id,
            login=login,
            nome=nome,
            perfil=perfil,
            ativo=ativo,
            origem=origem,
            papel=papel,
            ultimo_login=ultimo_login,
            criado_em=criado_em,
            email=email,
            superadmin=superadmin,
            totp_ativo=totp_ativo,
            trocar_senha=trocar_senha,
            bloqueado_ate=bloqueado_ate,
            ultimo_ip=ultimo_ip,
            codigos_recuperacao_restantes=codigos_recuperacao_restantes,
        )

        usuario.additional_properties = d
        return usuario

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
