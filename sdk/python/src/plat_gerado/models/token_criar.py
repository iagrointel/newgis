from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.token_criar_restricao_type_0 import TokenCriarRestricaoType0


T = TypeVar("T", bound="TokenCriar")


@_attrs_define
class TokenCriar:
    """
    Attributes:
        nome (str):
        escopos (list[str]):
        restricao (None | TokenCriarRestricaoType0 | Unset):
        validade_dias (int | None | Unset):
    """

    nome: str
    escopos: list[str]
    restricao: None | TokenCriarRestricaoType0 | Unset = UNSET
    validade_dias: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.token_criar_restricao_type_0 import TokenCriarRestricaoType0  # noqa: PLC0415

        nome = self.nome

        escopos = self.escopos

        restricao: dict[str, Any] | None | Unset
        if isinstance(self.restricao, Unset):
            restricao = UNSET
        elif isinstance(self.restricao, TokenCriarRestricaoType0):
            restricao = self.restricao.to_dict()
        else:
            restricao = self.restricao

        validade_dias: int | None | Unset
        if isinstance(self.validade_dias, Unset):
            validade_dias = UNSET
        else:
            validade_dias = self.validade_dias

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "escopos": escopos,
            }
        )
        if restricao is not UNSET:
            field_dict["restricao"] = restricao
        if validade_dias is not UNSET:
            field_dict["validade_dias"] = validade_dias

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.token_criar_restricao_type_0 import TokenCriarRestricaoType0  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        escopos = cast(list[str], d.pop("escopos"))

        def _parse_restricao(data: object) -> None | TokenCriarRestricaoType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                restricao_type_0 = TokenCriarRestricaoType0.from_dict(data)

                return restricao_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TokenCriarRestricaoType0 | Unset, data)

        restricao = _parse_restricao(d.pop("restricao", UNSET))

        def _parse_validade_dias(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        validade_dias = _parse_validade_dias(d.pop("validade_dias", UNSET))

        token_criar = cls(
            nome=nome,
            escopos=escopos,
            restricao=restricao,
            validade_dias=validade_dias,
        )

        return token_criar
