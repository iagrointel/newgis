from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.token_dono import TokenDono
    from ..models.token_restricao import TokenRestricao


T = TypeVar("T", bound="Token")


@_attrs_define
class Token:
    """
    Attributes:
        id (int):
        nome (str):
        prefixo (str):
        escopos (list[str]):
        restricao (TokenRestricao):
        criado_em (None | str):
        expira_em (None | str):
        revogado_em (None | str):
        ultimo_uso (None | str):
        ultimo_ip (None | str):
        dono (TokenDono):
        renovado_por (int | None):
        acessos_30d (int | None | Unset):
        ultimo_status (int | None | Unset):
    """

    id: int
    nome: str
    prefixo: str
    escopos: list[str]
    restricao: TokenRestricao
    criado_em: None | str
    expira_em: None | str
    revogado_em: None | str
    ultimo_uso: None | str
    ultimo_ip: None | str
    dono: TokenDono
    renovado_por: int | None
    acessos_30d: int | None | Unset = UNSET
    ultimo_status: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        nome = self.nome

        prefixo = self.prefixo

        escopos = self.escopos

        restricao = self.restricao.to_dict()

        criado_em: None | str
        criado_em = self.criado_em

        expira_em: None | str
        expira_em = self.expira_em

        revogado_em: None | str
        revogado_em = self.revogado_em

        ultimo_uso: None | str
        ultimo_uso = self.ultimo_uso

        ultimo_ip: None | str
        ultimo_ip = self.ultimo_ip

        dono = self.dono.to_dict()

        renovado_por: int | None
        renovado_por = self.renovado_por

        acessos_30d: int | None | Unset
        if isinstance(self.acessos_30d, Unset):
            acessos_30d = UNSET
        else:
            acessos_30d = self.acessos_30d

        ultimo_status: int | None | Unset
        if isinstance(self.ultimo_status, Unset):
            ultimo_status = UNSET
        else:
            ultimo_status = self.ultimo_status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nome": nome,
                "prefixo": prefixo,
                "escopos": escopos,
                "restricao": restricao,
                "criado_em": criado_em,
                "expira_em": expira_em,
                "revogado_em": revogado_em,
                "ultimo_uso": ultimo_uso,
                "ultimo_ip": ultimo_ip,
                "dono": dono,
                "renovado_por": renovado_por,
            }
        )
        if acessos_30d is not UNSET:
            field_dict["acessos_30d"] = acessos_30d
        if ultimo_status is not UNSET:
            field_dict["ultimo_status"] = ultimo_status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.token_dono import TokenDono  # noqa: PLC0415
        from ..models.token_restricao import TokenRestricao  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        nome = d.pop("nome")

        prefixo = d.pop("prefixo")

        escopos = cast(list[str], d.pop("escopos"))

        restricao = TokenRestricao.from_dict(d.pop("restricao"))

        def _parse_criado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        criado_em = _parse_criado_em(d.pop("criado_em"))

        def _parse_expira_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        expira_em = _parse_expira_em(d.pop("expira_em"))

        def _parse_revogado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        revogado_em = _parse_revogado_em(d.pop("revogado_em"))

        def _parse_ultimo_uso(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        ultimo_uso = _parse_ultimo_uso(d.pop("ultimo_uso"))

        def _parse_ultimo_ip(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        ultimo_ip = _parse_ultimo_ip(d.pop("ultimo_ip"))

        dono = TokenDono.from_dict(d.pop("dono"))

        def _parse_renovado_por(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        renovado_por = _parse_renovado_por(d.pop("renovado_por"))

        def _parse_acessos_30d(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        acessos_30d = _parse_acessos_30d(d.pop("acessos_30d", UNSET))

        def _parse_ultimo_status(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ultimo_status = _parse_ultimo_status(d.pop("ultimo_status", UNSET))

        token = cls(
            id=id,
            nome=nome,
            prefixo=prefixo,
            escopos=escopos,
            restricao=restricao,
            criado_em=criado_em,
            expira_em=expira_em,
            revogado_em=revogado_em,
            ultimo_uso=ultimo_uso,
            ultimo_ip=ultimo_ip,
            dono=dono,
            renovado_por=renovado_por,
            acessos_30d=acessos_30d,
            ultimo_status=ultimo_status,
        )

        token.additional_properties = d
        return token

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
