from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.analise_pacote_documentos_item import AnalisePacoteDocumentosItem
    from ..models.analise_pacote_fontes_item import AnalisePacoteFontesItem
    from ..models.analise_pacote_origem_type_0 import AnalisePacoteOrigemType0


T = TypeVar("T", bound="AnalisePacote")


@_attrs_define
class AnalisePacote:
    """
    Attributes:
        raiz (str):
        tipo_raiz (None | str):
        titulo_raiz (None | str):
        origem (AnalisePacoteOrigemType0 | None):
        sha256_conteudo (None | str):
        documentos (list[AnalisePacoteDocumentosItem]):
        fontes (list[AnalisePacoteFontesItem]):
        pronto (bool):
    """

    raiz: str
    tipo_raiz: None | str
    titulo_raiz: None | str
    origem: AnalisePacoteOrigemType0 | None
    sha256_conteudo: None | str
    documentos: list[AnalisePacoteDocumentosItem]
    fontes: list[AnalisePacoteFontesItem]
    pronto: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.analise_pacote_origem_type_0 import AnalisePacoteOrigemType0  # noqa: PLC0415

        raiz = self.raiz

        tipo_raiz: None | str
        tipo_raiz = self.tipo_raiz

        titulo_raiz: None | str
        titulo_raiz = self.titulo_raiz

        origem: dict[str, Any] | None
        if isinstance(self.origem, AnalisePacoteOrigemType0):
            origem = self.origem.to_dict()
        else:
            origem = self.origem

        sha256_conteudo: None | str
        sha256_conteudo = self.sha256_conteudo

        documentos = []
        for documentos_item_data in self.documentos:
            documentos_item = documentos_item_data.to_dict()
            documentos.append(documentos_item)

        fontes = []
        for fontes_item_data in self.fontes:
            fontes_item = fontes_item_data.to_dict()
            fontes.append(fontes_item)

        pronto = self.pronto

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "raiz": raiz,
                "tipo_raiz": tipo_raiz,
                "titulo_raiz": titulo_raiz,
                "origem": origem,
                "sha256_conteudo": sha256_conteudo,
                "documentos": documentos,
                "fontes": fontes,
                "pronto": pronto,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.analise_pacote_documentos_item import AnalisePacoteDocumentosItem  # noqa: PLC0415
        from ..models.analise_pacote_fontes_item import AnalisePacoteFontesItem  # noqa: PLC0415
        from ..models.analise_pacote_origem_type_0 import AnalisePacoteOrigemType0  # noqa: PLC0415

        d = dict(src_dict)
        raiz = d.pop("raiz")

        def _parse_tipo_raiz(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        tipo_raiz = _parse_tipo_raiz(d.pop("tipo_raiz"))

        def _parse_titulo_raiz(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        titulo_raiz = _parse_titulo_raiz(d.pop("titulo_raiz"))

        def _parse_origem(data: object) -> AnalisePacoteOrigemType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                origem_type_0 = AnalisePacoteOrigemType0.from_dict(data)

                return origem_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AnalisePacoteOrigemType0 | None, data)

        origem = _parse_origem(d.pop("origem"))

        def _parse_sha256_conteudo(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        sha256_conteudo = _parse_sha256_conteudo(d.pop("sha256_conteudo"))

        documentos = []
        _documentos = d.pop("documentos")
        for documentos_item_data in _documentos:
            documentos_item = AnalisePacoteDocumentosItem.from_dict(documentos_item_data)

            documentos.append(documentos_item)

        fontes = []
        _fontes = d.pop("fontes")
        for fontes_item_data in _fontes:
            fontes_item = AnalisePacoteFontesItem.from_dict(fontes_item_data)

            fontes.append(fontes_item)

        pronto = d.pop("pronto")

        analise_pacote = cls(
            raiz=raiz,
            tipo_raiz=tipo_raiz,
            titulo_raiz=titulo_raiz,
            origem=origem,
            sha256_conteudo=sha256_conteudo,
            documentos=documentos,
            fontes=fontes,
            pronto=pronto,
        )

        analise_pacote.additional_properties = d
        return analise_pacote

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
