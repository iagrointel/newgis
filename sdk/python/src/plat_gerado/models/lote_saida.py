from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.lote_falha import LoteFalha
    from ..models.lote_previa import LotePrevia


T = TypeVar("T", bound="LoteSaida")


@_attrs_define
class LoteSaida:
    """
    Attributes:
        execucao (str):
        operacao (str):
        total (int):
        alteradas (int | Unset):  Default: 0.
        apagadas (int | Unset):  Default: 0.
        criadas (int | Unset):  Default: 0.
        corrigidas (int | Unset):  Default: 0.
        falhas (list[LoteFalha] | Unset):
        falhas_total (int | Unset):  Default: 0.
        avisos (list[str] | Unset):
        traducao (None | str | Unset):
        traducao_motivo (None | str | Unset):
        job_id (None | str | Unset):
        previa (list[LotePrevia] | None | Unset):
        duracao_ms (int | None | Unset):
    """

    execucao: str
    operacao: str
    total: int
    alteradas: int | Unset = 0
    apagadas: int | Unset = 0
    criadas: int | Unset = 0
    corrigidas: int | Unset = 0
    falhas: list[LoteFalha] | Unset = UNSET
    falhas_total: int | Unset = 0
    avisos: list[str] | Unset = UNSET
    traducao: None | str | Unset = UNSET
    traducao_motivo: None | str | Unset = UNSET
    job_id: None | str | Unset = UNSET
    previa: list[LotePrevia] | None | Unset = UNSET
    duracao_ms: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        execucao = self.execucao

        operacao = self.operacao

        total = self.total

        alteradas = self.alteradas

        apagadas = self.apagadas

        criadas = self.criadas

        corrigidas = self.corrigidas

        falhas: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.falhas, Unset):
            falhas = []
            for falhas_item_data in self.falhas:
                falhas_item = falhas_item_data.to_dict()
                falhas.append(falhas_item)

        falhas_total = self.falhas_total

        avisos: list[str] | Unset = UNSET
        if not isinstance(self.avisos, Unset):
            avisos = self.avisos

        traducao: None | str | Unset
        if isinstance(self.traducao, Unset):
            traducao = UNSET
        else:
            traducao = self.traducao

        traducao_motivo: None | str | Unset
        if isinstance(self.traducao_motivo, Unset):
            traducao_motivo = UNSET
        else:
            traducao_motivo = self.traducao_motivo

        job_id: None | str | Unset
        if isinstance(self.job_id, Unset):
            job_id = UNSET
        else:
            job_id = self.job_id

        previa: list[dict[str, Any]] | None | Unset
        if isinstance(self.previa, Unset):
            previa = UNSET
        elif isinstance(self.previa, list):
            previa = []
            for previa_type_0_item_data in self.previa:
                previa_type_0_item = previa_type_0_item_data.to_dict()
                previa.append(previa_type_0_item)

        else:
            previa = self.previa

        duracao_ms: int | None | Unset
        if isinstance(self.duracao_ms, Unset):
            duracao_ms = UNSET
        else:
            duracao_ms = self.duracao_ms

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "execucao": execucao,
                "operacao": operacao,
                "total": total,
            }
        )
        if alteradas is not UNSET:
            field_dict["alteradas"] = alteradas
        if apagadas is not UNSET:
            field_dict["apagadas"] = apagadas
        if criadas is not UNSET:
            field_dict["criadas"] = criadas
        if corrigidas is not UNSET:
            field_dict["corrigidas"] = corrigidas
        if falhas is not UNSET:
            field_dict["falhas"] = falhas
        if falhas_total is not UNSET:
            field_dict["falhas_total"] = falhas_total
        if avisos is not UNSET:
            field_dict["avisos"] = avisos
        if traducao is not UNSET:
            field_dict["traducao"] = traducao
        if traducao_motivo is not UNSET:
            field_dict["traducao_motivo"] = traducao_motivo
        if job_id is not UNSET:
            field_dict["job_id"] = job_id
        if previa is not UNSET:
            field_dict["previa"] = previa
        if duracao_ms is not UNSET:
            field_dict["duracao_ms"] = duracao_ms

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.lote_falha import LoteFalha  # noqa: PLC0415
        from ..models.lote_previa import LotePrevia  # noqa: PLC0415

        d = dict(src_dict)
        execucao = d.pop("execucao")

        operacao = d.pop("operacao")

        total = d.pop("total")

        alteradas = d.pop("alteradas", UNSET)

        apagadas = d.pop("apagadas", UNSET)

        criadas = d.pop("criadas", UNSET)

        corrigidas = d.pop("corrigidas", UNSET)

        _falhas = d.pop("falhas", UNSET)
        falhas: list[LoteFalha] | Unset = UNSET
        if _falhas is not UNSET:
            falhas = []
            for falhas_item_data in _falhas:
                falhas_item = LoteFalha.from_dict(falhas_item_data)

                falhas.append(falhas_item)

        falhas_total = d.pop("falhas_total", UNSET)

        avisos = cast(list[str], d.pop("avisos", UNSET))

        def _parse_traducao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        traducao = _parse_traducao(d.pop("traducao", UNSET))

        def _parse_traducao_motivo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        traducao_motivo = _parse_traducao_motivo(d.pop("traducao_motivo", UNSET))

        def _parse_job_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        job_id = _parse_job_id(d.pop("job_id", UNSET))

        def _parse_previa(data: object) -> list[LotePrevia] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                previa_type_0 = []
                _previa_type_0 = data
                for previa_type_0_item_data in _previa_type_0:
                    previa_type_0_item = LotePrevia.from_dict(previa_type_0_item_data)

                    previa_type_0.append(previa_type_0_item)

                return previa_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[LotePrevia] | None | Unset, data)

        previa = _parse_previa(d.pop("previa", UNSET))

        def _parse_duracao_ms(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        duracao_ms = _parse_duracao_ms(d.pop("duracao_ms", UNSET))

        lote_saida = cls(
            execucao=execucao,
            operacao=operacao,
            total=total,
            alteradas=alteradas,
            apagadas=apagadas,
            criadas=criadas,
            corrigidas=corrigidas,
            falhas=falhas,
            falhas_total=falhas_total,
            avisos=avisos,
            traducao=traducao,
            traducao_motivo=traducao_motivo,
            job_id=job_id,
            previa=previa,
            duracao_ms=duracao_ms,
        )

        lote_saida.additional_properties = d
        return lote_saida

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
