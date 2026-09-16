from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.anexo_resposta import AnexoResposta
    from ..models.resposta_entrada_repeticoes import RespostaEntradaRepeticoes
    from ..models.resposta_entrada_valores import RespostaEntradaValores


T = TypeVar("T", bound="RespostaEntrada")


@_attrs_define
class RespostaEntrada:
    """
    Attributes:
        valores (RespostaEntradaValores | Unset):
        repeticoes (RespostaEntradaRepeticoes | Unset):
        inicio (None | str | Unset):
        fim (None | str | Unset):
        dispositivo (None | str | Unset):
        anexos (list[AnexoResposta] | Unset):
    """

    valores: RespostaEntradaValores | Unset = UNSET
    repeticoes: RespostaEntradaRepeticoes | Unset = UNSET
    inicio: None | str | Unset = UNSET
    fim: None | str | Unset = UNSET
    dispositivo: None | str | Unset = UNSET
    anexos: list[AnexoResposta] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        valores: dict[str, Any] | Unset = UNSET
        if not isinstance(self.valores, Unset):
            valores = self.valores.to_dict()

        repeticoes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.repeticoes, Unset):
            repeticoes = self.repeticoes.to_dict()

        inicio: None | str | Unset
        if isinstance(self.inicio, Unset):
            inicio = UNSET
        else:
            inicio = self.inicio

        fim: None | str | Unset
        if isinstance(self.fim, Unset):
            fim = UNSET
        else:
            fim = self.fim

        dispositivo: None | str | Unset
        if isinstance(self.dispositivo, Unset):
            dispositivo = UNSET
        else:
            dispositivo = self.dispositivo

        anexos: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.anexos, Unset):
            anexos = []
            for anexos_item_data in self.anexos:
                anexos_item = anexos_item_data.to_dict()
                anexos.append(anexos_item)

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if valores is not UNSET:
            field_dict["valores"] = valores
        if repeticoes is not UNSET:
            field_dict["repeticoes"] = repeticoes
        if inicio is not UNSET:
            field_dict["inicio"] = inicio
        if fim is not UNSET:
            field_dict["fim"] = fim
        if dispositivo is not UNSET:
            field_dict["dispositivo"] = dispositivo
        if anexos is not UNSET:
            field_dict["anexos"] = anexos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.anexo_resposta import AnexoResposta  # noqa: PLC0415
        from ..models.resposta_entrada_repeticoes import RespostaEntradaRepeticoes  # noqa: PLC0415
        from ..models.resposta_entrada_valores import RespostaEntradaValores  # noqa: PLC0415

        d = dict(src_dict)
        _valores = d.pop("valores", UNSET)
        valores: RespostaEntradaValores | Unset
        if isinstance(_valores, Unset):
            valores = UNSET
        else:
            valores = RespostaEntradaValores.from_dict(_valores)

        _repeticoes = d.pop("repeticoes", UNSET)
        repeticoes: RespostaEntradaRepeticoes | Unset
        if isinstance(_repeticoes, Unset):
            repeticoes = UNSET
        else:
            repeticoes = RespostaEntradaRepeticoes.from_dict(_repeticoes)

        def _parse_inicio(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        inicio = _parse_inicio(d.pop("inicio", UNSET))

        def _parse_fim(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        fim = _parse_fim(d.pop("fim", UNSET))

        def _parse_dispositivo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dispositivo = _parse_dispositivo(d.pop("dispositivo", UNSET))

        _anexos = d.pop("anexos", UNSET)
        anexos: list[AnexoResposta] | Unset = UNSET
        if _anexos is not UNSET:
            anexos = []
            for anexos_item_data in _anexos:
                anexos_item = AnexoResposta.from_dict(anexos_item_data)

                anexos.append(anexos_item)

        resposta_entrada = cls(
            valores=valores,
            repeticoes=repeticoes,
            inicio=inicio,
            fim=fim,
            dispositivo=dispositivo,
            anexos=anexos,
        )

        return resposta_entrada
