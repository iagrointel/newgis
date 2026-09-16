from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.camada_externa import CamadaExterna


T = TypeVar("T", bound="DescobrirResultado")


@_attrs_define
class DescobrirResultado:
    """
    Attributes:
        ok (bool):
        mensagem (str):
        total (int):
        itens (list[CamadaExterna]):
        url_sondada (None | str | Unset):
    """

    ok: bool
    mensagem: str
    total: int
    itens: list[CamadaExterna]
    url_sondada: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ok = self.ok

        mensagem = self.mensagem

        total = self.total

        itens = []
        for itens_item_data in self.itens:
            itens_item = itens_item_data.to_dict()
            itens.append(itens_item)

        url_sondada: None | str | Unset
        if isinstance(self.url_sondada, Unset):
            url_sondada = UNSET
        else:
            url_sondada = self.url_sondada

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ok": ok,
                "mensagem": mensagem,
                "total": total,
                "itens": itens,
            }
        )
        if url_sondada is not UNSET:
            field_dict["url_sondada"] = url_sondada

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.camada_externa import CamadaExterna  # noqa: PLC0415

        d = dict(src_dict)
        ok = d.pop("ok")

        mensagem = d.pop("mensagem")

        total = d.pop("total")

        itens = []
        _itens = d.pop("itens")
        for itens_item_data in _itens:
            itens_item = CamadaExterna.from_dict(itens_item_data)

            itens.append(itens_item)

        def _parse_url_sondada(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        url_sondada = _parse_url_sondada(d.pop("url_sondada", UNSET))

        descobrir_resultado = cls(
            ok=ok,
            mensagem=mensagem,
            total=total,
            itens=itens,
            url_sondada=url_sondada,
        )

        descobrir_resultado.additional_properties = d
        return descobrir_resultado

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
