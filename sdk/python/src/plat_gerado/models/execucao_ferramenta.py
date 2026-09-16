from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.execucao_ferramenta_parametros import ExecucaoFerramentaParametros


T = TypeVar("T", bound="ExecucaoFerramenta")


@_attrs_define
class ExecucaoFerramenta:
    """
    Attributes:
        parametros (ExecucaoFerramentaParametros | Unset):
        titulo (None | str | Unset):
        modo (str | Unset):  Default: 'auto'.
    """

    parametros: ExecucaoFerramentaParametros | Unset = UNSET
    titulo: None | str | Unset = UNSET
    modo: str | Unset = "auto"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        parametros: dict[str, Any] | Unset = UNSET
        if not isinstance(self.parametros, Unset):
            parametros = self.parametros.to_dict()

        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        modo = self.modo

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if parametros is not UNSET:
            field_dict["parametros"] = parametros
        if titulo is not UNSET:
            field_dict["titulo"] = titulo
        if modo is not UNSET:
            field_dict["modo"] = modo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.execucao_ferramenta_parametros import ExecucaoFerramentaParametros  # noqa: PLC0415

        d = dict(src_dict)
        _parametros = d.pop("parametros", UNSET)
        parametros: ExecucaoFerramentaParametros | Unset
        if isinstance(_parametros, Unset):
            parametros = UNSET
        else:
            parametros = ExecucaoFerramentaParametros.from_dict(_parametros)

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        modo = d.pop("modo", UNSET)

        execucao_ferramenta = cls(
            parametros=parametros,
            titulo=titulo,
            modo=modo,
        )

        execucao_ferramenta.additional_properties = d
        return execucao_ferramenta

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
