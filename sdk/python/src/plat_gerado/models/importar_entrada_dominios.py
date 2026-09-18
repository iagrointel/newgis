from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.importar_entrada_dominios_fields_item import ImportarEntradaDominiosFieldsItem
    from ..models.importar_entrada_dominios_types_item import ImportarEntradaDominiosTypesItem


T = TypeVar("T", bound="ImportarEntradaDominios")


@_attrs_define
class ImportarEntradaDominios:
    """Recorte do JSON de uma camada de FeatureServer/FGDB: `fields` com `domain`, e `types` com
    `domains`/`templates`. É o mesmo objeto que a Esri publica em `/FeatureServer/0?f=json`.

        Attributes:
            fields (list[ImportarEntradaDominiosFieldsItem] | Unset):
            types (list[ImportarEntradaDominiosTypesItem] | Unset):
            prefixo (None | str | Unset):
            item_id (None | str | Unset):
    """

    fields: list[ImportarEntradaDominiosFieldsItem] | Unset = UNSET
    types: list[ImportarEntradaDominiosTypesItem] | Unset = UNSET
    prefixo: None | str | Unset = UNSET
    item_id: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        fields: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.fields, Unset):
            fields = []
            for fields_item_data in self.fields:
                fields_item = fields_item_data.to_dict()
                fields.append(fields_item)

        types: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.types, Unset):
            types = []
            for types_item_data in self.types:
                types_item = types_item_data.to_dict()
                types.append(types_item)

        prefixo: None | str | Unset
        if isinstance(self.prefixo, Unset):
            prefixo = UNSET
        else:
            prefixo = self.prefixo

        item_id: None | str | Unset
        if isinstance(self.item_id, Unset):
            item_id = UNSET
        else:
            item_id = self.item_id

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if fields is not UNSET:
            field_dict["fields"] = fields
        if types is not UNSET:
            field_dict["types"] = types
        if prefixo is not UNSET:
            field_dict["prefixo"] = prefixo
        if item_id is not UNSET:
            field_dict["item_id"] = item_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.importar_entrada_dominios_fields_item import ImportarEntradaDominiosFieldsItem  # noqa: PLC0415
        from ..models.importar_entrada_dominios_types_item import ImportarEntradaDominiosTypesItem  # noqa: PLC0415

        d = dict(src_dict)
        _fields = d.pop("fields", UNSET)
        fields: list[ImportarEntradaDominiosFieldsItem] | Unset = UNSET
        if _fields is not UNSET:
            fields = []
            for fields_item_data in _fields:
                fields_item = ImportarEntradaDominiosFieldsItem.from_dict(fields_item_data)

                fields.append(fields_item)

        _types = d.pop("types", UNSET)
        types: list[ImportarEntradaDominiosTypesItem] | Unset = UNSET
        if _types is not UNSET:
            types = []
            for types_item_data in _types:
                types_item = ImportarEntradaDominiosTypesItem.from_dict(types_item_data)

                types.append(types_item)

        def _parse_prefixo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        prefixo = _parse_prefixo(d.pop("prefixo", UNSET))

        def _parse_item_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        item_id = _parse_item_id(d.pop("item_id", UNSET))

        importar_entrada_dominios = cls(
            fields=fields,
            types=types,
            prefixo=prefixo,
            item_id=item_id,
        )

        return importar_entrada_dominios
