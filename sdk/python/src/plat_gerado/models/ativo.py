from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.ativo_criado_por import AtivoCriadoPor


T = TypeVar("T", bound="Ativo")


@_attrs_define
class Ativo:
    """
    Attributes:
        global_id (str):
        rede_id (str):
        tipo_id (str):
        tipo_chave (str):
        numero (int):
        codigo (str):
        codigo_externo (None | str):
        criado_por (AtivoCriadoPor):
        criado_em (str):
        atualizado_em (str):
    """

    global_id: str
    rede_id: str
    tipo_id: str
    tipo_chave: str
    numero: int
    codigo: str
    codigo_externo: None | str
    criado_por: AtivoCriadoPor
    criado_em: str
    atualizado_em: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        global_id = self.global_id

        rede_id = self.rede_id

        tipo_id = self.tipo_id

        tipo_chave = self.tipo_chave

        numero = self.numero

        codigo = self.codigo

        codigo_externo: None | str
        codigo_externo = self.codigo_externo

        criado_por = self.criado_por.to_dict()

        criado_em = self.criado_em

        atualizado_em = self.atualizado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "global_id": global_id,
                "rede_id": rede_id,
                "tipo_id": tipo_id,
                "tipo_chave": tipo_chave,
                "numero": numero,
                "codigo": codigo,
                "codigo_externo": codigo_externo,
                "criado_por": criado_por,
                "criado_em": criado_em,
                "atualizado_em": atualizado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ativo_criado_por import AtivoCriadoPor  # noqa: PLC0415

        d = dict(src_dict)
        global_id = d.pop("global_id")

        rede_id = d.pop("rede_id")

        tipo_id = d.pop("tipo_id")

        tipo_chave = d.pop("tipo_chave")

        numero = d.pop("numero")

        codigo = d.pop("codigo")

        def _parse_codigo_externo(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        codigo_externo = _parse_codigo_externo(d.pop("codigo_externo"))

        criado_por = AtivoCriadoPor.from_dict(d.pop("criado_por"))

        criado_em = d.pop("criado_em")

        atualizado_em = d.pop("atualizado_em")

        ativo = cls(
            global_id=global_id,
            rede_id=rede_id,
            tipo_id=tipo_id,
            tipo_chave=tipo_chave,
            numero=numero,
            codigo=codigo,
            codigo_externo=codigo_externo,
            criado_por=criado_por,
            criado_em=criado_em,
            atualizado_em=atualizado_em,
        )

        ativo.additional_properties = d
        return ativo

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
