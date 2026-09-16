from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.execucao_fator_saida import ExecucaoFatorSaida
    from ..models.grade_saida import GradeSaida


T = TypeVar("T", bound="Execucao")


@_attrs_define
class Execucao:
    """
    Attributes:
        id (str):
        conjunto_id (str):
        nivel (str):
        aprovacao_tipo (str):
        aprovacao_valor (float):
        celulas (int):
        celulas_possiveis (int):
        celulas_com_nota (int):
        celulas_aprovadas (int):
        duracao_ms (int):
        criado_em (str):
        grade (GradeSaida):
        fatores (list[ExecucaoFatorSaida]):
        execucao_pai_id (None | str | Unset):
    """

    id: str
    conjunto_id: str
    nivel: str
    aprovacao_tipo: str
    aprovacao_valor: float
    celulas: int
    celulas_possiveis: int
    celulas_com_nota: int
    celulas_aprovadas: int
    duracao_ms: int
    criado_em: str
    grade: GradeSaida
    fatores: list[ExecucaoFatorSaida]
    execucao_pai_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        conjunto_id = self.conjunto_id

        nivel = self.nivel

        aprovacao_tipo = self.aprovacao_tipo

        aprovacao_valor = self.aprovacao_valor

        celulas = self.celulas

        celulas_possiveis = self.celulas_possiveis

        celulas_com_nota = self.celulas_com_nota

        celulas_aprovadas = self.celulas_aprovadas

        duracao_ms = self.duracao_ms

        criado_em = self.criado_em

        grade = self.grade.to_dict()

        fatores = []
        for fatores_item_data in self.fatores:
            fatores_item = fatores_item_data.to_dict()
            fatores.append(fatores_item)

        execucao_pai_id: None | str | Unset
        if isinstance(self.execucao_pai_id, Unset):
            execucao_pai_id = UNSET
        else:
            execucao_pai_id = self.execucao_pai_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "conjunto_id": conjunto_id,
                "nivel": nivel,
                "aprovacao_tipo": aprovacao_tipo,
                "aprovacao_valor": aprovacao_valor,
                "celulas": celulas,
                "celulas_possiveis": celulas_possiveis,
                "celulas_com_nota": celulas_com_nota,
                "celulas_aprovadas": celulas_aprovadas,
                "duracao_ms": duracao_ms,
                "criado_em": criado_em,
                "grade": grade,
                "fatores": fatores,
            }
        )
        if execucao_pai_id is not UNSET:
            field_dict["execucao_pai_id"] = execucao_pai_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.execucao_fator_saida import ExecucaoFatorSaida  # noqa: PLC0415
        from ..models.grade_saida import GradeSaida  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        conjunto_id = d.pop("conjunto_id")

        nivel = d.pop("nivel")

        aprovacao_tipo = d.pop("aprovacao_tipo")

        aprovacao_valor = d.pop("aprovacao_valor")

        celulas = d.pop("celulas")

        celulas_possiveis = d.pop("celulas_possiveis")

        celulas_com_nota = d.pop("celulas_com_nota")

        celulas_aprovadas = d.pop("celulas_aprovadas")

        duracao_ms = d.pop("duracao_ms")

        criado_em = d.pop("criado_em")

        grade = GradeSaida.from_dict(d.pop("grade"))

        fatores = []
        _fatores = d.pop("fatores")
        for fatores_item_data in _fatores:
            fatores_item = ExecucaoFatorSaida.from_dict(fatores_item_data)

            fatores.append(fatores_item)

        def _parse_execucao_pai_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        execucao_pai_id = _parse_execucao_pai_id(d.pop("execucao_pai_id", UNSET))

        execucao = cls(
            id=id,
            conjunto_id=conjunto_id,
            nivel=nivel,
            aprovacao_tipo=aprovacao_tipo,
            aprovacao_valor=aprovacao_valor,
            celulas=celulas,
            celulas_possiveis=celulas_possiveis,
            celulas_com_nota=celulas_com_nota,
            celulas_aprovadas=celulas_aprovadas,
            duracao_ms=duracao_ms,
            criado_em=criado_em,
            grade=grade,
            fatores=fatores,
            execucao_pai_id=execucao_pai_id,
        )

        execucao.additional_properties = d
        return execucao

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
