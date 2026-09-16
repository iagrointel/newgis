from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.pacote_instalado_contagens import PacoteInstaladoContagens


T = TypeVar("T", bound="PacoteInstalado")


@_attrs_define
class PacoteInstalado:
    """
    Attributes:
        codigo (str):
        nome (str):
        versao (str):
        disciplina (str):
        bytes_ (int):
        sha256 (str):
        contagens (PacoteInstaladoContagens):
        descricao (None | str | Unset):
        fonte (None | str | Unset):
    """

    codigo: str
    nome: str
    versao: str
    disciplina: str
    bytes_: int
    sha256: str
    contagens: PacoteInstaladoContagens
    descricao: None | str | Unset = UNSET
    fonte: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        codigo = self.codigo

        nome = self.nome

        versao = self.versao

        disciplina = self.disciplina

        bytes_ = self.bytes_

        sha256 = self.sha256

        contagens = self.contagens.to_dict()

        descricao: None | str | Unset
        if isinstance(self.descricao, Unset):
            descricao = UNSET
        else:
            descricao = self.descricao

        fonte: None | str | Unset
        if isinstance(self.fonte, Unset):
            fonte = UNSET
        else:
            fonte = self.fonte

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "codigo": codigo,
                "nome": nome,
                "versao": versao,
                "disciplina": disciplina,
                "bytes": bytes_,
                "sha256": sha256,
                "contagens": contagens,
            }
        )
        if descricao is not UNSET:
            field_dict["descricao"] = descricao
        if fonte is not UNSET:
            field_dict["fonte"] = fonte

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pacote_instalado_contagens import PacoteInstaladoContagens  # noqa: PLC0415

        d = dict(src_dict)
        codigo = d.pop("codigo")

        nome = d.pop("nome")

        versao = d.pop("versao")

        disciplina = d.pop("disciplina")

        bytes_ = d.pop("bytes")

        sha256 = d.pop("sha256")

        contagens = PacoteInstaladoContagens.from_dict(d.pop("contagens"))

        def _parse_descricao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        descricao = _parse_descricao(d.pop("descricao", UNSET))

        def _parse_fonte(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        fonte = _parse_fonte(d.pop("fonte", UNSET))

        pacote_instalado = cls(
            codigo=codigo,
            nome=nome,
            versao=versao,
            disciplina=disciplina,
            bytes_=bytes_,
            sha256=sha256,
            contagens=contagens,
            descricao=descricao,
            fonte=fonte,
        )

        pacote_instalado.additional_properties = d
        return pacote_instalado

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
