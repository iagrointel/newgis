from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.validacao_resultado_erros_item import ValidacaoResultadoErrosItem


T = TypeVar("T", bound="ValidacaoResultado")


@_attrs_define
class ValidacaoResultado:
    """
    Attributes:
        rede_id (str):
        regras_ativas (bool):
        conexoes_avaliadas (int):
        associacoes_avaliadas (int):
        total_erros (int):
        erros (list[ValidacaoResultadoErrosItem]):
    """

    rede_id: str
    regras_ativas: bool
    conexoes_avaliadas: int
    associacoes_avaliadas: int
    total_erros: int
    erros: list[ValidacaoResultadoErrosItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rede_id = self.rede_id

        regras_ativas = self.regras_ativas

        conexoes_avaliadas = self.conexoes_avaliadas

        associacoes_avaliadas = self.associacoes_avaliadas

        total_erros = self.total_erros

        erros = []
        for erros_item_data in self.erros:
            erros_item = erros_item_data.to_dict()
            erros.append(erros_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rede_id": rede_id,
                "regras_ativas": regras_ativas,
                "conexoes_avaliadas": conexoes_avaliadas,
                "associacoes_avaliadas": associacoes_avaliadas,
                "total_erros": total_erros,
                "erros": erros,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.validacao_resultado_erros_item import ValidacaoResultadoErrosItem  # noqa: PLC0415

        d = dict(src_dict)
        rede_id = d.pop("rede_id")

        regras_ativas = d.pop("regras_ativas")

        conexoes_avaliadas = d.pop("conexoes_avaliadas")

        associacoes_avaliadas = d.pop("associacoes_avaliadas")

        total_erros = d.pop("total_erros")

        erros = []
        _erros = d.pop("erros")
        for erros_item_data in _erros:
            erros_item = ValidacaoResultadoErrosItem.from_dict(erros_item_data)

            erros.append(erros_item)

        validacao_resultado = cls(
            rede_id=rede_id,
            regras_ativas=regras_ativas,
            conexoes_avaliadas=conexoes_avaliadas,
            associacoes_avaliadas=associacoes_avaliadas,
            total_erros=total_erros,
            erros=erros,
        )

        validacao_resultado.additional_properties = d
        return validacao_resultado

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
