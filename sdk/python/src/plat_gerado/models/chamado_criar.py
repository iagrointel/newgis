from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.chamado_criar_contexto import ChamadoCriarContexto


T = TypeVar("T", bound="ChamadoCriar")


@_attrs_define
class ChamadoCriar:
    """
    Attributes:
        titulo (str):
        descricao (str):
        severidade (str):
        contexto (ChamadoCriarContexto | Unset):
        captura (None | str | Unset):
    """

    titulo: str
    descricao: str
    severidade: str
    contexto: ChamadoCriarContexto | Unset = UNSET
    captura: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        titulo = self.titulo

        descricao = self.descricao

        severidade = self.severidade

        contexto: dict[str, Any] | Unset = UNSET
        if not isinstance(self.contexto, Unset):
            contexto = self.contexto.to_dict()

        captura: None | str | Unset
        if isinstance(self.captura, Unset):
            captura = UNSET
        else:
            captura = self.captura

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "titulo": titulo,
                "descricao": descricao,
                "severidade": severidade,
            }
        )
        if contexto is not UNSET:
            field_dict["contexto"] = contexto
        if captura is not UNSET:
            field_dict["captura"] = captura

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.chamado_criar_contexto import ChamadoCriarContexto  # noqa: PLC0415

        d = dict(src_dict)
        titulo = d.pop("titulo")

        descricao = d.pop("descricao")

        severidade = d.pop("severidade")

        _contexto = d.pop("contexto", UNSET)
        contexto: ChamadoCriarContexto | Unset
        if isinstance(_contexto, Unset):
            contexto = UNSET
        else:
            contexto = ChamadoCriarContexto.from_dict(_contexto)

        def _parse_captura(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        captura = _parse_captura(d.pop("captura", UNSET))

        chamado_criar = cls(
            titulo=titulo,
            descricao=descricao,
            severidade=severidade,
            contexto=contexto,
            captura=captura,
        )

        return chamado_criar
