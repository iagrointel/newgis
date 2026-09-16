from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="AcervoAssinaturaEntrada")


@_attrs_define
class AcervoAssinaturaEntrada:
    """Corpo OBRIGATÓRIO de POST /api/acervo/camadas/{camada}/assinatura (item L6-01-e). O clique na
    licença chega como `aceite_licenca=true` + o sha256 do texto que estava na tela: o servidor só grava se
    o sha bater com o texto atual da fonte — sha defasado é 409 (a tela relê e mostra o texto novo).
    Default False/"": nunca se aceita sozinho.

        Attributes:
            aceite_licenca (bool | Unset):  Default: False.
            licenca_sha256 (str | Unset):  Default: ''.
    """

    aceite_licenca: bool | Unset = False
    licenca_sha256: str | Unset = ""

    def to_dict(self) -> dict[str, Any]:
        aceite_licenca = self.aceite_licenca

        licenca_sha256 = self.licenca_sha256

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if aceite_licenca is not UNSET:
            field_dict["aceite_licenca"] = aceite_licenca
        if licenca_sha256 is not UNSET:
            field_dict["licenca_sha256"] = licenca_sha256

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        aceite_licenca = d.pop("aceite_licenca", UNSET)

        licenca_sha256 = d.pop("licenca_sha256", UNSET)

        acervo_assinatura_entrada = cls(
            aceite_licenca=aceite_licenca,
            licenca_sha256=licenca_sha256,
        )

        return acervo_assinatura_entrada
