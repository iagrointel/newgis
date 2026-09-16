from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.pacote_entrada_mapeamento import PacoteEntradaMapeamento


T = TypeVar("T", bound="PacoteEntrada")


@_attrs_define
class PacoteEntrada:
    """O zip vem em base64 dentro de JSON, e não em multipart, pela mesma razão da miniatura (ADR 0004
    seção 11): o CSRF sob cookie exige application/json.

        Attributes:
            conteudo (None | str | Unset):
            modelo_id (None | str | Unset):
            mapeamento (PacoteEntradaMapeamento | Unset):
            pasta_id (None | str | Unset):
    """

    conteudo: None | str | Unset = UNSET
    modelo_id: None | str | Unset = UNSET
    mapeamento: PacoteEntradaMapeamento | Unset = UNSET
    pasta_id: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        conteudo: None | str | Unset
        if isinstance(self.conteudo, Unset):
            conteudo = UNSET
        else:
            conteudo = self.conteudo

        modelo_id: None | str | Unset
        if isinstance(self.modelo_id, Unset):
            modelo_id = UNSET
        else:
            modelo_id = self.modelo_id

        mapeamento: dict[str, Any] | Unset = UNSET
        if not isinstance(self.mapeamento, Unset):
            mapeamento = self.mapeamento.to_dict()

        pasta_id: None | str | Unset
        if isinstance(self.pasta_id, Unset):
            pasta_id = UNSET
        else:
            pasta_id = self.pasta_id

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if conteudo is not UNSET:
            field_dict["conteudo"] = conteudo
        if modelo_id is not UNSET:
            field_dict["modelo_id"] = modelo_id
        if mapeamento is not UNSET:
            field_dict["mapeamento"] = mapeamento
        if pasta_id is not UNSET:
            field_dict["pasta_id"] = pasta_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pacote_entrada_mapeamento import PacoteEntradaMapeamento  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_conteudo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        conteudo = _parse_conteudo(d.pop("conteudo", UNSET))

        def _parse_modelo_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        modelo_id = _parse_modelo_id(d.pop("modelo_id", UNSET))

        _mapeamento = d.pop("mapeamento", UNSET)
        mapeamento: PacoteEntradaMapeamento | Unset
        if isinstance(_mapeamento, Unset):
            mapeamento = UNSET
        else:
            mapeamento = PacoteEntradaMapeamento.from_dict(_mapeamento)

        def _parse_pasta_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pasta_id = _parse_pasta_id(d.pop("pasta_id", UNSET))

        pacote_entrada = cls(
            conteudo=conteudo,
            modelo_id=modelo_id,
            mapeamento=mapeamento,
            pasta_id=pasta_id,
        )

        return pacote_entrada
