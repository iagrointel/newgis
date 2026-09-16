from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.mudanca_servidor_atributos_type_0 import MudancaServidorAtributosType0
    from ..models.mudanca_servidor_geometria_type_0 import MudancaServidorGeometriaType0


T = TypeVar("T", bound="MudancaServidor")


@_attrs_define
class MudancaServidor:
    """
    Attributes:
        operacao (str):
        id (str):
        fid (int | None | Unset):
        versao (int | None | Unset):
        atributos (MudancaServidorAtributosType0 | None | Unset):
        geometria (MudancaServidorGeometriaType0 | None | Unset):
    """

    operacao: str
    id: str
    fid: int | None | Unset = UNSET
    versao: int | None | Unset = UNSET
    atributos: MudancaServidorAtributosType0 | None | Unset = UNSET
    geometria: MudancaServidorGeometriaType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.mudanca_servidor_atributos_type_0 import MudancaServidorAtributosType0  # noqa: PLC0415
        from ..models.mudanca_servidor_geometria_type_0 import MudancaServidorGeometriaType0  # noqa: PLC0415

        operacao = self.operacao

        id = self.id

        fid: int | None | Unset
        if isinstance(self.fid, Unset):
            fid = UNSET
        else:
            fid = self.fid

        versao: int | None | Unset
        if isinstance(self.versao, Unset):
            versao = UNSET
        else:
            versao = self.versao

        atributos: dict[str, Any] | None | Unset
        if isinstance(self.atributos, Unset):
            atributos = UNSET
        elif isinstance(self.atributos, MudancaServidorAtributosType0):
            atributos = self.atributos.to_dict()
        else:
            atributos = self.atributos

        geometria: dict[str, Any] | None | Unset
        if isinstance(self.geometria, Unset):
            geometria = UNSET
        elif isinstance(self.geometria, MudancaServidorGeometriaType0):
            geometria = self.geometria.to_dict()
        else:
            geometria = self.geometria

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "operacao": operacao,
                "id": id,
            }
        )
        if fid is not UNSET:
            field_dict["fid"] = fid
        if versao is not UNSET:
            field_dict["versao"] = versao
        if atributos is not UNSET:
            field_dict["atributos"] = atributos
        if geometria is not UNSET:
            field_dict["geometria"] = geometria

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mudanca_servidor_atributos_type_0 import MudancaServidorAtributosType0  # noqa: PLC0415
        from ..models.mudanca_servidor_geometria_type_0 import MudancaServidorGeometriaType0  # noqa: PLC0415

        d = dict(src_dict)
        operacao = d.pop("operacao")

        id = d.pop("id")

        def _parse_fid(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        fid = _parse_fid(d.pop("fid", UNSET))

        def _parse_versao(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        versao = _parse_versao(d.pop("versao", UNSET))

        def _parse_atributos(data: object) -> MudancaServidorAtributosType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                atributos_type_0 = MudancaServidorAtributosType0.from_dict(data)

                return atributos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MudancaServidorAtributosType0 | None | Unset, data)

        atributos = _parse_atributos(d.pop("atributos", UNSET))

        def _parse_geometria(data: object) -> MudancaServidorGeometriaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                geometria_type_0 = MudancaServidorGeometriaType0.from_dict(data)

                return geometria_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MudancaServidorGeometriaType0 | None | Unset, data)

        geometria = _parse_geometria(d.pop("geometria", UNSET))

        mudanca_servidor = cls(
            operacao=operacao,
            id=id,
            fid=fid,
            versao=versao,
            atributos=atributos,
            geometria=geometria,
        )

        mudanca_servidor.additional_properties = d
        return mudanca_servidor

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
