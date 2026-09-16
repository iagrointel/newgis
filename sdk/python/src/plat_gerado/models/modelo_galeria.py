from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ModeloGaleria")


@_attrs_define
class ModeloGaleria:
    """
    Attributes:
        id (str):
        escopo (str):
        nome (str):
        descricao (str):
        tipo_raiz (str):
        documentos (int):
        fontes (int):
        sha256 (str):
        bytes_ (int):
        do_inquilino (bool):
        criado_em (None | str):
    """

    id: str
    escopo: str
    nome: str
    descricao: str
    tipo_raiz: str
    documentos: int
    fontes: int
    sha256: str
    bytes_: int
    do_inquilino: bool
    criado_em: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        escopo = self.escopo

        nome = self.nome

        descricao = self.descricao

        tipo_raiz = self.tipo_raiz

        documentos = self.documentos

        fontes = self.fontes

        sha256 = self.sha256

        bytes_ = self.bytes_

        do_inquilino = self.do_inquilino

        criado_em: None | str
        criado_em = self.criado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "escopo": escopo,
                "nome": nome,
                "descricao": descricao,
                "tipo_raiz": tipo_raiz,
                "documentos": documentos,
                "fontes": fontes,
                "sha256": sha256,
                "bytes": bytes_,
                "do_inquilino": do_inquilino,
                "criado_em": criado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        escopo = d.pop("escopo")

        nome = d.pop("nome")

        descricao = d.pop("descricao")

        tipo_raiz = d.pop("tipo_raiz")

        documentos = d.pop("documentos")

        fontes = d.pop("fontes")

        sha256 = d.pop("sha256")

        bytes_ = d.pop("bytes")

        do_inquilino = d.pop("do_inquilino")

        def _parse_criado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        criado_em = _parse_criado_em(d.pop("criado_em"))

        modelo_galeria = cls(
            id=id,
            escopo=escopo,
            nome=nome,
            descricao=descricao,
            tipo_raiz=tipo_raiz,
            documentos=documentos,
            fontes=fontes,
            sha256=sha256,
            bytes_=bytes_,
            do_inquilino=do_inquilino,
            criado_em=criado_em,
        )

        modelo_galeria.additional_properties = d
        return modelo_galeria

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
