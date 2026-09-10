from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.conexao_entrada_config import ConexaoEntradaConfig


T = TypeVar("T", bound="ConexaoEntrada")


@_attrs_define
class ConexaoEntrada:
    """
    Attributes:
        tipo (str):
        nome (str):
        url (str):
        modo (str | Unset):  Default: 'referenciada'.
        config (ConexaoEntradaConfig | Unset):
        credencial (None | str | Unset):
    """

    tipo: str
    nome: str
    url: str
    modo: str | Unset = "referenciada"
    config: ConexaoEntradaConfig | Unset = UNSET
    credencial: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        tipo = self.tipo

        nome = self.nome

        url = self.url

        modo = self.modo

        config: dict[str, Any] | Unset = UNSET
        if not isinstance(self.config, Unset):
            config = self.config.to_dict()

        credencial: None | str | Unset
        if isinstance(self.credencial, Unset):
            credencial = UNSET
        else:
            credencial = self.credencial

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "tipo": tipo,
                "nome": nome,
                "url": url,
            }
        )
        if modo is not UNSET:
            field_dict["modo"] = modo
        if config is not UNSET:
            field_dict["config"] = config
        if credencial is not UNSET:
            field_dict["credencial"] = credencial

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conexao_entrada_config import ConexaoEntradaConfig  # noqa: PLC0415

        d = dict(src_dict)
        tipo = d.pop("tipo")

        nome = d.pop("nome")

        url = d.pop("url")

        modo = d.pop("modo", UNSET)

        _config = d.pop("config", UNSET)
        config: ConexaoEntradaConfig | Unset
        if isinstance(_config, Unset):
            config = UNSET
        else:
            config = ConexaoEntradaConfig.from_dict(_config)

        def _parse_credencial(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        credencial = _parse_credencial(d.pop("credencial", UNSET))

        conexao_entrada = cls(
            tipo=tipo,
            nome=nome,
            url=url,
            modo=modo,
            config=config,
            credencial=credencial,
        )

        return conexao_entrada
