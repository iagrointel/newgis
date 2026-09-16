from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.opcoes_csv import OpcoesCsv


T = TypeVar("T", bound="ExportacaoEntrada")


@_attrs_define
class ExportacaoEntrada:
    """
    Attributes:
        item_id (str):
        formato (str):
        nome (None | str | Unset):
        campos (list[str] | None | Unset):
        where (None | str | Unset):
        bbox (list[float] | None | Unset):
        srid_saida (int | None | Unset):
        codificacao (None | str | Unset):
        pasta_id (None | str | Unset):
        csv (None | OpcoesCsv | Unset):
    """

    item_id: str
    formato: str
    nome: None | str | Unset = UNSET
    campos: list[str] | None | Unset = UNSET
    where: None | str | Unset = UNSET
    bbox: list[float] | None | Unset = UNSET
    srid_saida: int | None | Unset = UNSET
    codificacao: None | str | Unset = UNSET
    pasta_id: None | str | Unset = UNSET
    csv: None | OpcoesCsv | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.opcoes_csv import OpcoesCsv  # noqa: PLC0415

        item_id = self.item_id

        formato = self.formato

        nome: None | str | Unset
        if isinstance(self.nome, Unset):
            nome = UNSET
        else:
            nome = self.nome

        campos: list[str] | None | Unset
        if isinstance(self.campos, Unset):
            campos = UNSET
        elif isinstance(self.campos, list):
            campos = self.campos

        else:
            campos = self.campos

        where: None | str | Unset
        if isinstance(self.where, Unset):
            where = UNSET
        else:
            where = self.where

        bbox: list[float] | None | Unset
        if isinstance(self.bbox, Unset):
            bbox = UNSET
        elif isinstance(self.bbox, list):
            bbox = self.bbox

        else:
            bbox = self.bbox

        srid_saida: int | None | Unset
        if isinstance(self.srid_saida, Unset):
            srid_saida = UNSET
        else:
            srid_saida = self.srid_saida

        codificacao: None | str | Unset
        if isinstance(self.codificacao, Unset):
            codificacao = UNSET
        else:
            codificacao = self.codificacao

        pasta_id: None | str | Unset
        if isinstance(self.pasta_id, Unset):
            pasta_id = UNSET
        else:
            pasta_id = self.pasta_id

        csv: dict[str, Any] | None | Unset
        if isinstance(self.csv, Unset):
            csv = UNSET
        elif isinstance(self.csv, OpcoesCsv):
            csv = self.csv.to_dict()
        else:
            csv = self.csv

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "item_id": item_id,
                "formato": formato,
            }
        )
        if nome is not UNSET:
            field_dict["nome"] = nome
        if campos is not UNSET:
            field_dict["campos"] = campos
        if where is not UNSET:
            field_dict["where"] = where
        if bbox is not UNSET:
            field_dict["bbox"] = bbox
        if srid_saida is not UNSET:
            field_dict["srid_saida"] = srid_saida
        if codificacao is not UNSET:
            field_dict["codificacao"] = codificacao
        if pasta_id is not UNSET:
            field_dict["pasta_id"] = pasta_id
        if csv is not UNSET:
            field_dict["csv"] = csv

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.opcoes_csv import OpcoesCsv  # noqa: PLC0415

        d = dict(src_dict)
        item_id = d.pop("item_id")

        formato = d.pop("formato")

        def _parse_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome = _parse_nome(d.pop("nome", UNSET))

        def _parse_campos(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                campos_type_0 = cast(list[str], data)

                return campos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        campos = _parse_campos(d.pop("campos", UNSET))

        def _parse_where(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        where = _parse_where(d.pop("where", UNSET))

        def _parse_bbox(data: object) -> list[float] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                bbox_type_0 = cast(list[float], data)

                return bbox_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[float] | None | Unset, data)

        bbox = _parse_bbox(d.pop("bbox", UNSET))

        def _parse_srid_saida(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        srid_saida = _parse_srid_saida(d.pop("srid_saida", UNSET))

        def _parse_codificacao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        codificacao = _parse_codificacao(d.pop("codificacao", UNSET))

        def _parse_pasta_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pasta_id = _parse_pasta_id(d.pop("pasta_id", UNSET))

        def _parse_csv(data: object) -> None | OpcoesCsv | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                csv_type_0 = OpcoesCsv.from_dict(data)

                return csv_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | OpcoesCsv | Unset, data)

        csv = _parse_csv(d.pop("csv", UNSET))

        exportacao_entrada = cls(
            item_id=item_id,
            formato=formato,
            nome=nome,
            campos=campos,
            where=where,
            bbox=bbox,
            srid_saida=srid_saida,
            codificacao=codificacao,
            pasta_id=pasta_id,
            csv=csv,
        )

        return exportacao_entrada
