from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.camada_baixada import CamadaBaixada
    from ..models.conflito import Conflito
    from ..models.sincronizar_saida_subidas import SincronizarSaidaSubidas


T = TypeVar("T", bound="SincronizarSaida")


@_attrs_define
class SincronizarSaida:
    """
    Attributes:
        replica_id (str):
        geracao (int):
        repetida (bool | Unset):  Default: False.
        subidas (SincronizarSaidaSubidas | Unset):
        conflitos (list[Conflito] | Unset):
        baixadas (list[CamadaBaixada] | Unset):
        avisos (list[str] | Unset):
    """

    replica_id: str
    geracao: int
    repetida: bool | Unset = False
    subidas: SincronizarSaidaSubidas | Unset = UNSET
    conflitos: list[Conflito] | Unset = UNSET
    baixadas: list[CamadaBaixada] | Unset = UNSET
    avisos: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        replica_id = self.replica_id

        geracao = self.geracao

        repetida = self.repetida

        subidas: dict[str, Any] | Unset = UNSET
        if not isinstance(self.subidas, Unset):
            subidas = self.subidas.to_dict()

        conflitos: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.conflitos, Unset):
            conflitos = []
            for conflitos_item_data in self.conflitos:
                conflitos_item = conflitos_item_data.to_dict()
                conflitos.append(conflitos_item)

        baixadas: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.baixadas, Unset):
            baixadas = []
            for baixadas_item_data in self.baixadas:
                baixadas_item = baixadas_item_data.to_dict()
                baixadas.append(baixadas_item)

        avisos: list[str] | Unset = UNSET
        if not isinstance(self.avisos, Unset):
            avisos = self.avisos

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "replica_id": replica_id,
                "geracao": geracao,
            }
        )
        if repetida is not UNSET:
            field_dict["repetida"] = repetida
        if subidas is not UNSET:
            field_dict["subidas"] = subidas
        if conflitos is not UNSET:
            field_dict["conflitos"] = conflitos
        if baixadas is not UNSET:
            field_dict["baixadas"] = baixadas
        if avisos is not UNSET:
            field_dict["avisos"] = avisos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.camada_baixada import CamadaBaixada  # noqa: PLC0415
        from ..models.conflito import Conflito  # noqa: PLC0415
        from ..models.sincronizar_saida_subidas import SincronizarSaidaSubidas  # noqa: PLC0415

        d = dict(src_dict)
        replica_id = d.pop("replica_id")

        geracao = d.pop("geracao")

        repetida = d.pop("repetida", UNSET)

        _subidas = d.pop("subidas", UNSET)
        subidas: SincronizarSaidaSubidas | Unset
        if isinstance(_subidas, Unset):
            subidas = UNSET
        else:
            subidas = SincronizarSaidaSubidas.from_dict(_subidas)

        _conflitos = d.pop("conflitos", UNSET)
        conflitos: list[Conflito] | Unset = UNSET
        if _conflitos is not UNSET:
            conflitos = []
            for conflitos_item_data in _conflitos:
                conflitos_item = Conflito.from_dict(conflitos_item_data)

                conflitos.append(conflitos_item)

        _baixadas = d.pop("baixadas", UNSET)
        baixadas: list[CamadaBaixada] | Unset = UNSET
        if _baixadas is not UNSET:
            baixadas = []
            for baixadas_item_data in _baixadas:
                baixadas_item = CamadaBaixada.from_dict(baixadas_item_data)

                baixadas.append(baixadas_item)

        avisos = cast(list[str], d.pop("avisos", UNSET))

        sincronizar_saida = cls(
            replica_id=replica_id,
            geracao=geracao,
            repetida=repetida,
            subidas=subidas,
            conflitos=conflitos,
            baixadas=baixadas,
            avisos=avisos,
        )

        sincronizar_saida.additional_properties = d
        return sincronizar_saida

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
