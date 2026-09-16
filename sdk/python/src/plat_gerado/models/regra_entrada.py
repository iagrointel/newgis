from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="RegraEntrada")


@_attrs_define
class RegraEntrada:
    """
    Attributes:
        id (str):
        tipo (str):
        expressao (str):
        nome (None | str | Unset):
        campo (None | str | Unset):
        gatilhos (list[str] | None | Unset):
        eventos (list[str] | None | Unset):
        ordem (int | Unset):  Default: 0.
        habilitada (bool | Unset):  Default: True.
        mensagem (None | str | Unset):
        codigo (None | str | Unset):
        excluir_em_massa (bool | Unset):  Default: False.
    """

    id: str
    tipo: str
    expressao: str
    nome: None | str | Unset = UNSET
    campo: None | str | Unset = UNSET
    gatilhos: list[str] | None | Unset = UNSET
    eventos: list[str] | None | Unset = UNSET
    ordem: int | Unset = 0
    habilitada: bool | Unset = True
    mensagem: None | str | Unset = UNSET
    codigo: None | str | Unset = UNSET
    excluir_em_massa: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        tipo = self.tipo

        expressao = self.expressao

        nome: None | str | Unset
        if isinstance(self.nome, Unset):
            nome = UNSET
        else:
            nome = self.nome

        campo: None | str | Unset
        if isinstance(self.campo, Unset):
            campo = UNSET
        else:
            campo = self.campo

        gatilhos: list[str] | None | Unset
        if isinstance(self.gatilhos, Unset):
            gatilhos = UNSET
        elif isinstance(self.gatilhos, list):
            gatilhos = self.gatilhos

        else:
            gatilhos = self.gatilhos

        eventos: list[str] | None | Unset
        if isinstance(self.eventos, Unset):
            eventos = UNSET
        elif isinstance(self.eventos, list):
            eventos = self.eventos

        else:
            eventos = self.eventos

        ordem = self.ordem

        habilitada = self.habilitada

        mensagem: None | str | Unset
        if isinstance(self.mensagem, Unset):
            mensagem = UNSET
        else:
            mensagem = self.mensagem

        codigo: None | str | Unset
        if isinstance(self.codigo, Unset):
            codigo = UNSET
        else:
            codigo = self.codigo

        excluir_em_massa = self.excluir_em_massa

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "tipo": tipo,
                "expressao": expressao,
            }
        )
        if nome is not UNSET:
            field_dict["nome"] = nome
        if campo is not UNSET:
            field_dict["campo"] = campo
        if gatilhos is not UNSET:
            field_dict["gatilhos"] = gatilhos
        if eventos is not UNSET:
            field_dict["eventos"] = eventos
        if ordem is not UNSET:
            field_dict["ordem"] = ordem
        if habilitada is not UNSET:
            field_dict["habilitada"] = habilitada
        if mensagem is not UNSET:
            field_dict["mensagem"] = mensagem
        if codigo is not UNSET:
            field_dict["codigo"] = codigo
        if excluir_em_massa is not UNSET:
            field_dict["excluir_em_massa"] = excluir_em_massa

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        tipo = d.pop("tipo")

        expressao = d.pop("expressao")

        def _parse_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome = _parse_nome(d.pop("nome", UNSET))

        def _parse_campo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        campo = _parse_campo(d.pop("campo", UNSET))

        def _parse_gatilhos(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                gatilhos_type_0 = cast(list[str], data)

                return gatilhos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        gatilhos = _parse_gatilhos(d.pop("gatilhos", UNSET))

        def _parse_eventos(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                eventos_type_0 = cast(list[str], data)

                return eventos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        eventos = _parse_eventos(d.pop("eventos", UNSET))

        ordem = d.pop("ordem", UNSET)

        habilitada = d.pop("habilitada", UNSET)

        def _parse_mensagem(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mensagem = _parse_mensagem(d.pop("mensagem", UNSET))

        def _parse_codigo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        codigo = _parse_codigo(d.pop("codigo", UNSET))

        excluir_em_massa = d.pop("excluir_em_massa", UNSET)

        regra_entrada = cls(
            id=id,
            tipo=tipo,
            expressao=expressao,
            nome=nome,
            campo=campo,
            gatilhos=gatilhos,
            eventos=eventos,
            ordem=ordem,
            habilitada=habilitada,
            mensagem=mensagem,
            codigo=codigo,
            excluir_em_massa=excluir_em_massa,
        )

        return regra_entrada
