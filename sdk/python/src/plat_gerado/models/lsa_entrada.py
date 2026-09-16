from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.lsa_entrada_analysistype import LsaEntradaAnalysistype
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.lsa_entrada_parcel_features_item import LsaEntradaParcelFeaturesItem


T = TypeVar("T", bound="LsaEntrada")


@_attrs_define
class LsaEntrada:
    """Analyze/apply na forma da doc (analysisType, convergenceTolerance, parcelFeatures). O
    campo `semLinhas` é extra declarado da casa (§13): medida excluída DA RODADA por ser
    grosseira — o ajuste não apaga medida, só deixa de usá-la.

        Attributes:
            parcel_features (list[LsaEntradaParcelFeaturesItem]):
            gdb_version (None | str | Unset):
            session_id (None | str | Unset):
            analysis_type (LsaEntradaAnalysistype | Unset):  Default: LsaEntradaAnalysistype.WEIGHTED_LEAST_SQUARES.
            convergence_tolerance (float | Unset):  Default: 0.05.
            sem_linhas (list[str] | None | Unset):
    """

    parcel_features: list[LsaEntradaParcelFeaturesItem]
    gdb_version: None | str | Unset = UNSET
    session_id: None | str | Unset = UNSET
    analysis_type: LsaEntradaAnalysistype | Unset = LsaEntradaAnalysistype.WEIGHTED_LEAST_SQUARES
    convergence_tolerance: float | Unset = 0.05
    sem_linhas: list[str] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        parcel_features = []
        for parcel_features_item_data in self.parcel_features:
            parcel_features_item = parcel_features_item_data.to_dict()
            parcel_features.append(parcel_features_item)

        gdb_version: None | str | Unset
        if isinstance(self.gdb_version, Unset):
            gdb_version = UNSET
        else:
            gdb_version = self.gdb_version

        session_id: None | str | Unset
        if isinstance(self.session_id, Unset):
            session_id = UNSET
        else:
            session_id = self.session_id

        analysis_type: str | Unset = UNSET
        if not isinstance(self.analysis_type, Unset):
            analysis_type = self.analysis_type.value

        convergence_tolerance = self.convergence_tolerance

        sem_linhas: list[str] | None | Unset
        if isinstance(self.sem_linhas, Unset):
            sem_linhas = UNSET
        elif isinstance(self.sem_linhas, list):
            sem_linhas = self.sem_linhas

        else:
            sem_linhas = self.sem_linhas

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "parcelFeatures": parcel_features,
            }
        )
        if gdb_version is not UNSET:
            field_dict["gdbVersion"] = gdb_version
        if session_id is not UNSET:
            field_dict["sessionId"] = session_id
        if analysis_type is not UNSET:
            field_dict["analysisType"] = analysis_type
        if convergence_tolerance is not UNSET:
            field_dict["convergenceTolerance"] = convergence_tolerance
        if sem_linhas is not UNSET:
            field_dict["semLinhas"] = sem_linhas

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.lsa_entrada_parcel_features_item import LsaEntradaParcelFeaturesItem  # noqa: PLC0415

        d = dict(src_dict)
        parcel_features = []
        _parcel_features = d.pop("parcelFeatures")
        for parcel_features_item_data in _parcel_features:
            parcel_features_item = LsaEntradaParcelFeaturesItem.from_dict(parcel_features_item_data)

            parcel_features.append(parcel_features_item)

        def _parse_gdb_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        gdb_version = _parse_gdb_version(d.pop("gdbVersion", UNSET))

        def _parse_session_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        session_id = _parse_session_id(d.pop("sessionId", UNSET))

        _analysis_type = d.pop("analysisType", UNSET)
        analysis_type: LsaEntradaAnalysistype | Unset
        if isinstance(_analysis_type, Unset):
            analysis_type = UNSET
        else:
            analysis_type = LsaEntradaAnalysistype(_analysis_type)

        convergence_tolerance = d.pop("convergenceTolerance", UNSET)

        def _parse_sem_linhas(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                sem_linhas_type_0 = cast(list[str], data)

                return sem_linhas_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        sem_linhas = _parse_sem_linhas(d.pop("semLinhas", UNSET))

        lsa_entrada = cls(
            parcel_features=parcel_features,
            gdb_version=gdb_version,
            session_id=session_id,
            analysis_type=analysis_type,
            convergence_tolerance=convergence_tolerance,
            sem_linhas=sem_linhas,
        )

        lsa_entrada.additional_properties = d
        return lsa_entrada

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
