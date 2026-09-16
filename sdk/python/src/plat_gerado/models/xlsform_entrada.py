from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="XlsformEntrada")


@_attrs_define
class XlsformEntrada:
    """
    Attributes:
        nome (str):
        conteudo (str):
        titulo (None | str | Unset):
        camada_destino (None | str | Unset):
    """

    nome: str
    conteudo: str
    titulo: None | str | Unset = UNSET
    camada_destino: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        conteudo = self.conteudo

        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        camada_destino: None | str | Unset
        if isinstance(self.camada_destino, Unset):
            camada_destino = UNSET
        else:
            camada_destino = self.camada_destino

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "conteudo": conteudo,
            }
        )
        if titulo is not UNSET:
            field_dict["titulo"] = titulo
        if camada_destino is not UNSET:
            field_dict["camada_destino"] = camada_destino

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        conteudo = d.pop("conteudo")

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        def _parse_camada_destino(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        camada_destino = _parse_camada_destino(d.pop("camada_destino", UNSET))

        xlsform_entrada = cls(
            nome=nome,
            conteudo=conteudo,
            titulo=titulo,
            camada_destino=camada_destino,
        )

        return xlsform_entrada
