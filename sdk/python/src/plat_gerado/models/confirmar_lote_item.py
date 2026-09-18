from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.confirmar_lote_item_cad_type_0 import ConfirmarLoteItemCadType0
    from ..models.confirmar_lote_item_camada_type_0 import ConfirmarLoteItemCamadaType0
    from ..models.confirmar_lote_item_campos_type_0_item import ConfirmarLoteItemCamposType0Item
    from ..models.confirmar_lote_item_codificacao_type_0 import ConfirmarLoteItemCodificacaoType0
    from ..models.confirmar_lote_item_crs_type_0 import ConfirmarLoteItemCrsType0
    from ..models.confirmar_lote_item_geometria_type_0 import ConfirmarLoteItemGeometriaType0
    from ..models.confirmar_lote_item_validade_type_0 import ConfirmarLoteItemValidadeType0


T = TypeVar("T", bound="ConfirmarLoteItem")


@_attrs_define
class ConfirmarLoteItem:
    """
    Attributes:
        importacao_id (str):
        titulo (None | str | Unset):
        crs (ConfirmarLoteItemCrsType0 | None | Unset):
        codificacao (ConfirmarLoteItemCodificacaoType0 | None | Unset):
        geometria (ConfirmarLoteItemGeometriaType0 | None | Unset):
        campos (list[ConfirmarLoteItemCamposType0Item] | None | Unset):
        validade (ConfirmarLoteItemValidadeType0 | None | Unset):
        cad (ConfirmarLoteItemCadType0 | None | Unset):
        camada (ConfirmarLoteItemCamadaType0 | None | Unset):
    """

    importacao_id: str
    titulo: None | str | Unset = UNSET
    crs: ConfirmarLoteItemCrsType0 | None | Unset = UNSET
    codificacao: ConfirmarLoteItemCodificacaoType0 | None | Unset = UNSET
    geometria: ConfirmarLoteItemGeometriaType0 | None | Unset = UNSET
    campos: list[ConfirmarLoteItemCamposType0Item] | None | Unset = UNSET
    validade: ConfirmarLoteItemValidadeType0 | None | Unset = UNSET
    cad: ConfirmarLoteItemCadType0 | None | Unset = UNSET
    camada: ConfirmarLoteItemCamadaType0 | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.confirmar_lote_item_cad_type_0 import ConfirmarLoteItemCadType0  # noqa: PLC0415
        from ..models.confirmar_lote_item_camada_type_0 import ConfirmarLoteItemCamadaType0  # noqa: PLC0415
        from ..models.confirmar_lote_item_codificacao_type_0 import ConfirmarLoteItemCodificacaoType0  # noqa: PLC0415
        from ..models.confirmar_lote_item_crs_type_0 import ConfirmarLoteItemCrsType0  # noqa: PLC0415
        from ..models.confirmar_lote_item_geometria_type_0 import ConfirmarLoteItemGeometriaType0  # noqa: PLC0415
        from ..models.confirmar_lote_item_validade_type_0 import ConfirmarLoteItemValidadeType0  # noqa: PLC0415

        importacao_id = self.importacao_id

        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        crs: dict[str, Any] | None | Unset
        if isinstance(self.crs, Unset):
            crs = UNSET
        elif isinstance(self.crs, ConfirmarLoteItemCrsType0):
            crs = self.crs.to_dict()
        else:
            crs = self.crs

        codificacao: dict[str, Any] | None | Unset
        if isinstance(self.codificacao, Unset):
            codificacao = UNSET
        elif isinstance(self.codificacao, ConfirmarLoteItemCodificacaoType0):
            codificacao = self.codificacao.to_dict()
        else:
            codificacao = self.codificacao

        geometria: dict[str, Any] | None | Unset
        if isinstance(self.geometria, Unset):
            geometria = UNSET
        elif isinstance(self.geometria, ConfirmarLoteItemGeometriaType0):
            geometria = self.geometria.to_dict()
        else:
            geometria = self.geometria

        campos: list[dict[str, Any]] | None | Unset
        if isinstance(self.campos, Unset):
            campos = UNSET
        elif isinstance(self.campos, list):
            campos = []
            for campos_type_0_item_data in self.campos:
                campos_type_0_item = campos_type_0_item_data.to_dict()
                campos.append(campos_type_0_item)

        else:
            campos = self.campos

        validade: dict[str, Any] | None | Unset
        if isinstance(self.validade, Unset):
            validade = UNSET
        elif isinstance(self.validade, ConfirmarLoteItemValidadeType0):
            validade = self.validade.to_dict()
        else:
            validade = self.validade

        cad: dict[str, Any] | None | Unset
        if isinstance(self.cad, Unset):
            cad = UNSET
        elif isinstance(self.cad, ConfirmarLoteItemCadType0):
            cad = self.cad.to_dict()
        else:
            cad = self.cad

        camada: dict[str, Any] | None | Unset
        if isinstance(self.camada, Unset):
            camada = UNSET
        elif isinstance(self.camada, ConfirmarLoteItemCamadaType0):
            camada = self.camada.to_dict()
        else:
            camada = self.camada

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "importacao_id": importacao_id,
            }
        )
        if titulo is not UNSET:
            field_dict["titulo"] = titulo
        if crs is not UNSET:
            field_dict["crs"] = crs
        if codificacao is not UNSET:
            field_dict["codificacao"] = codificacao
        if geometria is not UNSET:
            field_dict["geometria"] = geometria
        if campos is not UNSET:
            field_dict["campos"] = campos
        if validade is not UNSET:
            field_dict["validade"] = validade
        if cad is not UNSET:
            field_dict["cad"] = cad
        if camada is not UNSET:
            field_dict["camada"] = camada

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.confirmar_lote_item_cad_type_0 import ConfirmarLoteItemCadType0  # noqa: PLC0415
        from ..models.confirmar_lote_item_camada_type_0 import ConfirmarLoteItemCamadaType0  # noqa: PLC0415
        from ..models.confirmar_lote_item_campos_type_0_item import ConfirmarLoteItemCamposType0Item  # noqa: PLC0415
        from ..models.confirmar_lote_item_codificacao_type_0 import ConfirmarLoteItemCodificacaoType0  # noqa: PLC0415
        from ..models.confirmar_lote_item_crs_type_0 import ConfirmarLoteItemCrsType0  # noqa: PLC0415
        from ..models.confirmar_lote_item_geometria_type_0 import ConfirmarLoteItemGeometriaType0  # noqa: PLC0415
        from ..models.confirmar_lote_item_validade_type_0 import ConfirmarLoteItemValidadeType0  # noqa: PLC0415

        d = dict(src_dict)
        importacao_id = d.pop("importacao_id")

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        def _parse_crs(data: object) -> ConfirmarLoteItemCrsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                crs_type_0 = ConfirmarLoteItemCrsType0.from_dict(data)

                return crs_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConfirmarLoteItemCrsType0 | None | Unset, data)

        crs = _parse_crs(d.pop("crs", UNSET))

        def _parse_codificacao(data: object) -> ConfirmarLoteItemCodificacaoType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                codificacao_type_0 = ConfirmarLoteItemCodificacaoType0.from_dict(data)

                return codificacao_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConfirmarLoteItemCodificacaoType0 | None | Unset, data)

        codificacao = _parse_codificacao(d.pop("codificacao", UNSET))

        def _parse_geometria(data: object) -> ConfirmarLoteItemGeometriaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                geometria_type_0 = ConfirmarLoteItemGeometriaType0.from_dict(data)

                return geometria_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConfirmarLoteItemGeometriaType0 | None | Unset, data)

        geometria = _parse_geometria(d.pop("geometria", UNSET))

        def _parse_campos(data: object) -> list[ConfirmarLoteItemCamposType0Item] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                campos_type_0 = []
                _campos_type_0 = data
                for campos_type_0_item_data in _campos_type_0:
                    campos_type_0_item = ConfirmarLoteItemCamposType0Item.from_dict(campos_type_0_item_data)

                    campos_type_0.append(campos_type_0_item)

                return campos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ConfirmarLoteItemCamposType0Item] | None | Unset, data)

        campos = _parse_campos(d.pop("campos", UNSET))

        def _parse_validade(data: object) -> ConfirmarLoteItemValidadeType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                validade_type_0 = ConfirmarLoteItemValidadeType0.from_dict(data)

                return validade_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConfirmarLoteItemValidadeType0 | None | Unset, data)

        validade = _parse_validade(d.pop("validade", UNSET))

        def _parse_cad(data: object) -> ConfirmarLoteItemCadType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                cad_type_0 = ConfirmarLoteItemCadType0.from_dict(data)

                return cad_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConfirmarLoteItemCadType0 | None | Unset, data)

        cad = _parse_cad(d.pop("cad", UNSET))

        def _parse_camada(data: object) -> ConfirmarLoteItemCamadaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                camada_type_0 = ConfirmarLoteItemCamadaType0.from_dict(data)

                return camada_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConfirmarLoteItemCamadaType0 | None | Unset, data)

        camada = _parse_camada(d.pop("camada", UNSET))

        confirmar_lote_item = cls(
            importacao_id=importacao_id,
            titulo=titulo,
            crs=crs,
            codificacao=codificacao,
            geometria=geometria,
            campos=campos,
            validade=validade,
            cad=cad,
            camada=camada,
        )

        return confirmar_lote_item
