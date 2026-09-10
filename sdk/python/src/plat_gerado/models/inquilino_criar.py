from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.inquilino_criar_config_type_0 import InquilinoCriarConfigType0


T = TypeVar("T", bound="InquilinoCriar")


@_attrs_define
class InquilinoCriar:
    """
    Attributes:
        slug (str):
        nome (str):
        admin_login (str):
        admin_nome (str):
        config (InquilinoCriarConfigType0 | None | Unset):
    """

    slug: str
    nome: str
    admin_login: str
    admin_nome: str
    config: InquilinoCriarConfigType0 | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.inquilino_criar_config_type_0 import InquilinoCriarConfigType0  # noqa: PLC0415

        slug = self.slug

        nome = self.nome

        admin_login = self.admin_login

        admin_nome = self.admin_nome

        config: dict[str, Any] | None | Unset
        if isinstance(self.config, Unset):
            config = UNSET
        elif isinstance(self.config, InquilinoCriarConfigType0):
            config = self.config.to_dict()
        else:
            config = self.config

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "slug": slug,
                "nome": nome,
                "admin_login": admin_login,
                "admin_nome": admin_nome,
            }
        )
        if config is not UNSET:
            field_dict["config"] = config

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.inquilino_criar_config_type_0 import InquilinoCriarConfigType0  # noqa: PLC0415

        d = dict(src_dict)
        slug = d.pop("slug")

        nome = d.pop("nome")

        admin_login = d.pop("admin_login")

        admin_nome = d.pop("admin_nome")

        def _parse_config(data: object) -> InquilinoCriarConfigType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_type_0 = InquilinoCriarConfigType0.from_dict(data)

                return config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(InquilinoCriarConfigType0 | None | Unset, data)

        config = _parse_config(d.pop("config", UNSET))

        inquilino_criar = cls(
            slug=slug,
            nome=nome,
            admin_login=admin_login,
            admin_nome=admin_nome,
            config=config,
        )

        return inquilino_criar
