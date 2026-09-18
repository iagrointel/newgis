from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.preset_importar_escopo import PresetImportarEscopo
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.preset_importar_conteudo import PresetImportarConteudo


T = TypeVar("T", bound="PresetImportar")


@_attrs_define
class PresetImportar:
    """Documento gerado por GET .../exportar. `fatores_modelo` é OPCIONAL: quando informado, preset
    que declara fator fora dessa lista é recusado com a lista do que falta (refutação do item).

        Attributes:
            formato (str):
            versao (int):
            nome (str):
            conteudo (PresetImportarConteudo):
            descricao (str | Unset):  Default: ''.
            escopo (PresetImportarEscopo | Unset):  Default: PresetImportarEscopo.USUARIO.
            integrado (bool | None | Unset):
            fatores_modelo (list[str] | None | Unset):
    """

    formato: str
    versao: int
    nome: str
    conteudo: PresetImportarConteudo
    descricao: str | Unset = ""
    escopo: PresetImportarEscopo | Unset = PresetImportarEscopo.USUARIO
    integrado: bool | None | Unset = UNSET
    fatores_modelo: list[str] | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        formato = self.formato

        versao = self.versao

        nome = self.nome

        conteudo = self.conteudo.to_dict()

        descricao = self.descricao

        escopo: str | Unset = UNSET
        if not isinstance(self.escopo, Unset):
            escopo = self.escopo.value

        integrado: bool | None | Unset
        if isinstance(self.integrado, Unset):
            integrado = UNSET
        else:
            integrado = self.integrado

        fatores_modelo: list[str] | None | Unset
        if isinstance(self.fatores_modelo, Unset):
            fatores_modelo = UNSET
        elif isinstance(self.fatores_modelo, list):
            fatores_modelo = self.fatores_modelo

        else:
            fatores_modelo = self.fatores_modelo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "formato": formato,
                "versao": versao,
                "nome": nome,
                "conteudo": conteudo,
            }
        )
        if descricao is not UNSET:
            field_dict["descricao"] = descricao
        if escopo is not UNSET:
            field_dict["escopo"] = escopo
        if integrado is not UNSET:
            field_dict["integrado"] = integrado
        if fatores_modelo is not UNSET:
            field_dict["fatores_modelo"] = fatores_modelo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.preset_importar_conteudo import PresetImportarConteudo  # noqa: PLC0415

        d = dict(src_dict)
        formato = d.pop("formato")

        versao = d.pop("versao")

        nome = d.pop("nome")

        conteudo = PresetImportarConteudo.from_dict(d.pop("conteudo"))

        descricao = d.pop("descricao", UNSET)

        _escopo = d.pop("escopo", UNSET)
        escopo: PresetImportarEscopo | Unset
        if isinstance(_escopo, Unset):
            escopo = UNSET
        else:
            escopo = PresetImportarEscopo(_escopo)

        def _parse_integrado(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        integrado = _parse_integrado(d.pop("integrado", UNSET))

        def _parse_fatores_modelo(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                fatores_modelo_type_0 = cast(list[str], data)

                return fatores_modelo_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        fatores_modelo = _parse_fatores_modelo(d.pop("fatores_modelo", UNSET))

        preset_importar = cls(
            formato=formato,
            versao=versao,
            nome=nome,
            conteudo=conteudo,
            descricao=descricao,
            escopo=escopo,
            integrado=integrado,
            fatores_modelo=fatores_modelo,
        )

        return preset_importar
