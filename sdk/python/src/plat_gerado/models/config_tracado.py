from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.config_tracado_config import ConfigTracadoConfig


T = TypeVar("T", bound="ConfigTracado")


@_attrs_define
class ConfigTracado:
    """
    Attributes:
        id (str):
        rede_id (str):
        codigo (str):
        nome (str):
        descricao (None | str):
        tipo (str):
        config (ConfigTracadoConfig):
        origem (str):
        compartilhada (bool):
        dono_id (int | None):
        criado_em (str):
        atualizado_em (str):
    """

    id: str
    rede_id: str
    codigo: str
    nome: str
    descricao: None | str
    tipo: str
    config: ConfigTracadoConfig
    origem: str
    compartilhada: bool
    dono_id: int | None
    criado_em: str
    atualizado_em: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        rede_id = self.rede_id

        codigo = self.codigo

        nome = self.nome

        descricao: None | str
        descricao = self.descricao

        tipo = self.tipo

        config = self.config.to_dict()

        origem = self.origem

        compartilhada = self.compartilhada

        dono_id: int | None
        dono_id = self.dono_id

        criado_em = self.criado_em

        atualizado_em = self.atualizado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "rede_id": rede_id,
                "codigo": codigo,
                "nome": nome,
                "descricao": descricao,
                "tipo": tipo,
                "config": config,
                "origem": origem,
                "compartilhada": compartilhada,
                "dono_id": dono_id,
                "criado_em": criado_em,
                "atualizado_em": atualizado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.config_tracado_config import ConfigTracadoConfig  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        rede_id = d.pop("rede_id")

        codigo = d.pop("codigo")

        nome = d.pop("nome")

        def _parse_descricao(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        descricao = _parse_descricao(d.pop("descricao"))

        tipo = d.pop("tipo")

        config = ConfigTracadoConfig.from_dict(d.pop("config"))

        origem = d.pop("origem")

        compartilhada = d.pop("compartilhada")

        def _parse_dono_id(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        dono_id = _parse_dono_id(d.pop("dono_id"))

        criado_em = d.pop("criado_em")

        atualizado_em = d.pop("atualizado_em")

        config_tracado = cls(
            id=id,
            rede_id=rede_id,
            codigo=codigo,
            nome=nome,
            descricao=descricao,
            tipo=tipo,
            config=config,
            origem=origem,
            compartilhada=compartilhada,
            dono_id=dono_id,
            criado_em=criado_em,
            atualizado_em=atualizado_em,
        )

        config_tracado.additional_properties = d
        return config_tracado

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
