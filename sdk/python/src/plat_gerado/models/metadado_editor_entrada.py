from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.metadado_editor_entrada_item_type_0 import MetadadoEditorEntradaItemType0
    from ..models.metadado_editor_entrada_metadado import MetadadoEditorEntradaMetadado


T = TypeVar("T", bound="MetadadoEditorEntrada")


@_attrs_define
class MetadadoEditorEntrada:
    """Corpo de `POST /api/itens/{id}/metadado/validar` e `PUT /api/itens/{id}/metadado` (item
    L0-09-metadado-catalogo, cláusula 3): `item` é o subconjunto sincronizado (título/resumo/tags/créditos/
    termos de uso — mesmo contrato de `ItemEditar`, validado por `editar_item`), `metadado` é a parte própria
    do Perfil MGB 2.0 (`app/catalogo/metadado_mgb.py`, `ESQUEMA_MGB`). Ambos ficam soltos (`dict`) aqui: quem
    valida estrutura é `metadado_mgb.validar_estrutura`/`editar_item`, nunca este modelo — repetir o esquema
    aqui seria um segundo lugar de verdade.

        Attributes:
            item (MetadadoEditorEntradaItemType0 | None | Unset):
            metadado (MetadadoEditorEntradaMetadado | Unset):
    """

    item: MetadadoEditorEntradaItemType0 | None | Unset = UNSET
    metadado: MetadadoEditorEntradaMetadado | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.metadado_editor_entrada_item_type_0 import MetadadoEditorEntradaItemType0  # noqa: PLC0415

        item: dict[str, Any] | None | Unset
        if isinstance(self.item, Unset):
            item = UNSET
        elif isinstance(self.item, MetadadoEditorEntradaItemType0):
            item = self.item.to_dict()
        else:
            item = self.item

        metadado: dict[str, Any] | Unset = UNSET
        if not isinstance(self.metadado, Unset):
            metadado = self.metadado.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if item is not UNSET:
            field_dict["item"] = item
        if metadado is not UNSET:
            field_dict["metadado"] = metadado

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.metadado_editor_entrada_item_type_0 import MetadadoEditorEntradaItemType0  # noqa: PLC0415
        from ..models.metadado_editor_entrada_metadado import MetadadoEditorEntradaMetadado  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_item(data: object) -> MetadadoEditorEntradaItemType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                item_type_0 = MetadadoEditorEntradaItemType0.from_dict(data)

                return item_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MetadadoEditorEntradaItemType0 | None | Unset, data)

        item = _parse_item(d.pop("item", UNSET))

        _metadado = d.pop("metadado", UNSET)
        metadado: MetadadoEditorEntradaMetadado | Unset
        if isinstance(_metadado, Unset):
            metadado = UNSET
        else:
            metadado = MetadadoEditorEntradaMetadado.from_dict(_metadado)

        metadado_editor_entrada = cls(
            item=item,
            metadado=metadado,
        )

        return metadado_editor_entrada
