from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.predefinicao_entrada_esticamento_type_0 import PredefinicaoEntradaEsticamentoType0


T = TypeVar("T", bound="PredefinicaoEntrada")


@_attrs_define
class PredefinicaoEntrada:
    """
    Attributes:
        nome (str):
        titulo (str):
        descricao (None | str | Unset):
        bandas (list[int] | None | Unset):
        colormap (None | str | Unset):
        esticamento (None | PredefinicaoEntradaEsticamentoType0 | Unset):
        nodata_transparente (bool | Unset):  Default: True.
        opacidade (float | Unset):  Default: 1.0.
        resampling (str | Unset):  Default: 'nearest'.
    """

    nome: str
    titulo: str
    descricao: None | str | Unset = UNSET
    bandas: list[int] | None | Unset = UNSET
    colormap: None | str | Unset = UNSET
    esticamento: None | PredefinicaoEntradaEsticamentoType0 | Unset = UNSET
    nodata_transparente: bool | Unset = True
    opacidade: float | Unset = 1.0
    resampling: str | Unset = "nearest"

    def to_dict(self) -> dict[str, Any]:
        from ..models.predefinicao_entrada_esticamento_type_0 import (
            PredefinicaoEntradaEsticamentoType0,  # noqa: PLC0415
        )

        nome = self.nome

        titulo = self.titulo

        descricao: None | str | Unset
        if isinstance(self.descricao, Unset):
            descricao = UNSET
        else:
            descricao = self.descricao

        bandas: list[int] | None | Unset
        if isinstance(self.bandas, Unset):
            bandas = UNSET
        elif isinstance(self.bandas, list):
            bandas = self.bandas

        else:
            bandas = self.bandas

        colormap: None | str | Unset
        if isinstance(self.colormap, Unset):
            colormap = UNSET
        else:
            colormap = self.colormap

        esticamento: dict[str, Any] | None | Unset
        if isinstance(self.esticamento, Unset):
            esticamento = UNSET
        elif isinstance(self.esticamento, PredefinicaoEntradaEsticamentoType0):
            esticamento = self.esticamento.to_dict()
        else:
            esticamento = self.esticamento

        nodata_transparente = self.nodata_transparente

        opacidade = self.opacidade

        resampling = self.resampling

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "titulo": titulo,
            }
        )
        if descricao is not UNSET:
            field_dict["descricao"] = descricao
        if bandas is not UNSET:
            field_dict["bandas"] = bandas
        if colormap is not UNSET:
            field_dict["colormap"] = colormap
        if esticamento is not UNSET:
            field_dict["esticamento"] = esticamento
        if nodata_transparente is not UNSET:
            field_dict["nodata_transparente"] = nodata_transparente
        if opacidade is not UNSET:
            field_dict["opacidade"] = opacidade
        if resampling is not UNSET:
            field_dict["resampling"] = resampling

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.predefinicao_entrada_esticamento_type_0 import (
            PredefinicaoEntradaEsticamentoType0,  # noqa: PLC0415
        )

        d = dict(src_dict)
        nome = d.pop("nome")

        titulo = d.pop("titulo")

        def _parse_descricao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        descricao = _parse_descricao(d.pop("descricao", UNSET))

        def _parse_bandas(data: object) -> list[int] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                bandas_type_0 = cast(list[int], data)

                return bandas_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[int] | None | Unset, data)

        bandas = _parse_bandas(d.pop("bandas", UNSET))

        def _parse_colormap(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        colormap = _parse_colormap(d.pop("colormap", UNSET))

        def _parse_esticamento(data: object) -> None | PredefinicaoEntradaEsticamentoType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                esticamento_type_0 = PredefinicaoEntradaEsticamentoType0.from_dict(data)

                return esticamento_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PredefinicaoEntradaEsticamentoType0 | Unset, data)

        esticamento = _parse_esticamento(d.pop("esticamento", UNSET))

        nodata_transparente = d.pop("nodata_transparente", UNSET)

        opacidade = d.pop("opacidade", UNSET)

        resampling = d.pop("resampling", UNSET)

        predefinicao_entrada = cls(
            nome=nome,
            titulo=titulo,
            descricao=descricao,
            bandas=bandas,
            colormap=colormap,
            esticamento=esticamento,
            nodata_transparente=nodata_transparente,
            opacidade=opacidade,
            resampling=resampling,
        )

        return predefinicao_entrada
