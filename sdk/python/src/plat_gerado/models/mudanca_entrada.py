from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.mudanca_entrada_tipo import MudancaEntradaTipo
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.campo_entrada import CampoEntrada


T = TypeVar("T", bound="MudancaEntrada")


@_attrs_define
class MudancaEntrada:
    """
    Attributes:
        tipo (MudancaEntradaTipo):
        campo (None | str | Unset):
        novo_campo (CampoEntrada | None | Unset):
        novo_alias (None | str | Unset):
        novo_tamanho (int | None | Unset):
        novo_tipo (None | str | Unset):
    """

    tipo: MudancaEntradaTipo
    campo: None | str | Unset = UNSET
    novo_campo: CampoEntrada | None | Unset = UNSET
    novo_alias: None | str | Unset = UNSET
    novo_tamanho: int | None | Unset = UNSET
    novo_tipo: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.campo_entrada import CampoEntrada  # noqa: PLC0415

        tipo = self.tipo.value

        campo: None | str | Unset
        if isinstance(self.campo, Unset):
            campo = UNSET
        else:
            campo = self.campo

        novo_campo: dict[str, Any] | None | Unset
        if isinstance(self.novo_campo, Unset):
            novo_campo = UNSET
        elif isinstance(self.novo_campo, CampoEntrada):
            novo_campo = self.novo_campo.to_dict()
        else:
            novo_campo = self.novo_campo

        novo_alias: None | str | Unset
        if isinstance(self.novo_alias, Unset):
            novo_alias = UNSET
        else:
            novo_alias = self.novo_alias

        novo_tamanho: int | None | Unset
        if isinstance(self.novo_tamanho, Unset):
            novo_tamanho = UNSET
        else:
            novo_tamanho = self.novo_tamanho

        novo_tipo: None | str | Unset
        if isinstance(self.novo_tipo, Unset):
            novo_tipo = UNSET
        else:
            novo_tipo = self.novo_tipo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "tipo": tipo,
            }
        )
        if campo is not UNSET:
            field_dict["campo"] = campo
        if novo_campo is not UNSET:
            field_dict["novo_campo"] = novo_campo
        if novo_alias is not UNSET:
            field_dict["novo_alias"] = novo_alias
        if novo_tamanho is not UNSET:
            field_dict["novo_tamanho"] = novo_tamanho
        if novo_tipo is not UNSET:
            field_dict["novo_tipo"] = novo_tipo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.campo_entrada import CampoEntrada  # noqa: PLC0415

        d = dict(src_dict)
        tipo = MudancaEntradaTipo(d.pop("tipo"))

        def _parse_campo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        campo = _parse_campo(d.pop("campo", UNSET))

        def _parse_novo_campo(data: object) -> CampoEntrada | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                novo_campo_type_0 = CampoEntrada.from_dict(data)

                return novo_campo_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CampoEntrada | None | Unset, data)

        novo_campo = _parse_novo_campo(d.pop("novo_campo", UNSET))

        def _parse_novo_alias(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        novo_alias = _parse_novo_alias(d.pop("novo_alias", UNSET))

        def _parse_novo_tamanho(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        novo_tamanho = _parse_novo_tamanho(d.pop("novo_tamanho", UNSET))

        def _parse_novo_tipo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        novo_tipo = _parse_novo_tipo(d.pop("novo_tipo", UNSET))

        mudanca_entrada = cls(
            tipo=tipo,
            campo=campo,
            novo_campo=novo_campo,
            novo_alias=novo_alias,
            novo_tamanho=novo_tamanho,
            novo_tipo=novo_tipo,
        )

        return mudanca_entrada
