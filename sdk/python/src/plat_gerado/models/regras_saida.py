from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.regras_saida_campos_virtuais_item import RegrasSaidaCamposVirtuaisItem
    from ..models.regras_saida_regras_item import RegrasSaidaRegrasItem
    from ..models.regras_saida_validacao_type_0 import RegrasSaidaValidacaoType0


T = TypeVar("T", bound="RegrasSaida")


@_attrs_define
class RegrasSaida:
    """
    Attributes:
        camada_id (str):
        regras (list[RegrasSaidaRegrasItem]):
        campos_virtuais (list[RegrasSaidaCamposVirtuaisItem]):
        ordem_de_avaliacao (list[str]):
        validacao (None | RegrasSaidaValidacaoType0 | Unset):
    """

    camada_id: str
    regras: list[RegrasSaidaRegrasItem]
    campos_virtuais: list[RegrasSaidaCamposVirtuaisItem]
    ordem_de_avaliacao: list[str]
    validacao: None | RegrasSaidaValidacaoType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.regras_saida_validacao_type_0 import RegrasSaidaValidacaoType0  # noqa: PLC0415

        camada_id = self.camada_id

        regras = []
        for regras_item_data in self.regras:
            regras_item = regras_item_data.to_dict()
            regras.append(regras_item)

        campos_virtuais = []
        for campos_virtuais_item_data in self.campos_virtuais:
            campos_virtuais_item = campos_virtuais_item_data.to_dict()
            campos_virtuais.append(campos_virtuais_item)

        ordem_de_avaliacao = self.ordem_de_avaliacao

        validacao: dict[str, Any] | None | Unset
        if isinstance(self.validacao, Unset):
            validacao = UNSET
        elif isinstance(self.validacao, RegrasSaidaValidacaoType0):
            validacao = self.validacao.to_dict()
        else:
            validacao = self.validacao

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "camada_id": camada_id,
                "regras": regras,
                "campos_virtuais": campos_virtuais,
                "ordem_de_avaliacao": ordem_de_avaliacao,
            }
        )
        if validacao is not UNSET:
            field_dict["validacao"] = validacao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.regras_saida_campos_virtuais_item import RegrasSaidaCamposVirtuaisItem  # noqa: PLC0415
        from ..models.regras_saida_regras_item import RegrasSaidaRegrasItem  # noqa: PLC0415
        from ..models.regras_saida_validacao_type_0 import RegrasSaidaValidacaoType0  # noqa: PLC0415

        d = dict(src_dict)
        camada_id = d.pop("camada_id")

        regras = []
        _regras = d.pop("regras")
        for regras_item_data in _regras:
            regras_item = RegrasSaidaRegrasItem.from_dict(regras_item_data)

            regras.append(regras_item)

        campos_virtuais = []
        _campos_virtuais = d.pop("campos_virtuais")
        for campos_virtuais_item_data in _campos_virtuais:
            campos_virtuais_item = RegrasSaidaCamposVirtuaisItem.from_dict(campos_virtuais_item_data)

            campos_virtuais.append(campos_virtuais_item)

        ordem_de_avaliacao = cast(list[str], d.pop("ordem_de_avaliacao"))

        def _parse_validacao(data: object) -> None | RegrasSaidaValidacaoType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                validacao_type_0 = RegrasSaidaValidacaoType0.from_dict(data)

                return validacao_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RegrasSaidaValidacaoType0 | Unset, data)

        validacao = _parse_validacao(d.pop("validacao", UNSET))

        regras_saida = cls(
            camada_id=camada_id,
            regras=regras,
            campos_virtuais=campos_virtuais,
            ordem_de_avaliacao=ordem_de_avaliacao,
            validacao=validacao,
        )

        regras_saida.additional_properties = d
        return regras_saida

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
