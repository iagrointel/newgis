from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.conexao_criada import ConexaoCriada
    from ..models.registro_saida import RegistroSaida


T = TypeVar("T", bound="CriarSaida")


@_attrs_define
class CriarSaida:
    """
    Attributes:
        registro (RegistroSaida):
        conexoes (list[ConexaoCriada]):
        avisos (list[str]):
    """

    registro: RegistroSaida
    conexoes: list[ConexaoCriada]
    avisos: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        registro = self.registro.to_dict()

        conexoes = []
        for conexoes_item_data in self.conexoes:
            conexoes_item = conexoes_item_data.to_dict()
            conexoes.append(conexoes_item)

        avisos = self.avisos

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "registro": registro,
                "conexoes": conexoes,
                "avisos": avisos,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conexao_criada import ConexaoCriada  # noqa: PLC0415
        from ..models.registro_saida import RegistroSaida  # noqa: PLC0415

        d = dict(src_dict)
        registro = RegistroSaida.from_dict(d.pop("registro"))

        conexoes = []
        _conexoes = d.pop("conexoes")
        for conexoes_item_data in _conexoes:
            conexoes_item = ConexaoCriada.from_dict(conexoes_item_data)

            conexoes.append(conexoes_item)

        avisos = cast(list[str], d.pop("avisos"))

        criar_saida = cls(
            registro=registro,
            conexoes=conexoes,
            avisos=avisos,
        )

        criar_saida.additional_properties = d
        return criar_saida

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
