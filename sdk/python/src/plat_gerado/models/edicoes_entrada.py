from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.crs import Crs
    from ..models.feicao_adicionar_edicao import FeicaoAdicionarEdicao
    from ..models.feicao_apagar import FeicaoApagar
    from ..models.feicao_atualizar_edicao import FeicaoAtualizarEdicao


T = TypeVar("T", bound="EdicoesEntrada")


@_attrs_define
class EdicoesEntrada:
    """
    Attributes:
        modo (str | Unset):  Default: 'transacao'.
        versao (None | str | Unset):
        crs (Crs | None | Unset):
        corrigir_geometria (bool | Unset):  Default: False.
        adicionar (list[FeicaoAdicionarEdicao] | Unset):
        atualizar (list[FeicaoAtualizarEdicao] | Unset):
        apagar (list[FeicaoApagar] | Unset):
    """

    modo: str | Unset = "transacao"
    versao: None | str | Unset = UNSET
    crs: Crs | None | Unset = UNSET
    corrigir_geometria: bool | Unset = False
    adicionar: list[FeicaoAdicionarEdicao] | Unset = UNSET
    atualizar: list[FeicaoAtualizarEdicao] | Unset = UNSET
    apagar: list[FeicaoApagar] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.crs import Crs  # noqa: PLC0415

        modo = self.modo

        versao: None | str | Unset
        if isinstance(self.versao, Unset):
            versao = UNSET
        else:
            versao = self.versao

        crs: dict[str, Any] | None | Unset
        if isinstance(self.crs, Unset):
            crs = UNSET
        elif isinstance(self.crs, Crs):
            crs = self.crs.to_dict()
        else:
            crs = self.crs

        corrigir_geometria = self.corrigir_geometria

        adicionar: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.adicionar, Unset):
            adicionar = []
            for adicionar_item_data in self.adicionar:
                adicionar_item = adicionar_item_data.to_dict()
                adicionar.append(adicionar_item)

        atualizar: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.atualizar, Unset):
            atualizar = []
            for atualizar_item_data in self.atualizar:
                atualizar_item = atualizar_item_data.to_dict()
                atualizar.append(atualizar_item)

        apagar: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.apagar, Unset):
            apagar = []
            for apagar_item_data in self.apagar:
                apagar_item = apagar_item_data.to_dict()
                apagar.append(apagar_item)

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if modo is not UNSET:
            field_dict["modo"] = modo
        if versao is not UNSET:
            field_dict["versao"] = versao
        if crs is not UNSET:
            field_dict["crs"] = crs
        if corrigir_geometria is not UNSET:
            field_dict["corrigir_geometria"] = corrigir_geometria
        if adicionar is not UNSET:
            field_dict["adicionar"] = adicionar
        if atualizar is not UNSET:
            field_dict["atualizar"] = atualizar
        if apagar is not UNSET:
            field_dict["apagar"] = apagar

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.crs import Crs  # noqa: PLC0415
        from ..models.feicao_adicionar_edicao import FeicaoAdicionarEdicao  # noqa: PLC0415
        from ..models.feicao_apagar import FeicaoApagar  # noqa: PLC0415
        from ..models.feicao_atualizar_edicao import FeicaoAtualizarEdicao  # noqa: PLC0415

        d = dict(src_dict)
        modo = d.pop("modo", UNSET)

        def _parse_versao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        versao = _parse_versao(d.pop("versao", UNSET))

        def _parse_crs(data: object) -> Crs | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                crs_type_0 = Crs.from_dict(data)

                return crs_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(Crs | None | Unset, data)

        crs = _parse_crs(d.pop("crs", UNSET))

        corrigir_geometria = d.pop("corrigir_geometria", UNSET)

        _adicionar = d.pop("adicionar", UNSET)
        adicionar: list[FeicaoAdicionarEdicao] | Unset = UNSET
        if _adicionar is not UNSET:
            adicionar = []
            for adicionar_item_data in _adicionar:
                adicionar_item = FeicaoAdicionarEdicao.from_dict(adicionar_item_data)

                adicionar.append(adicionar_item)

        _atualizar = d.pop("atualizar", UNSET)
        atualizar: list[FeicaoAtualizarEdicao] | Unset = UNSET
        if _atualizar is not UNSET:
            atualizar = []
            for atualizar_item_data in _atualizar:
                atualizar_item = FeicaoAtualizarEdicao.from_dict(atualizar_item_data)

                atualizar.append(atualizar_item)

        _apagar = d.pop("apagar", UNSET)
        apagar: list[FeicaoApagar] | Unset = UNSET
        if _apagar is not UNSET:
            apagar = []
            for apagar_item_data in _apagar:
                apagar_item = FeicaoApagar.from_dict(apagar_item_data)

                apagar.append(apagar_item)

        edicoes_entrada = cls(
            modo=modo,
            versao=versao,
            crs=crs,
            corrigir_geometria=corrigir_geometria,
            adicionar=adicionar,
            atualizar=atualizar,
            apagar=apagar,
        )

        return edicoes_entrada
