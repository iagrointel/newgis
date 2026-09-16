from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.leitura_entrada_bruta import LeituraEntradaBruta


T = TypeVar("T", bound="LeituraEntrada")


@_attrs_define
class LeituraEntrada:
    """
    Attributes:
        ativo (str):
        ts (str): ISO-8601, relógio do sensor
        fonte (str): ex.: simulador, sonda, conector
        grandeza (str):
        valor (float):
        unidade (str):
        cod_id (None | str | Unset):
        bruta (LeituraEntradaBruta | Unset): leitura crua do sensor, nunca interpretada
    """

    ativo: str
    ts: str
    fonte: str
    grandeza: str
    valor: float
    unidade: str
    cod_id: None | str | Unset = UNSET
    bruta: LeituraEntradaBruta | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        ativo = self.ativo

        ts = self.ts

        fonte = self.fonte

        grandeza = self.grandeza

        valor = self.valor

        unidade = self.unidade

        cod_id: None | str | Unset
        if isinstance(self.cod_id, Unset):
            cod_id = UNSET
        else:
            cod_id = self.cod_id

        bruta: dict[str, Any] | Unset = UNSET
        if not isinstance(self.bruta, Unset):
            bruta = self.bruta.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "ativo": ativo,
                "ts": ts,
                "fonte": fonte,
                "grandeza": grandeza,
                "valor": valor,
                "unidade": unidade,
            }
        )
        if cod_id is not UNSET:
            field_dict["cod_id"] = cod_id
        if bruta is not UNSET:
            field_dict["bruta"] = bruta

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.leitura_entrada_bruta import LeituraEntradaBruta  # noqa: PLC0415

        d = dict(src_dict)
        ativo = d.pop("ativo")

        ts = d.pop("ts")

        fonte = d.pop("fonte")

        grandeza = d.pop("grandeza")

        valor = d.pop("valor")

        unidade = d.pop("unidade")

        def _parse_cod_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cod_id = _parse_cod_id(d.pop("cod_id", UNSET))

        _bruta = d.pop("bruta", UNSET)
        bruta: LeituraEntradaBruta | Unset
        if isinstance(_bruta, Unset):
            bruta = UNSET
        else:
            bruta = LeituraEntradaBruta.from_dict(_bruta)

        leitura_entrada = cls(
            ativo=ativo,
            ts=ts,
            fonte=fonte,
            grandeza=grandeza,
            valor=valor,
            unidade=unidade,
            cod_id=cod_id,
            bruta=bruta,
        )

        return leitura_entrada
