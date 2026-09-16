from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.fonte_editar_config_type_0 import FonteEditarConfigType0
    from ..models.fonte_editar_mapeamento_type_0 import FonteEditarMapeamentoType0


T = TypeVar("T", bound="FonteEditar")


@_attrs_define
class FonteEditar:
    """
    Attributes:
        nome (None | str | Unset):
        estado (None | str | Unset):
        config (FonteEditarConfigType0 | None | Unset):
        mapeamento (FonteEditarMapeamentoType0 | None | Unset):
        filtro (None | str | Unset):
        remover_filtro (bool | Unset):  Default: False.
        limite_eventos_s (int | None | Unset):
        credencial (None | str | Unset):
        remover_credencial (bool | Unset):  Default: False.
    """

    nome: None | str | Unset = UNSET
    estado: None | str | Unset = UNSET
    config: FonteEditarConfigType0 | None | Unset = UNSET
    mapeamento: FonteEditarMapeamentoType0 | None | Unset = UNSET
    filtro: None | str | Unset = UNSET
    remover_filtro: bool | Unset = False
    limite_eventos_s: int | None | Unset = UNSET
    credencial: None | str | Unset = UNSET
    remover_credencial: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        from ..models.fonte_editar_config_type_0 import FonteEditarConfigType0  # noqa: PLC0415
        from ..models.fonte_editar_mapeamento_type_0 import FonteEditarMapeamentoType0  # noqa: PLC0415

        nome: None | str | Unset
        if isinstance(self.nome, Unset):
            nome = UNSET
        else:
            nome = self.nome

        estado: None | str | Unset
        if isinstance(self.estado, Unset):
            estado = UNSET
        else:
            estado = self.estado

        config: dict[str, Any] | None | Unset
        if isinstance(self.config, Unset):
            config = UNSET
        elif isinstance(self.config, FonteEditarConfigType0):
            config = self.config.to_dict()
        else:
            config = self.config

        mapeamento: dict[str, Any] | None | Unset
        if isinstance(self.mapeamento, Unset):
            mapeamento = UNSET
        elif isinstance(self.mapeamento, FonteEditarMapeamentoType0):
            mapeamento = self.mapeamento.to_dict()
        else:
            mapeamento = self.mapeamento

        filtro: None | str | Unset
        if isinstance(self.filtro, Unset):
            filtro = UNSET
        else:
            filtro = self.filtro

        remover_filtro = self.remover_filtro

        limite_eventos_s: int | None | Unset
        if isinstance(self.limite_eventos_s, Unset):
            limite_eventos_s = UNSET
        else:
            limite_eventos_s = self.limite_eventos_s

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
        if estado is not UNSET:
            field_dict["estado"] = estado
        if config is not UNSET:
            field_dict["config"] = config
        if mapeamento is not UNSET:
            field_dict["mapeamento"] = mapeamento
        if filtro is not UNSET:
            field_dict["filtro"] = filtro
        if remover_filtro is not UNSET:
            field_dict["remover_filtro"] = remover_filtro
        if limite_eventos_s is not UNSET:
            field_dict["limite_eventos_s"] = limite_eventos_s
        if credencial is not UNSET:
            field_dict["credencial"] = credencial
        if remover_credencial is not UNSET:
            field_dict["remover_credencial"] = remover_credencial

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.fonte_editar_config_type_0 import FonteEditarConfigType0  # noqa: PLC0415
        from ..models.fonte_editar_mapeamento_type_0 import FonteEditarMapeamentoType0  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome = _parse_nome(d.pop("nome", UNSET))

        def _parse_estado(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        estado = _parse_estado(d.pop("estado", UNSET))

        def _parse_config(data: object) -> FonteEditarConfigType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_type_0 = FonteEditarConfigType0.from_dict(data)

                return config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FonteEditarConfigType0 | None | Unset, data)

        config = _parse_config(d.pop("config", UNSET))

        def _parse_mapeamento(data: object) -> FonteEditarMapeamentoType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                mapeamento_type_0 = FonteEditarMapeamentoType0.from_dict(data)

                return mapeamento_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FonteEditarMapeamentoType0 | None | Unset, data)

        mapeamento = _parse_mapeamento(d.pop("mapeamento", UNSET))

        def _parse_filtro(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        filtro = _parse_filtro(d.pop("filtro", UNSET))

        remover_filtro = d.pop("remover_filtro", UNSET)

        def _parse_limite_eventos_s(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        limite_eventos_s = _parse_limite_eventos_s(d.pop("limite_eventos_s", UNSET))

        def _parse_credencial(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        credencial = _parse_credencial(d.pop("credencial", UNSET))

        remover_credencial = d.pop("remover_credencial", UNSET)

        fonte_editar = cls(
            nome=nome,
            estado=estado,
            config=config,
            mapeamento=mapeamento,
            filtro=filtro,
            remover_filtro=remover_filtro,
            limite_eventos_s=limite_eventos_s,
            credencial=credencial,
            remover_credencial=remover_credencial,
        )

        return fonte_editar
