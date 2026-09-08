from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.job_parametros import JobParametros


T = TypeVar("T", bound="Job")


@_attrs_define
class Job:
    """
    Attributes:
        id (UUID):
        tipo (str):
        estado (str):
        progresso (int):
        prioridade (int):
        pesado (bool):
        executor (str):
        criado_em (str):
        tentativa (int):
        max_tentativas (int):
        reinicios (int):
        cancelar_solicitado (bool):
        linhas_log (int):
        parametros (JobParametros):
        memoria_mb (int):
        timeout_s (int):
        mensagem (None | str | Unset):
        usuario_id (int | None | Unset):
        usuario_login (None | str | Unset):
        agendado_para (None | str | Unset):
        iniciado_em (None | str | Unset):
        heartbeat_em (None | str | Unset):
        terminado_em (None | str | Unset):
        duracao_s (float | None | Unset):
        cancelado_por (int | None | Unset):
        cancelado_em (None | str | Unset):
        worker (None | str | Unset):
        chave (None | str | Unset):
        agenda_id (None | Unset | UUID):
        programado_para (None | str | Unset):
        resultado (Any | None | Unset):
        erro (None | str | Unset):
        proveniencia (Any | None | Unset):
    """

    id: UUID
    tipo: str
    estado: str
    progresso: int
    prioridade: int
    pesado: bool
    executor: str
    criado_em: str
    tentativa: int
    max_tentativas: int
    reinicios: int
    cancelar_solicitado: bool
    linhas_log: int
    parametros: JobParametros
    memoria_mb: int
    timeout_s: int
    mensagem: None | str | Unset = UNSET
    usuario_id: int | None | Unset = UNSET
    usuario_login: None | str | Unset = UNSET
    agendado_para: None | str | Unset = UNSET
    iniciado_em: None | str | Unset = UNSET
    heartbeat_em: None | str | Unset = UNSET
    terminado_em: None | str | Unset = UNSET
    duracao_s: float | None | Unset = UNSET
    cancelado_por: int | None | Unset = UNSET
    cancelado_em: None | str | Unset = UNSET
    worker: None | str | Unset = UNSET
    chave: None | str | Unset = UNSET
    agenda_id: None | Unset | UUID = UNSET
    programado_para: None | str | Unset = UNSET
    resultado: Any | None | Unset = UNSET
    erro: None | str | Unset = UNSET
    proveniencia: Any | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        tipo = self.tipo

        estado = self.estado

        progresso = self.progresso

        prioridade = self.prioridade

        pesado = self.pesado

        executor = self.executor

        criado_em = self.criado_em

        tentativa = self.tentativa

        max_tentativas = self.max_tentativas

        reinicios = self.reinicios

        cancelar_solicitado = self.cancelar_solicitado

        linhas_log = self.linhas_log

        parametros = self.parametros.to_dict()

        memoria_mb = self.memoria_mb

        timeout_s = self.timeout_s

        mensagem: None | str | Unset
        if isinstance(self.mensagem, Unset):
            mensagem = UNSET
        else:
            mensagem = self.mensagem

        usuario_id: int | None | Unset
        if isinstance(self.usuario_id, Unset):
            usuario_id = UNSET
        else:
            usuario_id = self.usuario_id

        usuario_login: None | str | Unset
        if isinstance(self.usuario_login, Unset):
            usuario_login = UNSET
        else:
            usuario_login = self.usuario_login

        agendado_para: None | str | Unset
        if isinstance(self.agendado_para, Unset):
            agendado_para = UNSET
        else:
            agendado_para = self.agendado_para

        iniciado_em: None | str | Unset
        if isinstance(self.iniciado_em, Unset):
            iniciado_em = UNSET
        else:
            iniciado_em = self.iniciado_em

        heartbeat_em: None | str | Unset
        if isinstance(self.heartbeat_em, Unset):
            heartbeat_em = UNSET
        else:
            heartbeat_em = self.heartbeat_em

        terminado_em: None | str | Unset
        if isinstance(self.terminado_em, Unset):
            terminado_em = UNSET
        else:
            terminado_em = self.terminado_em

        duracao_s: float | None | Unset
        if isinstance(self.duracao_s, Unset):
            duracao_s = UNSET
        else:
            duracao_s = self.duracao_s

        cancelado_por: int | None | Unset
        if isinstance(self.cancelado_por, Unset):
            cancelado_por = UNSET
        else:
            cancelado_por = self.cancelado_por

        cancelado_em: None | str | Unset
        if isinstance(self.cancelado_em, Unset):
            cancelado_em = UNSET
        else:
            cancelado_em = self.cancelado_em

        worker: None | str | Unset
        if isinstance(self.worker, Unset):
            worker = UNSET
        else:
            worker = self.worker

        chave: None | str | Unset
        if isinstance(self.chave, Unset):
            chave = UNSET
        else:
            chave = self.chave

        agenda_id: None | str | Unset
        if isinstance(self.agenda_id, Unset):
            agenda_id = UNSET
        elif isinstance(self.agenda_id, UUID):
            agenda_id = str(self.agenda_id)
        else:
            agenda_id = self.agenda_id

        programado_para: None | str | Unset
        if isinstance(self.programado_para, Unset):
            programado_para = UNSET
        else:
            programado_para = self.programado_para

        resultado: Any | None | Unset
        if isinstance(self.resultado, Unset):
            resultado = UNSET
        else:
            resultado = self.resultado

        erro: None | str | Unset
        if isinstance(self.erro, Unset):
            erro = UNSET
        else:
            erro = self.erro

        proveniencia: Any | None | Unset
        if isinstance(self.proveniencia, Unset):
            proveniencia = UNSET
        else:
            proveniencia = self.proveniencia

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "tipo": tipo,
                "estado": estado,
                "progresso": progresso,
                "prioridade": prioridade,
                "pesado": pesado,
                "executor": executor,
                "criado_em": criado_em,
                "tentativa": tentativa,
                "max_tentativas": max_tentativas,
                "reinicios": reinicios,
                "cancelar_solicitado": cancelar_solicitado,
                "linhas_log": linhas_log,
                "parametros": parametros,
                "memoria_mb": memoria_mb,
                "timeout_s": timeout_s,
            }
        )
        if mensagem is not UNSET:
            field_dict["mensagem"] = mensagem
        if usuario_id is not UNSET:
            field_dict["usuario_id"] = usuario_id
        if usuario_login is not UNSET:
            field_dict["usuario_login"] = usuario_login
        if agendado_para is not UNSET:
            field_dict["agendado_para"] = agendado_para
        if iniciado_em is not UNSET:
            field_dict["iniciado_em"] = iniciado_em
        if heartbeat_em is not UNSET:
            field_dict["heartbeat_em"] = heartbeat_em
        if terminado_em is not UNSET:
            field_dict["terminado_em"] = terminado_em
        if duracao_s is not UNSET:
            field_dict["duracao_s"] = duracao_s
        if cancelado_por is not UNSET:
            field_dict["cancelado_por"] = cancelado_por
        if cancelado_em is not UNSET:
            field_dict["cancelado_em"] = cancelado_em
        if worker is not UNSET:
            field_dict["worker"] = worker
        if chave is not UNSET:
            field_dict["chave"] = chave
        if agenda_id is not UNSET:
            field_dict["agenda_id"] = agenda_id
        if programado_para is not UNSET:
            field_dict["programado_para"] = programado_para
        if resultado is not UNSET:
            field_dict["resultado"] = resultado
        if erro is not UNSET:
            field_dict["erro"] = erro
        if proveniencia is not UNSET:
            field_dict["proveniencia"] = proveniencia

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.job_parametros import JobParametros  # noqa: PLC0415

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        tipo = d.pop("tipo")

        estado = d.pop("estado")

        progresso = d.pop("progresso")

        prioridade = d.pop("prioridade")

        pesado = d.pop("pesado")

        executor = d.pop("executor")

        criado_em = d.pop("criado_em")

        tentativa = d.pop("tentativa")

        max_tentativas = d.pop("max_tentativas")

        reinicios = d.pop("reinicios")

        cancelar_solicitado = d.pop("cancelar_solicitado")

        linhas_log = d.pop("linhas_log")

        parametros = JobParametros.from_dict(d.pop("parametros"))

        memoria_mb = d.pop("memoria_mb")

        timeout_s = d.pop("timeout_s")

        def _parse_mensagem(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mensagem = _parse_mensagem(d.pop("mensagem", UNSET))

        def _parse_usuario_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        usuario_id = _parse_usuario_id(d.pop("usuario_id", UNSET))

        def _parse_usuario_login(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        usuario_login = _parse_usuario_login(d.pop("usuario_login", UNSET))

        def _parse_agendado_para(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        agendado_para = _parse_agendado_para(d.pop("agendado_para", UNSET))

        def _parse_iniciado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        iniciado_em = _parse_iniciado_em(d.pop("iniciado_em", UNSET))

        def _parse_heartbeat_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        heartbeat_em = _parse_heartbeat_em(d.pop("heartbeat_em", UNSET))

        def _parse_terminado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        terminado_em = _parse_terminado_em(d.pop("terminado_em", UNSET))

        def _parse_duracao_s(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        duracao_s = _parse_duracao_s(d.pop("duracao_s", UNSET))

        def _parse_cancelado_por(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        cancelado_por = _parse_cancelado_por(d.pop("cancelado_por", UNSET))

        def _parse_cancelado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cancelado_em = _parse_cancelado_em(d.pop("cancelado_em", UNSET))

        def _parse_worker(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        worker = _parse_worker(d.pop("worker", UNSET))

        def _parse_chave(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        chave = _parse_chave(d.pop("chave", UNSET))

        def _parse_agenda_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                agenda_id_type_0 = UUID(data)

                return agenda_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        agenda_id = _parse_agenda_id(d.pop("agenda_id", UNSET))

        def _parse_programado_para(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        programado_para = _parse_programado_para(d.pop("programado_para", UNSET))

        def _parse_resultado(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        resultado = _parse_resultado(d.pop("resultado", UNSET))

        def _parse_erro(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        erro = _parse_erro(d.pop("erro", UNSET))

        def _parse_proveniencia(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        proveniencia = _parse_proveniencia(d.pop("proveniencia", UNSET))

        job = cls(
            id=id,
            tipo=tipo,
            estado=estado,
            progresso=progresso,
            prioridade=prioridade,
            pesado=pesado,
            executor=executor,
            criado_em=criado_em,
            tentativa=tentativa,
            max_tentativas=max_tentativas,
            reinicios=reinicios,
            cancelar_solicitado=cancelar_solicitado,
            linhas_log=linhas_log,
            parametros=parametros,
            memoria_mb=memoria_mb,
            timeout_s=timeout_s,
            mensagem=mensagem,
            usuario_id=usuario_id,
            usuario_login=usuario_login,
            agendado_para=agendado_para,
            iniciado_em=iniciado_em,
            heartbeat_em=heartbeat_em,
            terminado_em=terminado_em,
            duracao_s=duracao_s,
            cancelado_por=cancelado_por,
            cancelado_em=cancelado_em,
            worker=worker,
            chave=chave,
            agenda_id=agenda_id,
            programado_para=programado_para,
            resultado=resultado,
            erro=erro,
            proveniencia=proveniencia,
        )

        job.additional_properties = d
        return job

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
