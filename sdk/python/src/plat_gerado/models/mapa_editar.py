from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.mapa_editar_dados_type_0 import MapaEditarDadosType0


T = TypeVar("T", bound="MapaEditar")


@_attrs_define
class MapaEditar:
    """
    Attributes:
        titulo (None | str | Unset):
        resumo (None | str | Unset):
        descricao (None | str | Unset):
        tags (list[str] | None | Unset):
        extent (list[float] | None | Unset):
        categorias (list[str] | None | Unset):
        dados (MapaEditarDadosType0 | None | Unset):
        versao_atual (int | None | Unset):
    """

    titulo: None | str | Unset = UNSET
    resumo: None | str | Unset = UNSET
    descricao: None | str | Unset = UNSET
    tags: list[str] | None | Unset = UNSET
    extent: list[float] | None | Unset = UNSET
    categorias: list[str] | None | Unset = UNSET
    dados: MapaEditarDadosType0 | None | Unset = UNSET
    versao_atual: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.mapa_editar_dados_type_0 import MapaEditarDadosType0  # noqa: PLC0415

        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        resumo: None | str | Unset
        if isinstance(self.resumo, Unset):
            resumo = UNSET
        else:
            resumo = self.resumo

        descricao: None | str | Unset
        if isinstance(self.descricao, Unset):
            descricao = UNSET
        else:
            descricao = self.descricao

        tags: list[str] | None | Unset
        if isinstance(self.tags, Unset):
            tags = UNSET
        elif isinstance(self.tags, list):
            tags = self.tags

        else:
            tags = self.tags

        extent: list[float] | None | Unset
        if isinstance(self.extent, Unset):
            extent = UNSET
        elif isinstance(self.extent, list):
            extent = self.extent

        else:
            extent = self.extent

        categorias: list[str] | None | Unset
        if isinstance(self.categorias, Unset):
            categorias = UNSET
        elif isinstance(self.categorias, list):
            categorias = self.categorias

        else:
            categorias = self.categorias

        dados: dict[str, Any] | None | Unset
        if isinstance(self.dados, Unset):
            dados = UNSET
        elif isinstance(self.dados, MapaEditarDadosType0):
            dados = self.dados.to_dict()
        else:
            dados = self.dados

        versao_atual: int | None | Unset
        if isinstance(self.versao_atual, Unset):
            versao_atual = UNSET
        else:
            versao_atual = self.versao_atual

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if titulo is not UNSET:
            field_dict["titulo"] = titulo
        if resumo is not UNSET:
            field_dict["resumo"] = resumo
        if descricao is not UNSET:
            field_dict["descricao"] = descricao
        if tags is not UNSET:
            field_dict["tags"] = tags
        if extent is not UNSET:
            field_dict["extent"] = extent
        if categorias is not UNSET:
            field_dict["categorias"] = categorias
        if dados is not UNSET:
            field_dict["dados"] = dados
        if versao_atual is not UNSET:
            field_dict["versao_atual"] = versao_atual

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mapa_editar_dados_type_0 import MapaEditarDadosType0  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        def _parse_resumo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resumo = _parse_resumo(d.pop("resumo", UNSET))

        def _parse_descricao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        descricao = _parse_descricao(d.pop("descricao", UNSET))

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

        def _parse_extent(data: object) -> list[float] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                extent_type_0 = cast(list[float], data)

                return extent_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[float] | None | Unset, data)

        extent = _parse_extent(d.pop("extent", UNSET))

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

        def _parse_dados(data: object) -> MapaEditarDadosType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                dados_type_0 = MapaEditarDadosType0.from_dict(data)

                return dados_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MapaEditarDadosType0 | None | Unset, data)

        dados = _parse_dados(d.pop("dados", UNSET))

        def _parse_versao_atual(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        versao_atual = _parse_versao_atual(d.pop("versao_atual", UNSET))

        mapa_editar = cls(
            titulo=titulo,
            resumo=resumo,
            descricao=descricao,
            tags=tags,
            extent=extent,
            categorias=categorias,
            dados=dados,
            versao_atual=versao_atual,
        )

        return mapa_editar
