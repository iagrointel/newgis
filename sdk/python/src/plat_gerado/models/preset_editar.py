from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.preset_editar_escopo_type_0 import PresetEditarEscopoType0
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.preset_editar_conteudo_type_0 import PresetEditarConteudoType0


T = TypeVar("T", bound="PresetEditar")


@_attrs_define
class PresetEditar:
    """
    Attributes:
        nome (None | str | Unset):
        descricao (None | str | Unset):
        escopo (None | PresetEditarEscopoType0 | Unset):
        conteudo (None | PresetEditarConteudoType0 | Unset):
    """

    nome: None | str | Unset = UNSET
    descricao: None | str | Unset = UNSET
    escopo: None | PresetEditarEscopoType0 | Unset = UNSET
    conteudo: None | PresetEditarConteudoType0 | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.preset_editar_conteudo_type_0 import PresetEditarConteudoType0  # noqa: PLC0415

        nome: None | str | Unset
        if isinstance(self.nome, Unset):
            nome = UNSET
        else:
            nome = self.nome

        descricao: None | str | Unset
        if isinstance(self.descricao, Unset):
            descricao = UNSET
        else:
            descricao = self.descricao

        escopo: None | str | Unset
        if isinstance(self.escopo, Unset):
            escopo = UNSET
        elif isinstance(self.escopo, PresetEditarEscopoType0):
            escopo = self.escopo.value
        else:
            escopo = self.escopo

        conteudo: dict[str, Any] | None | Unset
        if isinstance(self.conteudo, Unset):
            conteudo = UNSET
        elif isinstance(self.conteudo, PresetEditarConteudoType0):
            conteudo = self.conteudo.to_dict()
        else:
            conteudo = self.conteudo

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if nome is not UNSET:
            field_dict["nome"] = nome
        if descricao is not UNSET:
            field_dict["descricao"] = descricao
        if escopo is not UNSET:
            field_dict["escopo"] = escopo
        if conteudo is not UNSET:
            field_dict["conteudo"] = conteudo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.preset_editar_conteudo_type_0 import PresetEditarConteudoType0  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome = _parse_nome(d.pop("nome", UNSET))

        def _parse_descricao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        descricao = _parse_descricao(d.pop("descricao", UNSET))

        def _parse_escopo(data: object) -> None | PresetEditarEscopoType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                escopo_type_0 = PresetEditarEscopoType0(data)

                return escopo_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PresetEditarEscopoType0 | Unset, data)

        escopo = _parse_escopo(d.pop("escopo", UNSET))

        def _parse_conteudo(data: object) -> None | PresetEditarConteudoType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                conteudo_type_0 = PresetEditarConteudoType0.from_dict(data)

                return conteudo_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PresetEditarConteudoType0 | Unset, data)

        conteudo = _parse_conteudo(d.pop("conteudo", UNSET))

        preset_editar = cls(
            nome=nome,
            descricao=descricao,
            escopo=escopo,
            conteudo=conteudo,
        )

        return preset_editar
