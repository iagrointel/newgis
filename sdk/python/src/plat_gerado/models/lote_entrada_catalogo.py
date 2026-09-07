from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="LoteEntradaCatalogo")


@_attrs_define
class LoteEntradaCatalogo:
    """
    Attributes:
        ids (list[str]):
        acao (str):
        pasta_id (None | str | Unset):
        tags (list[str] | None | Unset):
        de (None | str | Unset):
        para (None | str | Unset):
        categorias (list[str] | None | Unset):
        status (None | str | Unset):
        acesso (None | str | Unset):
        grupos (list[str] | None | Unset):
        cascata (bool | Unset):  Default: False.
    """

    ids: list[str]
    acao: str
    pasta_id: None | str | Unset = UNSET
    tags: list[str] | None | Unset = UNSET
    de: None | str | Unset = UNSET
    para: None | str | Unset = UNSET
    categorias: list[str] | None | Unset = UNSET
    status: None | str | Unset = UNSET
    acesso: None | str | Unset = UNSET
    grupos: list[str] | None | Unset = UNSET
    cascata: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        ids = self.ids

        acao = self.acao

        pasta_id: None | str | Unset
        if isinstance(self.pasta_id, Unset):
            pasta_id = UNSET
        else:
            pasta_id = self.pasta_id

        tags: list[str] | None | Unset
        if isinstance(self.tags, Unset):
            tags = UNSET
        elif isinstance(self.tags, list):
            tags = self.tags

        else:
            tags = self.tags

        de: None | str | Unset
        if isinstance(self.de, Unset):
            de = UNSET
        else:
            de = self.de

        para: None | str | Unset
        if isinstance(self.para, Unset):
            para = UNSET
        else:
            para = self.para

        categorias: list[str] | None | Unset
        if isinstance(self.categorias, Unset):
            categorias = UNSET
        elif isinstance(self.categorias, list):
            categorias = self.categorias

        else:
            categorias = self.categorias

        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        else:
            status = self.status

        acesso: None | str | Unset
        if isinstance(self.acesso, Unset):
            acesso = UNSET
        else:
            acesso = self.acesso

        grupos: list[str] | None | Unset
        if isinstance(self.grupos, Unset):
            grupos = UNSET
        elif isinstance(self.grupos, list):
            grupos = self.grupos

        else:
            grupos = self.grupos

        cascata = self.cascata

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "ids": ids,
                "acao": acao,
            }
        )
        if pasta_id is not UNSET:
            field_dict["pasta_id"] = pasta_id
        if tags is not UNSET:
            field_dict["tags"] = tags
        if de is not UNSET:
            field_dict["de"] = de
        if para is not UNSET:
            field_dict["para"] = para
        if categorias is not UNSET:
            field_dict["categorias"] = categorias
        if status is not UNSET:
            field_dict["status"] = status
        if acesso is not UNSET:
            field_dict["acesso"] = acesso
        if grupos is not UNSET:
            field_dict["grupos"] = grupos
        if cascata is not UNSET:
            field_dict["cascata"] = cascata

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        ids = cast(list[str], d.pop("ids"))

        acao = d.pop("acao")

        def _parse_pasta_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pasta_id = _parse_pasta_id(d.pop("pasta_id", UNSET))

        def _parse_tags(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                tags_type_0 = cast(list[str], data)

                return tags_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        tags = _parse_tags(d.pop("tags", UNSET))

        def _parse_de(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        de = _parse_de(d.pop("de", UNSET))

        def _parse_para(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        para = _parse_para(d.pop("para", UNSET))

        def _parse_categorias(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                categorias_type_0 = cast(list[str], data)

                return categorias_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        categorias = _parse_categorias(d.pop("categorias", UNSET))

        def _parse_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        status = _parse_status(d.pop("status", UNSET))

        def _parse_acesso(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        acesso = _parse_acesso(d.pop("acesso", UNSET))

        def _parse_grupos(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                grupos_type_0 = cast(list[str], data)

                return grupos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        grupos = _parse_grupos(d.pop("grupos", UNSET))

        cascata = d.pop("cascata", UNSET)

        lote_entrada_catalogo = cls(
            ids=ids,
            acao=acao,
            pasta_id=pasta_id,
            tags=tags,
            de=de,
            para=para,
            categorias=categorias,
            status=status,
            acesso=acesso,
            grupos=grupos,
            cascata=cascata,
        )

        return lote_entrada_catalogo
