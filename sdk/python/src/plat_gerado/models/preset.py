from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.preset_conteudo import PresetConteudo


T = TypeVar("T", bound="Preset")


@_attrs_define
class Preset:
    """
    Attributes:
        id (str):
        nome (str):
        descricao (str):
        escopo (str):
        integrado (bool):
        conteudo (PresetConteudo):
        dono_id (None | str | Unset):
        dono_login (None | str | Unset):
        criado_em (None | str | Unset):
        atualizado_em (None | str | Unset):
    """

    id: str
    nome: str
    descricao: str
    escopo: str
    integrado: bool
    conteudo: PresetConteudo
    dono_id: None | str | Unset = UNSET
    dono_login: None | str | Unset = UNSET
    criado_em: None | str | Unset = UNSET
    atualizado_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        nome = self.nome

        descricao = self.descricao

        escopo = self.escopo

        integrado = self.integrado

        conteudo = self.conteudo.to_dict()

        dono_id: None | str | Unset
        if isinstance(self.dono_id, Unset):
            dono_id = UNSET
        else:
            dono_id = self.dono_id

        dono_login: None | str | Unset
        if isinstance(self.dono_login, Unset):
            dono_login = UNSET
        else:
            dono_login = self.dono_login

        criado_em: None | str | Unset
        if isinstance(self.criado_em, Unset):
            criado_em = UNSET
        else:
            criado_em = self.criado_em

        atualizado_em: None | str | Unset
        if isinstance(self.atualizado_em, Unset):
            atualizado_em = UNSET
        else:
            atualizado_em = self.atualizado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nome": nome,
                "descricao": descricao,
                "escopo": escopo,
                "integrado": integrado,
                "conteudo": conteudo,
            }
        )
        if dono_id is not UNSET:
            field_dict["dono_id"] = dono_id
        if dono_login is not UNSET:
            field_dict["dono_login"] = dono_login
        if criado_em is not UNSET:
            field_dict["criado_em"] = criado_em
        if atualizado_em is not UNSET:
            field_dict["atualizado_em"] = atualizado_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.preset_conteudo import PresetConteudo  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        nome = d.pop("nome")

        descricao = d.pop("descricao")

        escopo = d.pop("escopo")

        integrado = d.pop("integrado")

        conteudo = PresetConteudo.from_dict(d.pop("conteudo"))

        def _parse_dono_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dono_id = _parse_dono_id(d.pop("dono_id", UNSET))

        def _parse_dono_login(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dono_login = _parse_dono_login(d.pop("dono_login", UNSET))

        def _parse_criado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        criado_em = _parse_criado_em(d.pop("criado_em", UNSET))

        def _parse_atualizado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        atualizado_em = _parse_atualizado_em(d.pop("atualizado_em", UNSET))

        preset = cls(
            id=id,
            nome=nome,
            descricao=descricao,
            escopo=escopo,
            integrado=integrado,
            conteudo=conteudo,
            dono_id=dono_id,
            dono_login=dono_login,
            criado_em=criado_em,
            atualizado_em=atualizado_em,
        )

        preset.additional_properties = d
        return preset

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
