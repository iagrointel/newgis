from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.camada_externa_extensao_type_0 import CamadaExternaExtensaoType0


T = TypeVar("T", bound="CamadaExterna")


@_attrs_define
class CamadaExterna:
    """
    Attributes:
        nome (str):
        descoberta_em (str):
        titulo (None | str | Unset):
        crs (list[str] | Unset):
        extensao (CamadaExternaExtensaoType0 | None | Unset):
    """

    nome: str
    descoberta_em: str
    titulo: None | str | Unset = UNSET
    crs: list[str] | Unset = UNSET
    extensao: CamadaExternaExtensaoType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.camada_externa_extensao_type_0 import CamadaExternaExtensaoType0  # noqa: PLC0415

        nome = self.nome

        descoberta_em = self.descoberta_em

        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        crs: list[str] | Unset = UNSET
        if not isinstance(self.crs, Unset):
            crs = self.crs

        extensao: dict[str, Any] | None | Unset
        if isinstance(self.extensao, Unset):
            extensao = UNSET
        elif isinstance(self.extensao, CamadaExternaExtensaoType0):
            extensao = self.extensao.to_dict()
        else:
            extensao = self.extensao

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nome": nome,
                "descoberta_em": descoberta_em,
            }
        )
        if titulo is not UNSET:
            field_dict["titulo"] = titulo
        if crs is not UNSET:
            field_dict["crs"] = crs
        if extensao is not UNSET:
            field_dict["extensao"] = extensao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.camada_externa_extensao_type_0 import CamadaExternaExtensaoType0  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        descoberta_em = d.pop("descoberta_em")

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        crs = cast(list[str], d.pop("crs", UNSET))

        def _parse_extensao(data: object) -> CamadaExternaExtensaoType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                extensao_type_0 = CamadaExternaExtensaoType0.from_dict(data)

                return extensao_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CamadaExternaExtensaoType0 | None | Unset, data)

        extensao = _parse_extensao(d.pop("extensao", UNSET))

        camada_externa = cls(
            nome=nome,
            descoberta_em=descoberta_em,
            titulo=titulo,
            crs=crs,
            extensao=extensao,
        )

        camada_externa.additional_properties = d
        return camada_externa

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
