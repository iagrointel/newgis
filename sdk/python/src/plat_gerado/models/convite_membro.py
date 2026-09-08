from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.convite_membro_criado_por_type_0 import ConviteMembroCriadoPorType0
    from ..models.convite_membro_papel_type_0 import ConviteMembroPapelType0


T = TypeVar("T", bound="ConviteMembro")


@_attrs_define
class ConviteMembro:
    """
    Attributes:
        id (str):
        email (str):
        perfil (str):
        criado_em (str):
        expira_em (str):
        nome_sugerido (None | str | Unset):
        papel (ConviteMembroPapelType0 | None | Unset):
        criado_por (ConviteMembroCriadoPorType0 | None | Unset):
        usado_em (None | str | Unset):
        cancelado_em (None | str | Unset):
    """

    id: str
    email: str
    perfil: str
    criado_em: str
    expira_em: str
    nome_sugerido: None | str | Unset = UNSET
    papel: ConviteMembroPapelType0 | None | Unset = UNSET
    criado_por: ConviteMembroCriadoPorType0 | None | Unset = UNSET
    usado_em: None | str | Unset = UNSET
    cancelado_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.convite_membro_criado_por_type_0 import ConviteMembroCriadoPorType0  # noqa: PLC0415
        from ..models.convite_membro_papel_type_0 import ConviteMembroPapelType0  # noqa: PLC0415

        id = self.id

        email = self.email

        perfil = self.perfil

        criado_em = self.criado_em

        expira_em = self.expira_em

        nome_sugerido: None | str | Unset
        if isinstance(self.nome_sugerido, Unset):
            nome_sugerido = UNSET
        else:
            nome_sugerido = self.nome_sugerido

        papel: dict[str, Any] | None | Unset
        if isinstance(self.papel, Unset):
            papel = UNSET
        elif isinstance(self.papel, ConviteMembroPapelType0):
            papel = self.papel.to_dict()
        else:
            papel = self.papel

        criado_por: dict[str, Any] | None | Unset
        if isinstance(self.criado_por, Unset):
            criado_por = UNSET
        elif isinstance(self.criado_por, ConviteMembroCriadoPorType0):
            criado_por = self.criado_por.to_dict()
        else:
            criado_por = self.criado_por

        usado_em: None | str | Unset
        if isinstance(self.usado_em, Unset):
            usado_em = UNSET
        else:
            usado_em = self.usado_em

        cancelado_em: None | str | Unset
        if isinstance(self.cancelado_em, Unset):
            cancelado_em = UNSET
        else:
            cancelado_em = self.cancelado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "email": email,
                "perfil": perfil,
                "criado_em": criado_em,
                "expira_em": expira_em,
            }
        )
        if nome_sugerido is not UNSET:
            field_dict["nome_sugerido"] = nome_sugerido
        if papel is not UNSET:
            field_dict["papel"] = papel
        if criado_por is not UNSET:
            field_dict["criado_por"] = criado_por
        if usado_em is not UNSET:
            field_dict["usado_em"] = usado_em
        if cancelado_em is not UNSET:
            field_dict["cancelado_em"] = cancelado_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.convite_membro_criado_por_type_0 import ConviteMembroCriadoPorType0  # noqa: PLC0415
        from ..models.convite_membro_papel_type_0 import ConviteMembroPapelType0  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        email = d.pop("email")

        perfil = d.pop("perfil")

        criado_em = d.pop("criado_em")

        expira_em = d.pop("expira_em")

        def _parse_nome_sugerido(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome_sugerido = _parse_nome_sugerido(d.pop("nome_sugerido", UNSET))

        def _parse_papel(data: object) -> ConviteMembroPapelType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                papel_type_0 = ConviteMembroPapelType0.from_dict(data)

                return papel_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConviteMembroPapelType0 | None | Unset, data)

        papel = _parse_papel(d.pop("papel", UNSET))

        def _parse_criado_por(data: object) -> ConviteMembroCriadoPorType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                criado_por_type_0 = ConviteMembroCriadoPorType0.from_dict(data)

                return criado_por_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConviteMembroCriadoPorType0 | None | Unset, data)

        criado_por = _parse_criado_por(d.pop("criado_por", UNSET))

        def _parse_usado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        usado_em = _parse_usado_em(d.pop("usado_em", UNSET))

        def _parse_cancelado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cancelado_em = _parse_cancelado_em(d.pop("cancelado_em", UNSET))

        convite_membro = cls(
            id=id,
            email=email,
            perfil=perfil,
            criado_em=criado_em,
            expira_em=expira_em,
            nome_sugerido=nome_sugerido,
            papel=papel,
            criado_por=criado_por,
            usado_em=usado_em,
            cancelado_em=cancelado_em,
        )

        convite_membro.additional_properties = d
        return convite_membro

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
