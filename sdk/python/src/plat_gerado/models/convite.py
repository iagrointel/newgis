from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.convite_convidado_por_type_0 import ConviteConvidadoPorType0
    from ..models.convite_grupo import ConviteGrupo


T = TypeVar("T", bound="Convite")


@_attrs_define
class Convite:
    """
    Attributes:
        grupo (ConviteGrupo):
        papel (str):
        convidado_por (ConviteConvidadoPorType0 | None):
        criado_em (None | str):
    """

    grupo: ConviteGrupo
    papel: str
    convidado_por: ConviteConvidadoPorType0 | None
    criado_em: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.convite_convidado_por_type_0 import ConviteConvidadoPorType0  # noqa: PLC0415

        grupo = self.grupo.to_dict()

        papel = self.papel

        convidado_por: dict[str, Any] | None
        if isinstance(self.convidado_por, ConviteConvidadoPorType0):
            convidado_por = self.convidado_por.to_dict()
        else:
            convidado_por = self.convidado_por

        criado_em: None | str
        criado_em = self.criado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "grupo": grupo,
                "papel": papel,
                "convidado_por": convidado_por,
                "criado_em": criado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.convite_convidado_por_type_0 import ConviteConvidadoPorType0  # noqa: PLC0415
        from ..models.convite_grupo import ConviteGrupo  # noqa: PLC0415

        d = dict(src_dict)
        grupo = ConviteGrupo.from_dict(d.pop("grupo"))

        papel = d.pop("papel")

        def _parse_convidado_por(data: object) -> ConviteConvidadoPorType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                convidado_por_type_0 = ConviteConvidadoPorType0.from_dict(data)

                return convidado_por_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConviteConvidadoPorType0 | None, data)

        convidado_por = _parse_convidado_por(d.pop("convidado_por"))

        def _parse_criado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        criado_em = _parse_criado_em(d.pop("criado_em"))

        convite = cls(
            grupo=grupo,
            papel=papel,
            convidado_por=convidado_por,
            criado_em=criado_em,
        )

        convite.additional_properties = d
        return convite

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
