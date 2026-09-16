from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.lote_destino import LoteDestino
    from ..models.lote_selecao import LoteSelecao


T = TypeVar("T", bound="LoteEntrada")


@_attrs_define
class LoteEntrada:
    """
    Attributes:
        operacao (str):
        selecao (LoteSelecao): Exatamente uma das três formas: `ids` (globalids), `onde` (expressão booleana da
            linguagem L2-10-c sobre
            os campos da camada) ou `todas`.
        campo (None | str | Unset):
        expressao (None | str | Unset):
        valor (Any | Unset):
        destino (LoteDestino | None | Unset):
        modo (str | Unset):  Default: 'transacao'.
        previa (bool | Unset):  Default: False.
        avaliacao (str | Unset):  Default: 'auto'.
    """

    operacao: str
    selecao: LoteSelecao
    campo: None | str | Unset = UNSET
    expressao: None | str | Unset = UNSET
    valor: Any | Unset = UNSET
    destino: LoteDestino | None | Unset = UNSET
    modo: str | Unset = "transacao"
    previa: bool | Unset = False
    avaliacao: str | Unset = "auto"

    def to_dict(self) -> dict[str, Any]:
        from ..models.lote_destino import LoteDestino  # noqa: PLC0415

        operacao = self.operacao

        selecao = self.selecao.to_dict()

        campo: None | str | Unset
        if isinstance(self.campo, Unset):
            campo = UNSET
        else:
            campo = self.campo

        expressao: None | str | Unset
        if isinstance(self.expressao, Unset):
            expressao = UNSET
        else:
            expressao = self.expressao

        valor = self.valor

        destino: dict[str, Any] | None | Unset
        if isinstance(self.destino, Unset):
            destino = UNSET
        elif isinstance(self.destino, LoteDestino):
            destino = self.destino.to_dict()
        else:
            destino = self.destino

        modo = self.modo

        previa = self.previa

        avaliacao = self.avaliacao

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "operacao": operacao,
                "selecao": selecao,
            }
        )
        if campo is not UNSET:
            field_dict["campo"] = campo
        if expressao is not UNSET:
            field_dict["expressao"] = expressao
        if valor is not UNSET:
            field_dict["valor"] = valor
        if destino is not UNSET:
            field_dict["destino"] = destino
        if modo is not UNSET:
            field_dict["modo"] = modo
        if previa is not UNSET:
            field_dict["previa"] = previa
        if avaliacao is not UNSET:
            field_dict["avaliacao"] = avaliacao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.lote_destino import LoteDestino  # noqa: PLC0415
        from ..models.lote_selecao import LoteSelecao  # noqa: PLC0415

        d = dict(src_dict)
        operacao = d.pop("operacao")

        selecao = LoteSelecao.from_dict(d.pop("selecao"))

        def _parse_campo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        campo = _parse_campo(d.pop("campo", UNSET))

        def _parse_expressao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        expressao = _parse_expressao(d.pop("expressao", UNSET))

        valor = d.pop("valor", UNSET)

        def _parse_destino(data: object) -> LoteDestino | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                destino_type_0 = LoteDestino.from_dict(data)

                return destino_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(LoteDestino | None | Unset, data)

        destino = _parse_destino(d.pop("destino", UNSET))

        modo = d.pop("modo", UNSET)

        previa = d.pop("previa", UNSET)

        avaliacao = d.pop("avaliacao", UNSET)

        lote_entrada = cls(
            operacao=operacao,
            selecao=selecao,
            campo=campo,
            expressao=expressao,
            valor=valor,
            destino=destino,
            modo=modo,
            previa=previa,
            avaliacao=avaliacao,
        )

        return lote_entrada
