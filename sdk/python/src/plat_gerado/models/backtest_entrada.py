from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.ponto import Ponto


T = TypeVar("T", bound="BacktestEntrada")


@_attrs_define
class BacktestEntrada:
    """
    Attributes:
        escolhas_item_id (None | str | Unset):
        pontos (list[Ponto] | None | Unset):
        n_permutacoes (int | Unset):  Default: 1000.
        semente (int | Unset):  Default: 0.
        data_decisao (None | str | Unset):
        data_camada (None | str | Unset):
        preferencia_revelada (bool | Unset):  Default: True.
    """

    escolhas_item_id: None | str | Unset = UNSET
    pontos: list[Ponto] | None | Unset = UNSET
    n_permutacoes: int | Unset = 1000
    semente: int | Unset = 0
    data_decisao: None | str | Unset = UNSET
    data_camada: None | str | Unset = UNSET
    preferencia_revelada: bool | Unset = True

    def to_dict(self) -> dict[str, Any]:
        escolhas_item_id: None | str | Unset
        if isinstance(self.escolhas_item_id, Unset):
            escolhas_item_id = UNSET
        else:
            escolhas_item_id = self.escolhas_item_id

        pontos: list[dict[str, Any]] | None | Unset
        if isinstance(self.pontos, Unset):
            pontos = UNSET
        elif isinstance(self.pontos, list):
            pontos = []
            for pontos_type_0_item_data in self.pontos:
                pontos_type_0_item = pontos_type_0_item_data.to_dict()
                pontos.append(pontos_type_0_item)

        else:
            pontos = self.pontos

        n_permutacoes = self.n_permutacoes

        semente = self.semente

        data_decisao: None | str | Unset
        if isinstance(self.data_decisao, Unset):
            data_decisao = UNSET
        else:
            data_decisao = self.data_decisao

        data_camada: None | str | Unset
        if isinstance(self.data_camada, Unset):
            data_camada = UNSET
        else:
            data_camada = self.data_camada

        preferencia_revelada = self.preferencia_revelada

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if escolhas_item_id is not UNSET:
            field_dict["escolhas_item_id"] = escolhas_item_id
        if pontos is not UNSET:
            field_dict["pontos"] = pontos
        if n_permutacoes is not UNSET:
            field_dict["n_permutacoes"] = n_permutacoes
        if semente is not UNSET:
            field_dict["semente"] = semente
        if data_decisao is not UNSET:
            field_dict["data_decisao"] = data_decisao
        if data_camada is not UNSET:
            field_dict["data_camada"] = data_camada
        if preferencia_revelada is not UNSET:
            field_dict["preferencia_revelada"] = preferencia_revelada

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ponto import Ponto  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_escolhas_item_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        escolhas_item_id = _parse_escolhas_item_id(d.pop("escolhas_item_id", UNSET))

        def _parse_pontos(data: object) -> list[Ponto] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                pontos_type_0 = []
                _pontos_type_0 = data
                for pontos_type_0_item_data in _pontos_type_0:
                    pontos_type_0_item = Ponto.from_dict(pontos_type_0_item_data)

                    pontos_type_0.append(pontos_type_0_item)

                return pontos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[Ponto] | None | Unset, data)

        pontos = _parse_pontos(d.pop("pontos", UNSET))

        n_permutacoes = d.pop("n_permutacoes", UNSET)

        semente = d.pop("semente", UNSET)

        def _parse_data_decisao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        data_decisao = _parse_data_decisao(d.pop("data_decisao", UNSET))

        def _parse_data_camada(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        data_camada = _parse_data_camada(d.pop("data_camada", UNSET))

        preferencia_revelada = d.pop("preferencia_revelada", UNSET)

        backtest_entrada = cls(
            escolhas_item_id=escolhas_item_id,
            pontos=pontos,
            n_permutacoes=n_permutacoes,
            semente=semente,
            data_decisao=data_decisao,
            data_camada=data_camada,
            preferencia_revelada=preferencia_revelada,
        )

        return backtest_entrada
