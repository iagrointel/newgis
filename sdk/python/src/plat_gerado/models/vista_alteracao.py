from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.vista_alteracao_estilo_type_0 import VistaAlteracaoEstiloType0
    from ..models.vista_alteracao_popup_type_0 import VistaAlteracaoPopupType0


T = TypeVar("T", bound="VistaAlteracao")


@_attrs_define
class VistaAlteracao:
    """
    Attributes:
        titulo (None | str | Unset):
        filtro (None | str | Unset):
        campos_ocultos (list[str] | Unset):
        somente_leitura (bool | Unset):  Default: True.
        extent (list[float] | None | Unset):
        estilo (None | Unset | VistaAlteracaoEstiloType0):
        popup (None | Unset | VistaAlteracaoPopupType0):
    """

    titulo: None | str | Unset = UNSET
    filtro: None | str | Unset = UNSET
    campos_ocultos: list[str] | Unset = UNSET
    somente_leitura: bool | Unset = True
    extent: list[float] | None | Unset = UNSET
    estilo: None | Unset | VistaAlteracaoEstiloType0 = UNSET
    popup: None | Unset | VistaAlteracaoPopupType0 = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.vista_alteracao_estilo_type_0 import VistaAlteracaoEstiloType0  # noqa: PLC0415
        from ..models.vista_alteracao_popup_type_0 import VistaAlteracaoPopupType0  # noqa: PLC0415

        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        filtro: None | str | Unset
        if isinstance(self.filtro, Unset):
            filtro = UNSET
        else:
            filtro = self.filtro

        campos_ocultos: list[str] | Unset = UNSET
        if not isinstance(self.campos_ocultos, Unset):
            campos_ocultos = self.campos_ocultos

        somente_leitura = self.somente_leitura

        extent: list[float] | None | Unset
        if isinstance(self.extent, Unset):
            extent = UNSET
        elif isinstance(self.extent, list):
            extent = self.extent

        else:
            extent = self.extent

        estilo: dict[str, Any] | None | Unset
        if isinstance(self.estilo, Unset):
            estilo = UNSET
        elif isinstance(self.estilo, VistaAlteracaoEstiloType0):
            estilo = self.estilo.to_dict()
        else:
            estilo = self.estilo

        popup: dict[str, Any] | None | Unset
        if isinstance(self.popup, Unset):
            popup = UNSET
        elif isinstance(self.popup, VistaAlteracaoPopupType0):
            popup = self.popup.to_dict()
        else:
            popup = self.popup

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if titulo is not UNSET:
            field_dict["titulo"] = titulo
        if filtro is not UNSET:
            field_dict["filtro"] = filtro
        if campos_ocultos is not UNSET:
            field_dict["campos_ocultos"] = campos_ocultos
        if somente_leitura is not UNSET:
            field_dict["somente_leitura"] = somente_leitura
        if extent is not UNSET:
            field_dict["extent"] = extent
        if estilo is not UNSET:
            field_dict["estilo"] = estilo
        if popup is not UNSET:
            field_dict["popup"] = popup

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.vista_alteracao_estilo_type_0 import VistaAlteracaoEstiloType0  # noqa: PLC0415
        from ..models.vista_alteracao_popup_type_0 import VistaAlteracaoPopupType0  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        def _parse_filtro(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        filtro = _parse_filtro(d.pop("filtro", UNSET))

        campos_ocultos = cast(list[str], d.pop("campos_ocultos", UNSET))

        somente_leitura = d.pop("somente_leitura", UNSET)

        def _parse_extent(data: object) -> list[float] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                extent_type_0 = cast(list[float], data)

                return extent_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[float] | None | Unset, data)

        extent = _parse_extent(d.pop("extent", UNSET))

        def _parse_estilo(data: object) -> None | Unset | VistaAlteracaoEstiloType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                estilo_type_0 = VistaAlteracaoEstiloType0.from_dict(data)

                return estilo_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | VistaAlteracaoEstiloType0, data)

        estilo = _parse_estilo(d.pop("estilo", UNSET))

        def _parse_popup(data: object) -> None | Unset | VistaAlteracaoPopupType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                popup_type_0 = VistaAlteracaoPopupType0.from_dict(data)

                return popup_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | VistaAlteracaoPopupType0, data)

        popup = _parse_popup(d.pop("popup", UNSET))

        vista_alteracao = cls(
            titulo=titulo,
            filtro=filtro,
            campos_ocultos=campos_ocultos,
            somente_leitura=somente_leitura,
            extent=extent,
            estilo=estilo,
            popup=popup,
        )

        return vista_alteracao
