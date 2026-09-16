from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.feicao_adicionar_edicao import FeicaoAdicionarEdicao
    from ..models.feicao_apagar import FeicaoApagar
    from ..models.feicao_atualizar_edicao import FeicaoAtualizarEdicao


T = TypeVar("T", bound="CamadaMudancas")


@_attrs_define
class CamadaMudancas:
    """
    Attributes:
        camada_id (str):
        adicionar (list[FeicaoAdicionarEdicao] | Unset):
        atualizar (list[FeicaoAtualizarEdicao] | Unset):
        apagar (list[FeicaoApagar] | Unset):
    """

    camada_id: str
    adicionar: list[FeicaoAdicionarEdicao] | Unset = UNSET
    atualizar: list[FeicaoAtualizarEdicao] | Unset = UNSET
    apagar: list[FeicaoApagar] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        camada_id = self.camada_id

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

        field_dict.update(
            {
                "camada_id": camada_id,
            }
        )
        if adicionar is not UNSET:
            field_dict["adicionar"] = adicionar
        if atualizar is not UNSET:
            field_dict["atualizar"] = atualizar
        if apagar is not UNSET:
            field_dict["apagar"] = apagar

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.feicao_adicionar_edicao import FeicaoAdicionarEdicao  # noqa: PLC0415
        from ..models.feicao_apagar import FeicaoApagar  # noqa: PLC0415
        from ..models.feicao_atualizar_edicao import FeicaoAtualizarEdicao  # noqa: PLC0415

        d = dict(src_dict)
        camada_id = d.pop("camada_id")

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

        camada_mudancas = cls(
            camada_id=camada_id,
            adicionar=adicionar,
            atualizar=atualizar,
            apagar=apagar,
        )

        return camada_mudancas
