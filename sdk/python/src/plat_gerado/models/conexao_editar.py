from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.conexao_editar_config_type_0 import ConexaoEditarConfigType0


T = TypeVar("T", bound="ConexaoEditar")


@_attrs_define
class ConexaoEditar:
    """
    Attributes:
        nome (None | str | Unset):
        url (None | str | Unset):
        modo (None | str | Unset):
        config (ConexaoEditarConfigType0 | None | Unset):
        credencial (None | str | Unset):
        remover_credencial (bool | Unset):  Default: False.
    """

    nome: None | str | Unset = UNSET
    url: None | str | Unset = UNSET
    modo: None | str | Unset = UNSET
    config: ConexaoEditarConfigType0 | None | Unset = UNSET
    credencial: None | str | Unset = UNSET
    remover_credencial: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        from ..models.conexao_editar_config_type_0 import ConexaoEditarConfigType0  # noqa: PLC0415

        nome: None | str | Unset
        if isinstance(self.nome, Unset):
            nome = UNSET
        else:
            nome = self.nome

        url: None | str | Unset
        if isinstance(self.url, Unset):
            url = UNSET
        else:
            url = self.url

        modo: None | str | Unset
        if isinstance(self.modo, Unset):
            modo = UNSET
        else:
            modo = self.modo

        config: dict[str, Any] | None | Unset
        if isinstance(self.config, Unset):
            config = UNSET
        elif isinstance(self.config, ConexaoEditarConfigType0):
            config = self.config.to_dict()
        else:
            config = self.config

        credencial: None | str | Unset
        if isinstance(self.credencial, Unset):
            credencial = UNSET
        else:
            credencial = self.credencial

        remover_credencial = self.remover_credencial

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if nome is not UNSET:
            field_dict["nome"] = nome
        if url is not UNSET:
            field_dict["url"] = url
        if modo is not UNSET:
            field_dict["modo"] = modo
        if config is not UNSET:
            field_dict["config"] = config
        if credencial is not UNSET:
            field_dict["credencial"] = credencial
        if remover_credencial is not UNSET:
            field_dict["remover_credencial"] = remover_credencial

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conexao_editar_config_type_0 import ConexaoEditarConfigType0  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome = _parse_nome(d.pop("nome", UNSET))

        def _parse_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        url = _parse_url(d.pop("url", UNSET))

        def _parse_modo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        modo = _parse_modo(d.pop("modo", UNSET))

        def _parse_config(data: object) -> ConexaoEditarConfigType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_type_0 = ConexaoEditarConfigType0.from_dict(data)

                return config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConexaoEditarConfigType0 | None | Unset, data)

        config = _parse_config(d.pop("config", UNSET))

        def _parse_credencial(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        credencial = _parse_credencial(d.pop("credencial", UNSET))

        remover_credencial = d.pop("remover_credencial", UNSET)

        conexao_editar = cls(
            nome=nome,
            url=url,
            modo=modo,
            config=config,
            credencial=credencial,
            remover_credencial=remover_credencial,
        )

        return conexao_editar
