from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.documento_publico_corpo import DocumentoPublicoCorpo


T = TypeVar("T", bound="DocumentoPublico")


@_attrs_define
class DocumentoPublico:
    """
    Attributes:
        item_id (str):
        titulo (None | str):
        tipo (str):
        resumo (None | str):
        versao_publicada (int):
        corpo (DocumentoPublicoCorpo):
        dominios_permitidos (list[str]):
        token (None | str):
    """

    item_id: str
    titulo: None | str
    tipo: str
    resumo: None | str
    versao_publicada: int
    corpo: DocumentoPublicoCorpo
    dominios_permitidos: list[str]
    token: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        item_id = self.item_id

        titulo: None | str
        titulo = self.titulo

        tipo = self.tipo

        resumo: None | str
        resumo = self.resumo

        versao_publicada = self.versao_publicada

        corpo = self.corpo.to_dict()

        dominios_permitidos = self.dominios_permitidos

        token: None | str
        token = self.token

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "item_id": item_id,
                "titulo": titulo,
                "tipo": tipo,
                "resumo": resumo,
                "versao_publicada": versao_publicada,
                "corpo": corpo,
                "dominios_permitidos": dominios_permitidos,
                "token": token,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.documento_publico_corpo import DocumentoPublicoCorpo  # noqa: PLC0415

        d = dict(src_dict)
        item_id = d.pop("item_id")

        def _parse_titulo(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        titulo = _parse_titulo(d.pop("titulo"))

        tipo = d.pop("tipo")

        def _parse_resumo(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        resumo = _parse_resumo(d.pop("resumo"))

        versao_publicada = d.pop("versao_publicada")

        corpo = DocumentoPublicoCorpo.from_dict(d.pop("corpo"))

        dominios_permitidos = cast(list[str], d.pop("dominios_permitidos"))

        def _parse_token(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        token = _parse_token(d.pop("token"))

        documento_publico = cls(
            item_id=item_id,
            titulo=titulo,
            tipo=tipo,
            resumo=resumo,
            versao_publicada=versao_publicada,
            corpo=corpo,
            dominios_permitidos=dominios_permitidos,
            token=token,
        )

        documento_publico.additional_properties = d
        return documento_publico

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
