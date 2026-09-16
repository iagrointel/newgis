from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.importar_saida_criados_item import ImportarSaidaCriadosItem
    from ..models.importar_saida_ignorados_item import ImportarSaidaIgnoradosItem
    from ..models.importar_saida_ligados_item import ImportarSaidaLigadosItem
    from ..models.importar_saida_reaproveitados_item import ImportarSaidaReaproveitadosItem
    from ..models.importar_saida_subtipos_type_0 import ImportarSaidaSubtiposType0


T = TypeVar("T", bound="ImportarSaida")


@_attrs_define
class ImportarSaida:
    """
    Attributes:
        criados (list[ImportarSaidaCriadosItem]):
        reaproveitados (list[ImportarSaidaReaproveitadosItem]):
        ligados (list[ImportarSaidaLigadosItem]):
        ignorados (list[ImportarSaidaIgnoradosItem]):
        subtipos (ImportarSaidaSubtiposType0 | None | Unset):
    """

    criados: list[ImportarSaidaCriadosItem]
    reaproveitados: list[ImportarSaidaReaproveitadosItem]
    ligados: list[ImportarSaidaLigadosItem]
    ignorados: list[ImportarSaidaIgnoradosItem]
    subtipos: ImportarSaidaSubtiposType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.importar_saida_subtipos_type_0 import ImportarSaidaSubtiposType0  # noqa: PLC0415

        criados = []
        for criados_item_data in self.criados:
            criados_item = criados_item_data.to_dict()
            criados.append(criados_item)

        reaproveitados = []
        for reaproveitados_item_data in self.reaproveitados:
            reaproveitados_item = reaproveitados_item_data.to_dict()
            reaproveitados.append(reaproveitados_item)

        ligados = []
        for ligados_item_data in self.ligados:
            ligados_item = ligados_item_data.to_dict()
            ligados.append(ligados_item)

        ignorados = []
        for ignorados_item_data in self.ignorados:
            ignorados_item = ignorados_item_data.to_dict()
            ignorados.append(ignorados_item)

        subtipos: dict[str, Any] | None | Unset
        if isinstance(self.subtipos, Unset):
            subtipos = UNSET
        elif isinstance(self.subtipos, ImportarSaidaSubtiposType0):
            subtipos = self.subtipos.to_dict()
        else:
            subtipos = self.subtipos

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "criados": criados,
                "reaproveitados": reaproveitados,
                "ligados": ligados,
                "ignorados": ignorados,
            }
        )
        if subtipos is not UNSET:
            field_dict["subtipos"] = subtipos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.importar_saida_criados_item import ImportarSaidaCriadosItem  # noqa: PLC0415
        from ..models.importar_saida_ignorados_item import ImportarSaidaIgnoradosItem  # noqa: PLC0415
        from ..models.importar_saida_ligados_item import ImportarSaidaLigadosItem  # noqa: PLC0415
        from ..models.importar_saida_reaproveitados_item import ImportarSaidaReaproveitadosItem  # noqa: PLC0415
        from ..models.importar_saida_subtipos_type_0 import ImportarSaidaSubtiposType0  # noqa: PLC0415

        d = dict(src_dict)
        criados = []
        _criados = d.pop("criados")
        for criados_item_data in _criados:
            criados_item = ImportarSaidaCriadosItem.from_dict(criados_item_data)

            criados.append(criados_item)

        reaproveitados = []
        _reaproveitados = d.pop("reaproveitados")
        for reaproveitados_item_data in _reaproveitados:
            reaproveitados_item = ImportarSaidaReaproveitadosItem.from_dict(reaproveitados_item_data)

            reaproveitados.append(reaproveitados_item)

        ligados = []
        _ligados = d.pop("ligados")
        for ligados_item_data in _ligados:
            ligados_item = ImportarSaidaLigadosItem.from_dict(ligados_item_data)

            ligados.append(ligados_item)

        ignorados = []
        _ignorados = d.pop("ignorados")
        for ignorados_item_data in _ignorados:
            ignorados_item = ImportarSaidaIgnoradosItem.from_dict(ignorados_item_data)

            ignorados.append(ignorados_item)

        def _parse_subtipos(data: object) -> ImportarSaidaSubtiposType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                subtipos_type_0 = ImportarSaidaSubtiposType0.from_dict(data)

                return subtipos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ImportarSaidaSubtiposType0 | None | Unset, data)

        subtipos = _parse_subtipos(d.pop("subtipos", UNSET))

        importar_saida = cls(
            criados=criados,
            reaproveitados=reaproveitados,
            ligados=ligados,
            ignorados=ignorados,
            subtipos=subtipos,
        )

        importar_saida.additional_properties = d
        return importar_saida

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
