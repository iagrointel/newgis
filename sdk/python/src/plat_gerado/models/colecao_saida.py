from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ColecaoSaida")


@_attrs_define
class ColecaoSaida:
    """
    Attributes:
        nome (str):
        srid_entregue (int):
        titulo (None | str | Unset):
        crs_nativo (None | str | Unset):
        srid_nativo (int | None | Unset):
        extent_4326 (list[float] | None | Unset):
        formatos (list[str] | Unset):
    """

    nome: str
    srid_entregue: int
    titulo: None | str | Unset = UNSET
    crs_nativo: None | str | Unset = UNSET
    srid_nativo: int | None | Unset = UNSET
    extent_4326: list[float] | None | Unset = UNSET
    formatos: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        srid_entregue = self.srid_entregue

        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        crs_nativo: None | str | Unset
        if isinstance(self.crs_nativo, Unset):
            crs_nativo = UNSET
        else:
            crs_nativo = self.crs_nativo

        srid_nativo: int | None | Unset
        if isinstance(self.srid_nativo, Unset):
            srid_nativo = UNSET
        else:
            srid_nativo = self.srid_nativo

        extent_4326: list[float] | None | Unset
        if isinstance(self.extent_4326, Unset):
            extent_4326 = UNSET
        elif isinstance(self.extent_4326, list):
            extent_4326 = self.extent_4326

        else:
            extent_4326 = self.extent_4326

        formatos: list[str] | Unset = UNSET
        if not isinstance(self.formatos, Unset):
            formatos = self.formatos

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nome": nome,
                "srid_entregue": srid_entregue,
            }
        )
        if titulo is not UNSET:
            field_dict["titulo"] = titulo
        if crs_nativo is not UNSET:
            field_dict["crs_nativo"] = crs_nativo
        if srid_nativo is not UNSET:
            field_dict["srid_nativo"] = srid_nativo
        if extent_4326 is not UNSET:
            field_dict["extent_4326"] = extent_4326
        if formatos is not UNSET:
            field_dict["formatos"] = formatos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        srid_entregue = d.pop("srid_entregue")

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        def _parse_crs_nativo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        crs_nativo = _parse_crs_nativo(d.pop("crs_nativo", UNSET))

        def _parse_srid_nativo(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        srid_nativo = _parse_srid_nativo(d.pop("srid_nativo", UNSET))

        def _parse_extent_4326(data: object) -> list[float] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                extent_4326_type_0 = cast(list[float], data)

                return extent_4326_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[float] | None | Unset, data)

        extent_4326 = _parse_extent_4326(d.pop("extent_4326", UNSET))

        formatos = cast(list[str], d.pop("formatos", UNSET))

        colecao_saida = cls(
            nome=nome,
            srid_entregue=srid_entregue,
            titulo=titulo,
            crs_nativo=crs_nativo,
            srid_nativo=srid_nativo,
            extent_4326=extent_4326,
            formatos=formatos,
        )

        colecao_saida.additional_properties = d
        return colecao_saida

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
