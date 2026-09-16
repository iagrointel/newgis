from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.diagrama_entrada_origem import DiagramaEntradaOrigem


T = TypeVar("T", bound="DiagramaEntrada")


@_attrs_define
class DiagramaEntrada:
    """Pedido de geração de diagrama. `origem` é validada em `diagrama._elementos_da_origem`, não aqui: as
    três formas (subrede, traçado, seleção) têm campos diferentes, e a mensagem de erro precisa dizer qual
    subrede/feição não existe NESTA rede — coisa que pydantic não sabe.

        Attributes:
            nome (str):
            origem (DiagramaEntradaOrigem | Unset):
            modelo (str | Unset):  Default: 'basico'.
            layout (None | str | Unset):
    """

    nome: str
    origem: DiagramaEntradaOrigem | Unset = UNSET
    modelo: str | Unset = "basico"
    layout: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        origem: dict[str, Any] | Unset = UNSET
        if not isinstance(self.origem, Unset):
            origem = self.origem.to_dict()

        modelo = self.modelo

        layout: None | str | Unset
        if isinstance(self.layout, Unset):
            layout = UNSET
        else:
            layout = self.layout

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nome": nome,
            }
        )
        if origem is not UNSET:
            field_dict["origem"] = origem
        if modelo is not UNSET:
            field_dict["modelo"] = modelo
        if layout is not UNSET:
            field_dict["layout"] = layout

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.diagrama_entrada_origem import DiagramaEntradaOrigem  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        _origem = d.pop("origem", UNSET)
        origem: DiagramaEntradaOrigem | Unset
        if isinstance(_origem, Unset):
            origem = UNSET
        else:
            origem = DiagramaEntradaOrigem.from_dict(_origem)

        modelo = d.pop("modelo", UNSET)

        def _parse_layout(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        layout = _parse_layout(d.pop("layout", UNSET))

        diagrama_entrada = cls(
            nome=nome,
            origem=origem,
            modelo=modelo,
            layout=layout,
        )

        diagrama_entrada.additional_properties = d
        return diagrama_entrada

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
