from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.fonte_entrada_config import FonteEntradaConfig
    from ..models.fonte_entrada_mapeamento import FonteEntradaMapeamento


T = TypeVar("T", bound="FonteEntrada")


@_attrs_define
class FonteEntrada:
    """
    Attributes:
        tipo (str):
        nome (str):
        config (FonteEntradaConfig | Unset):
        mapeamento (FonteEntradaMapeamento | Unset):
        filtro (None | str | Unset):
        limite_eventos_s (int | Unset):  Default: 1000.
        credencial (None | str | Unset):
    """

    tipo: str
    nome: str
    config: FonteEntradaConfig | Unset = UNSET
    mapeamento: FonteEntradaMapeamento | Unset = UNSET
    filtro: None | str | Unset = UNSET
    limite_eventos_s: int | Unset = 1000
    credencial: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        tipo = self.tipo

        nome = self.nome

        config: dict[str, Any] | Unset = UNSET
        if not isinstance(self.config, Unset):
            config = self.config.to_dict()

        mapeamento: dict[str, Any] | Unset = UNSET
        if not isinstance(self.mapeamento, Unset):
            mapeamento = self.mapeamento.to_dict()

        filtro: None | str | Unset
        if isinstance(self.filtro, Unset):
            filtro = UNSET
        else:
            filtro = self.filtro

        limite_eventos_s = self.limite_eventos_s

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
            }
        )
        if config is not UNSET:
            field_dict["config"] = config
        if mapeamento is not UNSET:
            field_dict["mapeamento"] = mapeamento
        if filtro is not UNSET:
            field_dict["filtro"] = filtro
        if limite_eventos_s is not UNSET:
            field_dict["limite_eventos_s"] = limite_eventos_s
        if credencial is not UNSET:
            field_dict["credencial"] = credencial

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.fonte_entrada_config import FonteEntradaConfig  # noqa: PLC0415
        from ..models.fonte_entrada_mapeamento import FonteEntradaMapeamento  # noqa: PLC0415

        d = dict(src_dict)
        tipo = d.pop("tipo")

        nome = d.pop("nome")

        _config = d.pop("config", UNSET)
        config: FonteEntradaConfig | Unset
        if isinstance(_config, Unset):
            config = UNSET
        else:
            config = FonteEntradaConfig.from_dict(_config)

        _mapeamento = d.pop("mapeamento", UNSET)
        mapeamento: FonteEntradaMapeamento | Unset
        if isinstance(_mapeamento, Unset):
            mapeamento = UNSET
        else:
            mapeamento = FonteEntradaMapeamento.from_dict(_mapeamento)

        def _parse_filtro(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        filtro = _parse_filtro(d.pop("filtro", UNSET))

        limite_eventos_s = d.pop("limite_eventos_s", UNSET)

        def _parse_credencial(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        credencial = _parse_credencial(d.pop("credencial", UNSET))

        fonte_entrada = cls(
            tipo=tipo,
            nome=nome,
            config=config,
            mapeamento=mapeamento,
            filtro=filtro,
            limite_eventos_s=limite_eventos_s,
            credencial=credencial,
        )

        return fonte_entrada
