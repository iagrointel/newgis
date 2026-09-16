from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ArquivoUrlEstado")


@_attrs_define
class ArquivoUrlEstado:
    """
    Attributes:
        conexao_id (str):
        intervalo_s (int):
        agendado (bool):
        sincronizacoes (int):
        recargas (int):
        formato (None | str | Unset):
        etag (None | str | Unset):
        last_modified (None | str | Unset):
        sha256 (None | str | Unset):
        bytes_ (int | None | Unset):
        item_id (None | str | Unset):
        importacao_id (None | str | Unset):
        proximo_em (None | str | Unset):
        ultimo_em (None | str | Unset):
        ultimo_resultado (None | str | Unset):
        ultimo_detalhe (None | str | Unset):
    """

    conexao_id: str
    intervalo_s: int
    agendado: bool
    sincronizacoes: int
    recargas: int
    formato: None | str | Unset = UNSET
    etag: None | str | Unset = UNSET
    last_modified: None | str | Unset = UNSET
    sha256: None | str | Unset = UNSET
    bytes_: int | None | Unset = UNSET
    item_id: None | str | Unset = UNSET
    importacao_id: None | str | Unset = UNSET
    proximo_em: None | str | Unset = UNSET
    ultimo_em: None | str | Unset = UNSET
    ultimo_resultado: None | str | Unset = UNSET
    ultimo_detalhe: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        conexao_id = self.conexao_id

        intervalo_s = self.intervalo_s

        agendado = self.agendado

        sincronizacoes = self.sincronizacoes

        recargas = self.recargas

        formato: None | str | Unset
        if isinstance(self.formato, Unset):
            formato = UNSET
        else:
            formato = self.formato

        etag: None | str | Unset
        if isinstance(self.etag, Unset):
            etag = UNSET
        else:
            etag = self.etag

        last_modified: None | str | Unset
        if isinstance(self.last_modified, Unset):
            last_modified = UNSET
        else:
            last_modified = self.last_modified

        sha256: None | str | Unset
        if isinstance(self.sha256, Unset):
            sha256 = UNSET
        else:
            sha256 = self.sha256

        bytes_: int | None | Unset
        if isinstance(self.bytes_, Unset):
            bytes_ = UNSET
        else:
            bytes_ = self.bytes_

        item_id: None | str | Unset
        if isinstance(self.item_id, Unset):
            item_id = UNSET
        else:
            item_id = self.item_id

        importacao_id: None | str | Unset
        if isinstance(self.importacao_id, Unset):
            importacao_id = UNSET
        else:
            importacao_id = self.importacao_id

        proximo_em: None | str | Unset
        if isinstance(self.proximo_em, Unset):
            proximo_em = UNSET
        else:
            proximo_em = self.proximo_em

        ultimo_em: None | str | Unset
        if isinstance(self.ultimo_em, Unset):
            ultimo_em = UNSET
        else:
            ultimo_em = self.ultimo_em

        ultimo_resultado: None | str | Unset
        if isinstance(self.ultimo_resultado, Unset):
            ultimo_resultado = UNSET
        else:
            ultimo_resultado = self.ultimo_resultado

        ultimo_detalhe: None | str | Unset
        if isinstance(self.ultimo_detalhe, Unset):
            ultimo_detalhe = UNSET
        else:
            ultimo_detalhe = self.ultimo_detalhe

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "conexao_id": conexao_id,
                "intervalo_s": intervalo_s,
                "agendado": agendado,
                "sincronizacoes": sincronizacoes,
                "recargas": recargas,
            }
        )
        if formato is not UNSET:
            field_dict["formato"] = formato
        if etag is not UNSET:
            field_dict["etag"] = etag
        if last_modified is not UNSET:
            field_dict["last_modified"] = last_modified
        if sha256 is not UNSET:
            field_dict["sha256"] = sha256
        if bytes_ is not UNSET:
            field_dict["bytes"] = bytes_
        if item_id is not UNSET:
            field_dict["item_id"] = item_id
        if importacao_id is not UNSET:
            field_dict["importacao_id"] = importacao_id
        if proximo_em is not UNSET:
            field_dict["proximo_em"] = proximo_em
        if ultimo_em is not UNSET:
            field_dict["ultimo_em"] = ultimo_em
        if ultimo_resultado is not UNSET:
            field_dict["ultimo_resultado"] = ultimo_resultado
        if ultimo_detalhe is not UNSET:
            field_dict["ultimo_detalhe"] = ultimo_detalhe

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        conexao_id = d.pop("conexao_id")

        intervalo_s = d.pop("intervalo_s")

        agendado = d.pop("agendado")

        sincronizacoes = d.pop("sincronizacoes")

        recargas = d.pop("recargas")

        def _parse_formato(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        formato = _parse_formato(d.pop("formato", UNSET))

        def _parse_etag(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        etag = _parse_etag(d.pop("etag", UNSET))

        def _parse_last_modified(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_modified = _parse_last_modified(d.pop("last_modified", UNSET))

        def _parse_sha256(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sha256 = _parse_sha256(d.pop("sha256", UNSET))

        def _parse_bytes_(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        bytes_ = _parse_bytes_(d.pop("bytes", UNSET))

        def _parse_item_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        item_id = _parse_item_id(d.pop("item_id", UNSET))

        def _parse_importacao_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        importacao_id = _parse_importacao_id(d.pop("importacao_id", UNSET))

        def _parse_proximo_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        proximo_em = _parse_proximo_em(d.pop("proximo_em", UNSET))

        def _parse_ultimo_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ultimo_em = _parse_ultimo_em(d.pop("ultimo_em", UNSET))

        def _parse_ultimo_resultado(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ultimo_resultado = _parse_ultimo_resultado(d.pop("ultimo_resultado", UNSET))

        def _parse_ultimo_detalhe(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ultimo_detalhe = _parse_ultimo_detalhe(d.pop("ultimo_detalhe", UNSET))

        arquivo_url_estado = cls(
            conexao_id=conexao_id,
            intervalo_s=intervalo_s,
            agendado=agendado,
            sincronizacoes=sincronizacoes,
            recargas=recargas,
            formato=formato,
            etag=etag,
            last_modified=last_modified,
            sha256=sha256,
            bytes_=bytes_,
            item_id=item_id,
            importacao_id=importacao_id,
            proximo_em=proximo_em,
            ultimo_em=ultimo_em,
            ultimo_resultado=ultimo_resultado,
            ultimo_detalhe=ultimo_detalhe,
        )

        arquivo_url_estado.additional_properties = d
        return arquivo_url_estado

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
