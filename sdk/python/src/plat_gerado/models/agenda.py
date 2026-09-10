from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.agenda_parametros import AgendaParametros


T = TypeVar("T", bound="Agenda")


@_attrs_define
class Agenda:
    """
    Attributes:
        id (UUID):
        nome (str):
        tipo (str):
        parametros (AgendaParametros):
        cron (str):
        fuso (str):
        ativa (bool):
        falhas_seguidas (int):
        criado_em (str):
        proxima_em (None | str | Unset):
        ultima_em (None | str | Unset):
        ultimo_job_id (None | Unset | UUID):
        ultimo_estado (None | str | Unset):
        expira_em (None | str | Unset):
        usuario_id (int | None | Unset):
        usuario_login (None | str | Unset):
    """

    id: UUID
    nome: str
    tipo: str
    parametros: AgendaParametros
    cron: str
    fuso: str
    ativa: bool
    falhas_seguidas: int
    criado_em: str
    proxima_em: None | str | Unset = UNSET
    ultima_em: None | str | Unset = UNSET
    ultimo_job_id: None | Unset | UUID = UNSET
    ultimo_estado: None | str | Unset = UNSET
    expira_em: None | str | Unset = UNSET
    usuario_id: int | None | Unset = UNSET
    usuario_login: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        nome = self.nome

        tipo = self.tipo

        parametros = self.parametros.to_dict()

        cron = self.cron

        fuso = self.fuso

        ativa = self.ativa

        falhas_seguidas = self.falhas_seguidas

        criado_em = self.criado_em

        proxima_em: None | str | Unset
        if isinstance(self.proxima_em, Unset):
            proxima_em = UNSET
        else:
            proxima_em = self.proxima_em

        ultima_em: None | str | Unset
        if isinstance(self.ultima_em, Unset):
            ultima_em = UNSET
        else:
            ultima_em = self.ultima_em

        ultimo_job_id: None | str | Unset
        if isinstance(self.ultimo_job_id, Unset):
            ultimo_job_id = UNSET
        elif isinstance(self.ultimo_job_id, UUID):
            ultimo_job_id = str(self.ultimo_job_id)
        else:
            ultimo_job_id = self.ultimo_job_id

        ultimo_estado: None | str | Unset
        if isinstance(self.ultimo_estado, Unset):
            ultimo_estado = UNSET
        else:
            ultimo_estado = self.ultimo_estado

        expira_em: None | str | Unset
        if isinstance(self.expira_em, Unset):
            expira_em = UNSET
        else:
            expira_em = self.expira_em

        usuario_id: int | None | Unset
        if isinstance(self.usuario_id, Unset):
            usuario_id = UNSET
        else:
            usuario_id = self.usuario_id

        usuario_login: None | str | Unset
        if isinstance(self.usuario_login, Unset):
            usuario_login = UNSET
        else:
            usuario_login = self.usuario_login

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nome": nome,
                "tipo": tipo,
                "parametros": parametros,
                "cron": cron,
                "fuso": fuso,
                "ativa": ativa,
                "falhas_seguidas": falhas_seguidas,
                "criado_em": criado_em,
            }
        )
        if proxima_em is not UNSET:
            field_dict["proxima_em"] = proxima_em
        if ultima_em is not UNSET:
            field_dict["ultima_em"] = ultima_em
        if ultimo_job_id is not UNSET:
            field_dict["ultimo_job_id"] = ultimo_job_id
        if ultimo_estado is not UNSET:
            field_dict["ultimo_estado"] = ultimo_estado
        if expira_em is not UNSET:
            field_dict["expira_em"] = expira_em
        if usuario_id is not UNSET:
            field_dict["usuario_id"] = usuario_id
        if usuario_login is not UNSET:
            field_dict["usuario_login"] = usuario_login

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agenda_parametros import AgendaParametros  # noqa: PLC0415

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        nome = d.pop("nome")

        tipo = d.pop("tipo")

        parametros = AgendaParametros.from_dict(d.pop("parametros"))

        cron = d.pop("cron")

        fuso = d.pop("fuso")

        ativa = d.pop("ativa")

        falhas_seguidas = d.pop("falhas_seguidas")

        criado_em = d.pop("criado_em")

        def _parse_proxima_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        proxima_em = _parse_proxima_em(d.pop("proxima_em", UNSET))

        def _parse_ultima_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ultima_em = _parse_ultima_em(d.pop("ultima_em", UNSET))

        def _parse_ultimo_job_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                ultimo_job_id_type_0 = UUID(data)

                return ultimo_job_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        ultimo_job_id = _parse_ultimo_job_id(d.pop("ultimo_job_id", UNSET))

        def _parse_ultimo_estado(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ultimo_estado = _parse_ultimo_estado(d.pop("ultimo_estado", UNSET))

        def _parse_expira_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        expira_em = _parse_expira_em(d.pop("expira_em", UNSET))

        def _parse_usuario_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        usuario_id = _parse_usuario_id(d.pop("usuario_id", UNSET))

        def _parse_usuario_login(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        usuario_login = _parse_usuario_login(d.pop("usuario_login", UNSET))

        agenda = cls(
            id=id,
            nome=nome,
            tipo=tipo,
            parametros=parametros,
            cron=cron,
            fuso=fuso,
            ativa=ativa,
            falhas_seguidas=falhas_seguidas,
            criado_em=criado_em,
            proxima_em=proxima_em,
            ultima_em=ultima_em,
            ultimo_job_id=ultimo_job_id,
            ultimo_estado=ultimo_estado,
            expira_em=expira_em,
            usuario_id=usuario_id,
            usuario_login=usuario_login,
        )

        agenda.additional_properties = d
        return agenda

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
