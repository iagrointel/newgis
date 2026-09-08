from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.item_entrada_classificacao_type_0 import ItemEntradaClassificacaoType0
    from ..models.item_entrada_dados import ItemEntradaDados


T = TypeVar("T", bound="ItemEntrada")


@_attrs_define
class ItemEntrada:
    """
    Attributes:
        tipo (str):
        titulo (str):
        resumo (None | str | Unset):
        descricao (None | str | Unset):
        tags (list[str] | Unset):
        creditos (None | str | Unset):
        termos_de_uso (None | str | Unset):
        pasta_id (None | str | Unset):
        extent (list[float] | None | Unset):
        extent_origem (None | str | Unset):
        categorias (list[str] | Unset):
        classificacao (ItemEntradaClassificacaoType0 | None | Unset):
        url (None | str | Unset):
        origem (str | Unset):  Default: 'hospedado'.
        dados (ItemEntradaDados | Unset):
        id (None | str | Unset):
    """

    tipo: str
    titulo: str
    resumo: None | str | Unset = UNSET
    descricao: None | str | Unset = UNSET
    tags: list[str] | Unset = UNSET
    creditos: None | str | Unset = UNSET
    termos_de_uso: None | str | Unset = UNSET
    pasta_id: None | str | Unset = UNSET
    extent: list[float] | None | Unset = UNSET
    extent_origem: None | str | Unset = UNSET
    categorias: list[str] | Unset = UNSET
    classificacao: ItemEntradaClassificacaoType0 | None | Unset = UNSET
    url: None | str | Unset = UNSET
    origem: str | Unset = "hospedado"
    dados: ItemEntradaDados | Unset = UNSET
    id: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.item_entrada_classificacao_type_0 import ItemEntradaClassificacaoType0  # noqa: PLC0415

        tipo = self.tipo

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

        creditos: None | str | Unset
        if isinstance(self.creditos, Unset):
            creditos = UNSET
        else:
            creditos = self.creditos

        termos_de_uso: None | str | Unset
        if isinstance(self.termos_de_uso, Unset):
            termos_de_uso = UNSET
        else:
            termos_de_uso = self.termos_de_uso

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

        extent_origem: None | str | Unset
        if isinstance(self.extent_origem, Unset):
            extent_origem = UNSET
        else:
            extent_origem = self.extent_origem

        categorias: list[str] | Unset = UNSET
        if not isinstance(self.categorias, Unset):
            categorias = self.categorias

        classificacao: dict[str, Any] | None | Unset
        if isinstance(self.classificacao, Unset):
            classificacao = UNSET
        elif isinstance(self.classificacao, ItemEntradaClassificacaoType0):
            classificacao = self.classificacao.to_dict()
        else:
            classificacao = self.classificacao

        url: None | str | Unset
        if isinstance(self.url, Unset):
            url = UNSET
        else:
            url = self.url

        origem = self.origem

        dados: dict[str, Any] | Unset = UNSET
        if not isinstance(self.dados, Unset):
            dados = self.dados.to_dict()

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "tipo": tipo,
                "titulo": titulo,
            }
        )
        if resumo is not UNSET:
            field_dict["resumo"] = resumo
        if descricao is not UNSET:
            field_dict["descricao"] = descricao
        if tags is not UNSET:
            field_dict["tags"] = tags
        if creditos is not UNSET:
            field_dict["creditos"] = creditos
        if termos_de_uso is not UNSET:
            field_dict["termos_de_uso"] = termos_de_uso
        if pasta_id is not UNSET:
            field_dict["pasta_id"] = pasta_id
        if extent is not UNSET:
            field_dict["extent"] = extent
        if extent_origem is not UNSET:
            field_dict["extent_origem"] = extent_origem
        if categorias is not UNSET:
            field_dict["categorias"] = categorias
        if classificacao is not UNSET:
            field_dict["classificacao"] = classificacao
        if url is not UNSET:
            field_dict["url"] = url
        if origem is not UNSET:
            field_dict["origem"] = origem
        if dados is not UNSET:
            field_dict["dados"] = dados
        if id is not UNSET:
            field_dict["id"] = id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.item_entrada_classificacao_type_0 import ItemEntradaClassificacaoType0  # noqa: PLC0415
        from ..models.item_entrada_dados import ItemEntradaDados  # noqa: PLC0415

        d = dict(src_dict)
        tipo = d.pop("tipo")

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

        def _parse_creditos(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        creditos = _parse_creditos(d.pop("creditos", UNSET))

        def _parse_termos_de_uso(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        termos_de_uso = _parse_termos_de_uso(d.pop("termos_de_uso", UNSET))

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

        def _parse_extent_origem(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        extent_origem = _parse_extent_origem(d.pop("extent_origem", UNSET))

        categorias = cast(list[str], d.pop("categorias", UNSET))

        def _parse_classificacao(data: object) -> ItemEntradaClassificacaoType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                classificacao_type_0 = ItemEntradaClassificacaoType0.from_dict(data)

                return classificacao_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ItemEntradaClassificacaoType0 | None | Unset, data)

        classificacao = _parse_classificacao(d.pop("classificacao", UNSET))

        def _parse_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        url = _parse_url(d.pop("url", UNSET))

        origem = d.pop("origem", UNSET)

        _dados = d.pop("dados", UNSET)
        dados: ItemEntradaDados | Unset
        if isinstance(_dados, Unset):
            dados = UNSET
        else:
            dados = ItemEntradaDados.from_dict(_dados)

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        item_entrada = cls(
            tipo=tipo,
            titulo=titulo,
            resumo=resumo,
            descricao=descricao,
            tags=tags,
            creditos=creditos,
            termos_de_uso=termos_de_uso,
            pasta_id=pasta_id,
            extent=extent,
            extent_origem=extent_origem,
            categorias=categorias,
            classificacao=classificacao,
            url=url,
            origem=origem,
            dados=dados,
            id=id,
        )

        return item_entrada
