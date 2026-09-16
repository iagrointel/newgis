from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.acervo_camada_frescor import AcervoCamadaFrescor
    from ..models.acervo_verificacao import AcervoVerificacao


T = TypeVar("T", bound="AcervoVerificacaoHistorico")


@_attrs_define
class AcervoVerificacaoHistorico:
    """
    Attributes:
        camada (AcervoCamadaFrescor): Uma camada do registro com o estado de verificação. `linhas_exatas` é NULL quando
            a contagem não coube
            no prazo de 25 s — a tela escreve "não contado no prazo", nunca zero, e `reltuples` não aparece aqui.
        total (int):
        verificacoes (list[AcervoVerificacao]):
    """

    camada: AcervoCamadaFrescor
    total: int
    verificacoes: list[AcervoVerificacao]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        camada = self.camada.to_dict()

        total = self.total

        verificacoes = []
        for verificacoes_item_data in self.verificacoes:
            verificacoes_item = verificacoes_item_data.to_dict()
            verificacoes.append(verificacoes_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "camada": camada,
                "total": total,
                "verificacoes": verificacoes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.acervo_camada_frescor import AcervoCamadaFrescor  # noqa: PLC0415
        from ..models.acervo_verificacao import AcervoVerificacao  # noqa: PLC0415

        d = dict(src_dict)
        camada = AcervoCamadaFrescor.from_dict(d.pop("camada"))

        total = d.pop("total")

        verificacoes = []
        _verificacoes = d.pop("verificacoes")
        for verificacoes_item_data in _verificacoes:
            verificacoes_item = AcervoVerificacao.from_dict(verificacoes_item_data)

            verificacoes.append(verificacoes_item)

        acervo_verificacao_historico = cls(
            camada=camada,
            total=total,
            verificacoes=verificacoes,
        )

        acervo_verificacao_historico.additional_properties = d
        return acervo_verificacao_historico

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
