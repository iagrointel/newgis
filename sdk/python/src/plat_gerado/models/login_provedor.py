from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.login_provedor_provisionamento import LoginProvedorProvisionamento


T = TypeVar("T", bound="LoginProvedor")


@_attrs_define
class LoginProvedor:
    """
    Attributes:
        tipo (str):
        id (int):
        habilitado (bool):
        rotulo (None | str):
        ordem (int | None):
        identificador (None | str):
        provisionamento (LoginProvedorProvisionamento):
        atualizado_em (None | str):
    """

    tipo: str
    id: int
    habilitado: bool
    rotulo: None | str
    ordem: int | None
    identificador: None | str
    provisionamento: LoginProvedorProvisionamento
    atualizado_em: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tipo = self.tipo

        id = self.id

        habilitado = self.habilitado

        rotulo: None | str
        rotulo = self.rotulo

        ordem: int | None
        ordem = self.ordem

        identificador: None | str
        identificador = self.identificador

        provisionamento = self.provisionamento.to_dict()

        atualizado_em: None | str
        atualizado_em = self.atualizado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tipo": tipo,
                "id": id,
                "habilitado": habilitado,
                "rotulo": rotulo,
                "ordem": ordem,
                "identificador": identificador,
                "provisionamento": provisionamento,
                "atualizado_em": atualizado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.login_provedor_provisionamento import LoginProvedorProvisionamento  # noqa: PLC0415

        d = dict(src_dict)
        tipo = d.pop("tipo")

        id = d.pop("id")

        habilitado = d.pop("habilitado")

        def _parse_rotulo(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        rotulo = _parse_rotulo(d.pop("rotulo"))

        def _parse_ordem(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        ordem = _parse_ordem(d.pop("ordem"))

        def _parse_identificador(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        identificador = _parse_identificador(d.pop("identificador"))

        provisionamento = LoginProvedorProvisionamento.from_dict(d.pop("provisionamento"))

        def _parse_atualizado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        atualizado_em = _parse_atualizado_em(d.pop("atualizado_em"))

        login_provedor = cls(
            tipo=tipo,
            id=id,
            habilitado=habilitado,
            rotulo=rotulo,
            ordem=ordem,
            identificador=identificador,
            provisionamento=provisionamento,
            atualizado_em=atualizado_em,
        )

        login_provedor.additional_properties = d
        return login_provedor

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
