from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.mapa_entrada_dados_type_0 import MapaEntradaDadosType0


T = TypeVar("T", bound="MapaEntrada")


@_attrs_define
class MapaEntrada:
    """
    Attributes:
        titulo (str):
        resumo (None | str | Unset):
        descricao (None | str | Unset):
        tags (list[str] | Unset):
        pasta_id (None | str | Unset):
        extent (list[float] | None | Unset):
        categorias (list[str] | Unset):
        dados (MapaEntradaDadosType0 | None | Unset):
    """

    titulo: str
    resumo: None | str | Unset = UNSET
    descricao: None | str | Unset = UNSET
    tags: list[str] | Unset = UNSET
    pasta_id: None | str | Unset = UNSET
    extent: list[float] | None | Unset = UNSET
    categorias: list[str] | Unset = UNSET
    dados: MapaEntradaDadosType0 | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.mapa_entrada_dados_type_0 import MapaEntradaDadosType0  # noqa: PLC0415

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

        tags: list[str] | Unset = UNSET
        if not isinstance(self.tags, Unset):
            tags = self.tags

        pasta_id: None | str | Unset
        if isinstance(self.pasta_id, Unset):
            pasta_id = UNSET
        else:
            pasta_id = self.pasta_id

        extent: list[float] | None | Unset
        if isinstance(self.extent, Unset):
            extent = UNSET
        elif isinstance(self.extent, list):
            extent = self.extent

        else:
            extent = self.extent

        categorias: list[str] | Unset = UNSET
        if not isinstance(self.categorias, Unset):
            categorias = self.categorias

        dados: dict[str, Any] | None | Unset
        if isinstance(self.dados, Unset):
            dados = UNSET
        elif isinstance(self.dados, MapaEntradaDadosType0):
            dados = self.dados.to_dict()
        else:
            dados = self.dados

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "titulo": titulo,
            }
        )
        if resumo is not UNSET:
            field_dict["resumo"] = resumo
        if descricao is not UNSET:
            field_dict["descricao"] = descricao
        if tags is not UNSET:
            field_dict["tags"] = tags
        if pasta_id is not UNSET:
            field_dict["pasta_id"] = pasta_id
        if extent is not UNSET:
            field_dict["extent"] = extent
        if categorias is not UNSET:
            field_dict["categorias"] = categorias
        if dados is not UNSET:
            field_dict["dados"] = dados

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mapa_entrada_dados_type_0 import MapaEntradaDadosType0  # noqa: PLC0415

        d = dict(src_dict)
        titulo = d.pop("titulo")

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

        tags = cast(list[str], d.pop("tags", UNSET))

        def _parse_pasta_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pasta_id = _parse_pasta_id(d.pop("pasta_id", UNSET))

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

        categorias = cast(list[str], d.pop("categorias", UNSET))

        def _parse_dados(data: object) -> MapaEntradaDadosType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                dados_type_0 = MapaEntradaDadosType0.from_dict(data)

                return dados_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MapaEntradaDadosType0 | None | Unset, data)

        dados = _parse_dados(d.pop("dados", UNSET))

        mapa_entrada = cls(
            titulo=titulo,
            resumo=resumo,
            descricao=descricao,
            tags=tags,
            pasta_id=pasta_id,
            extent=extent,
            categorias=categorias,
            dados=dados,
        )

        return mapa_entrada
