from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.confirmar_entrada_campos_type_0_item import ConfirmarEntradaCamposType0Item
    from ..models.confirmar_entrada_codificacao_type_0 import ConfirmarEntradaCodificacaoType0
    from ..models.confirmar_entrada_crs_type_0 import ConfirmarEntradaCrsType0
    from ..models.confirmar_entrada_geometria_type_0 import ConfirmarEntradaGeometriaType0
    from ..models.confirmar_entrada_validade_type_0 import ConfirmarEntradaValidadeType0


T = TypeVar("T", bound="ConfirmarEntrada")


@_attrs_define
class ConfirmarEntrada:
    """O corpo é a proposta EDITADA (ADR 0005 seção 5): só os campos que a tela deixa mudar. Cada um é validado
    contra a proposta gravada dentro da rota (nunca um esquema fixo — a proposta é que dá as opções válidas).

        Attributes:
            titulo (None | str | Unset):
            crs (ConfirmarEntradaCrsType0 | None | Unset):
            codificacao (ConfirmarEntradaCodificacaoType0 | None | Unset):
            geometria (ConfirmarEntradaGeometriaType0 | None | Unset):
            campos (list[ConfirmarEntradaCamposType0Item] | None | Unset):
            validade (ConfirmarEntradaValidadeType0 | None | Unset):
    """

    titulo: None | str | Unset = UNSET
    crs: ConfirmarEntradaCrsType0 | None | Unset = UNSET
    codificacao: ConfirmarEntradaCodificacaoType0 | None | Unset = UNSET
    geometria: ConfirmarEntradaGeometriaType0 | None | Unset = UNSET
    campos: list[ConfirmarEntradaCamposType0Item] | None | Unset = UNSET
    validade: ConfirmarEntradaValidadeType0 | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.confirmar_entrada_codificacao_type_0 import ConfirmarEntradaCodificacaoType0  # noqa: PLC0415
        from ..models.confirmar_entrada_crs_type_0 import ConfirmarEntradaCrsType0  # noqa: PLC0415
        from ..models.confirmar_entrada_geometria_type_0 import ConfirmarEntradaGeometriaType0  # noqa: PLC0415
        from ..models.confirmar_entrada_validade_type_0 import ConfirmarEntradaValidadeType0  # noqa: PLC0415

        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        crs: dict[str, Any] | None | Unset
        if isinstance(self.crs, Unset):
            crs = UNSET
        elif isinstance(self.crs, ConfirmarEntradaCrsType0):
            crs = self.crs.to_dict()
        else:
            crs = self.crs

        codificacao: dict[str, Any] | None | Unset
        if isinstance(self.codificacao, Unset):
            codificacao = UNSET
        elif isinstance(self.codificacao, ConfirmarEntradaCodificacaoType0):
            codificacao = self.codificacao.to_dict()
        else:
            codificacao = self.codificacao

        geometria: dict[str, Any] | None | Unset
        if isinstance(self.geometria, Unset):
            geometria = UNSET
        elif isinstance(self.geometria, ConfirmarEntradaGeometriaType0):
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
        elif isinstance(self.validade, ConfirmarEntradaValidadeType0):
            validade = self.validade.to_dict()
        else:
            validade = self.validade

        field_dict: dict[str, Any] = {}

        field_dict.update({})
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

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.confirmar_entrada_campos_type_0_item import ConfirmarEntradaCamposType0Item  # noqa: PLC0415
        from ..models.confirmar_entrada_codificacao_type_0 import ConfirmarEntradaCodificacaoType0  # noqa: PLC0415
        from ..models.confirmar_entrada_crs_type_0 import ConfirmarEntradaCrsType0  # noqa: PLC0415
        from ..models.confirmar_entrada_geometria_type_0 import ConfirmarEntradaGeometriaType0  # noqa: PLC0415
        from ..models.confirmar_entrada_validade_type_0 import ConfirmarEntradaValidadeType0  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        def _parse_crs(data: object) -> ConfirmarEntradaCrsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                crs_type_0 = ConfirmarEntradaCrsType0.from_dict(data)

                return crs_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConfirmarEntradaCrsType0 | None | Unset, data)

        crs = _parse_crs(d.pop("crs", UNSET))

        def _parse_codificacao(data: object) -> ConfirmarEntradaCodificacaoType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                codificacao_type_0 = ConfirmarEntradaCodificacaoType0.from_dict(data)

                return codificacao_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConfirmarEntradaCodificacaoType0 | None | Unset, data)

        codificacao = _parse_codificacao(d.pop("codificacao", UNSET))

        def _parse_geometria(data: object) -> ConfirmarEntradaGeometriaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                geometria_type_0 = ConfirmarEntradaGeometriaType0.from_dict(data)

                return geometria_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConfirmarEntradaGeometriaType0 | None | Unset, data)

        geometria = _parse_geometria(d.pop("geometria", UNSET))

        def _parse_campos(data: object) -> list[ConfirmarEntradaCamposType0Item] | None | Unset:
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
                    campos_type_0_item = ConfirmarEntradaCamposType0Item.from_dict(campos_type_0_item_data)

                    campos_type_0.append(campos_type_0_item)

                return campos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ConfirmarEntradaCamposType0Item] | None | Unset, data)

        campos = _parse_campos(d.pop("campos", UNSET))

        def _parse_validade(data: object) -> ConfirmarEntradaValidadeType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                validade_type_0 = ConfirmarEntradaValidadeType0.from_dict(data)

                return validade_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConfirmarEntradaValidadeType0 | None | Unset, data)

        validade = _parse_validade(d.pop("validade", UNSET))

        confirmar_entrada = cls(
            titulo=titulo,
            crs=crs,
            codificacao=codificacao,
            geometria=geometria,
            campos=campos,
            validade=validade,
        )

        return confirmar_entrada
