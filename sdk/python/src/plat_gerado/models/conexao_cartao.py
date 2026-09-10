from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ConexaoCartao")


@_attrs_define
class ConexaoCartao:
    """
    Attributes:
        id (str):
        tipo (str):
        modo (str):
        nome (str):
        url (str):
        saude (str):
        saude_verificada_em (None | str | Unset):
        estado_saude (str | Unset):  Default: 'nunca_testada'.
        disponibilidade_30d_pct (float | None | Unset):
        disponibilidade_30d_total (int | Unset):  Default: 0.
    """

    id: str
    tipo: str
    modo: str
    nome: str
    url: str
    saude: str
    saude_verificada_em: None | str | Unset = UNSET
    estado_saude: str | Unset = "nunca_testada"
    disponibilidade_30d_pct: float | None | Unset = UNSET
    disponibilidade_30d_total: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        tipo = self.tipo

        modo = self.modo

        nome = self.nome

        url = self.url

        saude = self.saude

        saude_verificada_em: None | str | Unset
        if isinstance(self.saude_verificada_em, Unset):
            saude_verificada_em = UNSET
        else:
            saude_verificada_em = self.saude_verificada_em

        estado_saude = self.estado_saude

        disponibilidade_30d_pct: float | None | Unset
        if isinstance(self.disponibilidade_30d_pct, Unset):
            disponibilidade_30d_pct = UNSET
        else:
            disponibilidade_30d_pct = self.disponibilidade_30d_pct

        disponibilidade_30d_total = self.disponibilidade_30d_total

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "tipo": tipo,
                "modo": modo,
                "nome": nome,
                "url": url,
                "saude": saude,
            }
        )
        if saude_verificada_em is not UNSET:
            field_dict["saude_verificada_em"] = saude_verificada_em
        if estado_saude is not UNSET:
            field_dict["estado_saude"] = estado_saude
        if disponibilidade_30d_pct is not UNSET:
            field_dict["disponibilidade_30d_pct"] = disponibilidade_30d_pct
        if disponibilidade_30d_total is not UNSET:
            field_dict["disponibilidade_30d_total"] = disponibilidade_30d_total

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        tipo = d.pop("tipo")

        modo = d.pop("modo")

        nome = d.pop("nome")

        url = d.pop("url")

        saude = d.pop("saude")

        def _parse_saude_verificada_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        saude_verificada_em = _parse_saude_verificada_em(d.pop("saude_verificada_em", UNSET))

        estado_saude = d.pop("estado_saude", UNSET)

        def _parse_disponibilidade_30d_pct(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        disponibilidade_30d_pct = _parse_disponibilidade_30d_pct(d.pop("disponibilidade_30d_pct", UNSET))

        disponibilidade_30d_total = d.pop("disponibilidade_30d_total", UNSET)

        conexao_cartao = cls(
            id=id,
            tipo=tipo,
            modo=modo,
            nome=nome,
            url=url,
            saude=saude,
            saude_verificada_em=saude_verificada_em,
            estado_saude=estado_saude,
            disponibilidade_30d_pct=disponibilidade_30d_pct,
            disponibilidade_30d_total=disponibilidade_30d_total,
        )

        conexao_cartao.additional_properties = d
        return conexao_cartao

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
