from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="TenantCotasEntrada")


@_attrs_define
class TenantCotasEntrada:
    """POST /api/plataforma/inquilinos/{id}/cotas (só superadmin; item L0-07-c-cotas-uso): todo campo é
    opcional — só o que vier não-None muda. cota_bytes_teto/cota_usuarios_teto são o TETO que o próprio
    inquilino (PUT /api/org) nunca ultrapassa; sem valor aqui o teto vigente não muda.

        Attributes:
            cota_bytes (int | None | Unset):
            cota_usuarios (int | None | Unset):
            cota_itens (int | None | Unset):
            cota_jobs_dia (int | None | Unset):
            cota_bytes_teto (int | None | Unset):
            cota_usuarios_teto (int | None | Unset):
    """

    cota_bytes: int | None | Unset = UNSET
    cota_usuarios: int | None | Unset = UNSET
    cota_itens: int | None | Unset = UNSET
    cota_jobs_dia: int | None | Unset = UNSET
    cota_bytes_teto: int | None | Unset = UNSET
    cota_usuarios_teto: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        cota_bytes: int | None | Unset
        if isinstance(self.cota_bytes, Unset):
            cota_bytes = UNSET
        else:
            cota_bytes = self.cota_bytes

        cota_usuarios: int | None | Unset
        if isinstance(self.cota_usuarios, Unset):
            cota_usuarios = UNSET
        else:
            cota_usuarios = self.cota_usuarios

        cota_itens: int | None | Unset
        if isinstance(self.cota_itens, Unset):
            cota_itens = UNSET
        else:
            cota_itens = self.cota_itens

        cota_jobs_dia: int | None | Unset
        if isinstance(self.cota_jobs_dia, Unset):
            cota_jobs_dia = UNSET
        else:
            cota_jobs_dia = self.cota_jobs_dia

        cota_bytes_teto: int | None | Unset
        if isinstance(self.cota_bytes_teto, Unset):
            cota_bytes_teto = UNSET
        else:
            cota_bytes_teto = self.cota_bytes_teto

        cota_usuarios_teto: int | None | Unset
        if isinstance(self.cota_usuarios_teto, Unset):
            cota_usuarios_teto = UNSET
        else:
            cota_usuarios_teto = self.cota_usuarios_teto

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if cota_bytes is not UNSET:
            field_dict["cota_bytes"] = cota_bytes
        if cota_usuarios is not UNSET:
            field_dict["cota_usuarios"] = cota_usuarios
        if cota_itens is not UNSET:
            field_dict["cota_itens"] = cota_itens
        if cota_jobs_dia is not UNSET:
            field_dict["cota_jobs_dia"] = cota_jobs_dia
        if cota_bytes_teto is not UNSET:
            field_dict["cota_bytes_teto"] = cota_bytes_teto
        if cota_usuarios_teto is not UNSET:
            field_dict["cota_usuarios_teto"] = cota_usuarios_teto

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_cota_bytes(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        cota_bytes = _parse_cota_bytes(d.pop("cota_bytes", UNSET))

        def _parse_cota_usuarios(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        cota_usuarios = _parse_cota_usuarios(d.pop("cota_usuarios", UNSET))

        def _parse_cota_itens(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        cota_itens = _parse_cota_itens(d.pop("cota_itens", UNSET))

        def _parse_cota_jobs_dia(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        cota_jobs_dia = _parse_cota_jobs_dia(d.pop("cota_jobs_dia", UNSET))

        def _parse_cota_bytes_teto(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        cota_bytes_teto = _parse_cota_bytes_teto(d.pop("cota_bytes_teto", UNSET))

        def _parse_cota_usuarios_teto(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        cota_usuarios_teto = _parse_cota_usuarios_teto(d.pop("cota_usuarios_teto", UNSET))

        tenant_cotas_entrada = cls(
            cota_bytes=cota_bytes,
            cota_usuarios=cota_usuarios,
            cota_itens=cota_itens,
            cota_jobs_dia=cota_jobs_dia,
            cota_bytes_teto=cota_bytes_teto,
            cota_usuarios_teto=cota_usuarios_teto,
        )

        return tenant_cotas_entrada
