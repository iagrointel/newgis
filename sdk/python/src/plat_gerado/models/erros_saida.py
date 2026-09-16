from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.erros_saida_itens_item import ErrosSaidaItensItem
    from ..models.erros_saida_validacao_type_0 import ErrosSaidaValidacaoType0


T = TypeVar("T", bound="ErrosSaida")


@_attrs_define
class ErrosSaida:
    """
    Attributes:
        total (int):
        itens (list[ErrosSaidaItensItem]):
        validacao (ErrosSaidaValidacaoType0 | None | Unset):
    """

    total: int
    itens: list[ErrosSaidaItensItem]
    validacao: ErrosSaidaValidacaoType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.erros_saida_validacao_type_0 import ErrosSaidaValidacaoType0  # noqa: PLC0415

        total = self.total

        itens = []
        for itens_item_data in self.itens:
            itens_item = itens_item_data.to_dict()
            itens.append(itens_item)

        validacao: dict[str, Any] | None | Unset
        if isinstance(self.validacao, Unset):
            validacao = UNSET
        elif isinstance(self.validacao, ErrosSaidaValidacaoType0):
            validacao = self.validacao.to_dict()
        else:
            validacao = self.validacao

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total": total,
                "itens": itens,
            }
        )
        if validacao is not UNSET:
            field_dict["validacao"] = validacao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.erros_saida_itens_item import ErrosSaidaItensItem  # noqa: PLC0415
        from ..models.erros_saida_validacao_type_0 import ErrosSaidaValidacaoType0  # noqa: PLC0415

        d = dict(src_dict)
        total = d.pop("total")

        itens = []
        _itens = d.pop("itens")
        for itens_item_data in _itens:
            itens_item = ErrosSaidaItensItem.from_dict(itens_item_data)

            itens.append(itens_item)

        def _parse_validacao(data: object) -> ErrosSaidaValidacaoType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                validacao_type_0 = ErrosSaidaValidacaoType0.from_dict(data)

                return validacao_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ErrosSaidaValidacaoType0 | None | Unset, data)

        validacao = _parse_validacao(d.pop("validacao", UNSET))

        erros_saida = cls(
            total=total,
            itens=itens,
            validacao=validacao,
        )

        erros_saida.additional_properties = d
        return erros_saida

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
