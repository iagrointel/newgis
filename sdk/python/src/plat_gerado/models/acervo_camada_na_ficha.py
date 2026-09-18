from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AcervoCamadaNaFicha")


@_attrs_define
class AcervoCamadaNaFicha:
    """Uma camada EXPOSTA da fonte, como a ficha a mostra (itens L6-01-c e L6-01-j-multi-servidor).
    `origem` é o texto que a tela escreve: camada lida por FDW de outro servidor da casa sai como
    "servidor remoto (<nome>)", por extenso — nunca um código que o leitor tenha de decifrar.

        Attributes:
            acervo_camada_id (str):
            servidor (str):
            schema_nome (str):
            tabela (str):
            estado (str):
            modo_acesso (str):
            origem (str):
            linhas_exatas (int | None | Unset):
            fdw_tabela (None | str | Unset):
            aviso (None | str | Unset):
    """

    acervo_camada_id: str
    servidor: str
    schema_nome: str
    tabela: str
    estado: str
    modo_acesso: str
    origem: str
    linhas_exatas: int | None | Unset = UNSET
    fdw_tabela: None | str | Unset = UNSET
    aviso: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        acervo_camada_id = self.acervo_camada_id

        servidor = self.servidor

        schema_nome = self.schema_nome

        tabela = self.tabela

        estado = self.estado

        modo_acesso = self.modo_acesso

        origem = self.origem

        linhas_exatas: int | None | Unset
        if isinstance(self.linhas_exatas, Unset):
            linhas_exatas = UNSET
        else:
            linhas_exatas = self.linhas_exatas

        fdw_tabela: None | str | Unset
        if isinstance(self.fdw_tabela, Unset):
            fdw_tabela = UNSET
        else:
            fdw_tabela = self.fdw_tabela

        aviso: None | str | Unset
        if isinstance(self.aviso, Unset):
            aviso = UNSET
        else:
            aviso = self.aviso

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "acervo_camada_id": acervo_camada_id,
                "servidor": servidor,
                "schema_nome": schema_nome,
                "tabela": tabela,
                "estado": estado,
                "modo_acesso": modo_acesso,
                "origem": origem,
            }
        )
        if linhas_exatas is not UNSET:
            field_dict["linhas_exatas"] = linhas_exatas
        if fdw_tabela is not UNSET:
            field_dict["fdw_tabela"] = fdw_tabela
        if aviso is not UNSET:
            field_dict["aviso"] = aviso

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        acervo_camada_id = d.pop("acervo_camada_id")

        servidor = d.pop("servidor")

        schema_nome = d.pop("schema_nome")

        tabela = d.pop("tabela")

        estado = d.pop("estado")

        modo_acesso = d.pop("modo_acesso")

        origem = d.pop("origem")

        def _parse_linhas_exatas(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        linhas_exatas = _parse_linhas_exatas(d.pop("linhas_exatas", UNSET))

        def _parse_fdw_tabela(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        fdw_tabela = _parse_fdw_tabela(d.pop("fdw_tabela", UNSET))

        def _parse_aviso(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        aviso = _parse_aviso(d.pop("aviso", UNSET))

        acervo_camada_na_ficha = cls(
            acervo_camada_id=acervo_camada_id,
            servidor=servidor,
            schema_nome=schema_nome,
            tabela=tabela,
            estado=estado,
            modo_acesso=modo_acesso,
            origem=origem,
            linhas_exatas=linhas_exatas,
            fdw_tabela=fdw_tabela,
            aviso=aviso,
        )

        acervo_camada_na_ficha.additional_properties = d
        return acervo_camada_na_ficha

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
