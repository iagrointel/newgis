from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.config_tracado_entrada_config import ConfigTracadoEntradaConfig


T = TypeVar("T", bound="ConfigTracadoEntrada")


@_attrs_define
class ConfigTracadoEntrada:
    """O documento salvo que preenche o pedido de traçado. `config` é validado contra o catálogo DA REDE em
    `config_tracado.validar_documento` (atributo, categoria, grupo, tipo, operador, função e tipo de
    resultado), e não por pydantic: a mensagem de erro precisa dizer qual atributo a rede não tem.

        Attributes:
            codigo (str):
            nome (str):
            tipo (str):
            descricao (None | str | Unset):
            config (ConfigTracadoEntradaConfig | Unset):
            compartilhada (bool | Unset):  Default: True.
    """

    codigo: str
    nome: str
    tipo: str
    descricao: None | str | Unset = UNSET
    config: ConfigTracadoEntradaConfig | Unset = UNSET
    compartilhada: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        codigo = self.codigo

        nome = self.nome

        tipo = self.tipo

        descricao: None | str | Unset
        if isinstance(self.descricao, Unset):
            descricao = UNSET
        else:
            descricao = self.descricao

        config: dict[str, Any] | Unset = UNSET
        if not isinstance(self.config, Unset):
            config = self.config.to_dict()

        compartilhada = self.compartilhada

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "codigo": codigo,
                "nome": nome,
                "tipo": tipo,
            }
        )
        if descricao is not UNSET:
            field_dict["descricao"] = descricao
        if config is not UNSET:
            field_dict["config"] = config
        if compartilhada is not UNSET:
            field_dict["compartilhada"] = compartilhada

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.config_tracado_entrada_config import ConfigTracadoEntradaConfig  # noqa: PLC0415

        d = dict(src_dict)
        codigo = d.pop("codigo")

        nome = d.pop("nome")

        tipo = d.pop("tipo")

        def _parse_descricao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        descricao = _parse_descricao(d.pop("descricao", UNSET))

        _config = d.pop("config", UNSET)
        config: ConfigTracadoEntradaConfig | Unset
        if isinstance(_config, Unset):
            config = UNSET
        else:
            config = ConfigTracadoEntradaConfig.from_dict(_config)

        compartilhada = d.pop("compartilhada", UNSET)

        config_tracado_entrada = cls(
            codigo=codigo,
            nome=nome,
            tipo=tipo,
            descricao=descricao,
            config=config,
            compartilhada=compartilhada,
        )

        config_tracado_entrada.additional_properties = d
        return config_tracado_entrada

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
