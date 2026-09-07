"""Logging JSON por linha em stdout (journal do systemd), sem dependência externa (ADR 0001 seção 9).
Leitura: `journalctl -u plat-api -o cat | jq`.

Item L7-06-c: nível ajustável em tempo de execução, por componente (nome do logger) ou por prefixo de
rota, sem reinício — equivalente ao `logLevel` do Server (OFF..DEBUG). O estado mora num arquivo JSON
compartilhado (`var/log_nivel.json`, fora do git) porque a API roda em vários processos gunicorn que não
compartilham memória; cada processo relê o arquivo só quando o `mtime` muda (um `stat()` por linha de
log, desprezível). Override tem prazo (`--por`); expirado é ignorado sem faxina — ADR 0018."""

import contextvars
import datetime
import json
import logging
import os
import secrets
import sys
import tempfile
from pathlib import Path

from app.settings import NIVEIS

CAMPOS_REQ = ("req_id", "metodo", "rota", "status", "tempo_ms", "ip", "tenant_id", "usuario_id", "token_id",
              "job_id", "tipo", "pid_filho")  # os três últimos: worker da fila (ADR 0003 seção 4.1)

ROOT = Path(__file__).resolve().parents[1]
NUMERO_NIVEL = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR}


def _arquivo_override() -> Path:
    """`PLAT_LOG_NIVEL_ARQUIVO` só existe para o teste de unidade isolar o arquivo (evita que dois testes
    em paralelo pisem no mesmo `var/log_nivel.json`); em produção e no worker sempre o caminho padrão."""
    return Path(os.environ.get("PLAT_LOG_NIVEL_ARQUIVO") or (ROOT / "var" / "log_nivel.json"))


def _agora() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _ler_overrides(caminho: Path) -> list[dict]:
    try:
        bruto = json.loads(caminho.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []
    if not isinstance(bruto, list):
        return []
    return [o for o in bruto if isinstance(o, dict) and "componente" in o and "nivel" in o]


def _escrever_overrides(caminho: Path, overrides: list[dict]) -> None:
    """Escrita atômica (tempfile + os.replace): um processo lendo no meio do caminho nunca vê JSON
    truncado — o mesmo padrão de `marcar_item.py` para `estado.json`."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=caminho.parent, prefix=".log_nivel_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(overrides, f, ensure_ascii=False)
        os.replace(tmp, caminho)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _expirado(override: dict, agora: datetime.datetime) -> bool:
    expira = override.get("expira_em")
    if not expira:
        return False
    try:
        return agora >= datetime.datetime.fromisoformat(expira)
    except ValueError:
        return True  # data ilegível: trata como expirado, nunca trava o sistema num nível preso


def _casa(componente_override: str, nome_logger: str, rota: str | None) -> bool:
    if componente_override == "*":
        return True
    if componente_override.startswith("rota:"):
        return rota is not None and rota.startswith(componente_override[len("rota:"):])
    return nome_logger == componente_override or nome_logger.startswith(componente_override + ".")


def definir_override(componente: str, nivel: str, minutos: float | None = None) -> dict:
    """`componente` é o nome do logger (`app.consulta`), um prefixo de rota (`rota:/api/tiles`) ou `*`
    (global). Grava por cima de um override existente do MESMO componente. `minutos=None` = sem prazo
    (só sai por `remover_override` ou por outro `definir_override` do mesmo componente)."""
    nivel = nivel.upper()
    if nivel not in NIVEIS:
        raise ValueError(f"nivel inválido: {nivel!r}; admitidos {NIVEIS}")
    caminho = _arquivo_override()
    overrides = [o for o in _ler_overrides(caminho) if o["componente"] != componente]
    registro = {
        "componente": componente,
        "nivel": nivel,
        "definido_em": _agora().isoformat(timespec="seconds"),
        "expira_em": (_agora() + datetime.timedelta(minutes=minutos)).isoformat(timespec="seconds") if minutos else None,
    }
    overrides.append(registro)
    _escrever_overrides(caminho, overrides)
    return registro


def remover_override(componente: str) -> bool:
    caminho = _arquivo_override()
    overrides = _ler_overrides(caminho)
    restante = [o for o in overrides if o["componente"] != componente]
    if len(restante) == len(overrides):
        return False
    _escrever_overrides(caminho, restante)
    return True


def listar_overrides(incluir_expirados: bool = False) -> list[dict]:
    agora = _agora()
    overrides = _ler_overrides(_arquivo_override())
    if incluir_expirados:
        return overrides
    return [o for o in overrides if not _expirado(o, agora)]


class FiltroNivelDinamico(logging.Filter):
    """Instalado no ÚNICO handler da raiz: relê `var/log_nivel.json` quando o `mtime` muda e decide, por
    registro, se o nível efetivo (override do componente/rota mais específico que bate, senão o padrão
    de partida) deixa passar. A raiz fica sempre em DEBUG (`configurar` abaixo) para que o filtro, não o
    nível do logger, seja quem decide — é o único jeito de mudar o volume sem reiniciar o processo."""

    def __init__(self, nivel_padrao: str):
        super().__init__()
        self.nivel_padrao = nivel_padrao
        self._arquivo = _arquivo_override()
        self._mtime: float | None = None
        self._overrides: list[dict] = []

    def _recarregar(self) -> None:
        try:
            m = self._arquivo.stat().st_mtime
        except FileNotFoundError:
            m = None
        if m != self._mtime:
            self._mtime = m
            self._overrides = _ler_overrides(self._arquivo) if m is not None else []

    def nivel_efetivo(self, nome_logger: str, rota: str | None = None) -> int:
        self._recarregar()
        agora = _agora()
        melhor = None
        for o in self._overrides:
            if _expirado(o, agora):
                continue
            if not _casa(o["componente"], nome_logger, rota):
                continue
            # mais específico vence: comprimento do texto do componente (rota:/api/x > rota:/api > "*")
            if melhor is None or len(o["componente"]) > len(melhor["componente"]):
                melhor = o
        return NUMERO_NIVEL[melhor["nivel"]] if melhor else NUMERO_NIVEL[self.nivel_padrao]

    def filter(self, registro: logging.LogRecord) -> bool:
        rota = getattr(registro, "rota", None)
        return registro.levelno >= self.nivel_efetivo(registro.name, rota)


class FormatadorJSON(logging.Formatter):
    def format(self, registro: logging.LogRecord) -> str:
        linha = {
            "ts": datetime.datetime.fromtimestamp(registro.created, datetime.UTC).isoformat(timespec="milliseconds"),
            "nivel": registro.levelname,
            "msg": registro.getMessage(),
            "logger": registro.name,
        }
        for campo in CAMPOS_REQ:
            valor = getattr(registro, campo, None)
            if valor is not None:
                linha[campo] = valor
        if registro.exc_info:
            linha["exc"] = self.formatException(registro.exc_info)
        return json.dumps(linha, ensure_ascii=False, default=str)


def configurar(nivel: str = "INFO") -> None:
    """Instala um único handler JSON na raiz; chamadas repetidas recriam o filtro de nível dinâmico com o
    padrão novo. A raiz fica em DEBUG: quem decide o corte é o `FiltroNivelDinamico`, não `Logger.level`
    (senão um `setLevel(WARNING)` descartaria o registro ANTES do filtro rodar, e o override para DEBUG
    nunca conseguiria reabrir a torneira sem reiniciar o processo)."""
    raiz = logging.getLogger()
    handler = next((h for h in raiz.handlers if getattr(h, "_plat_json", False)), None)
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(FormatadorJSON())
        handler._plat_json = True  # type: ignore[attr-defined]
        raiz.addHandler(handler)
    for f in list(handler.filters):
        if isinstance(f, FiltroNivelDinamico):
            handler.removeFilter(f)
    handler.addFilter(FiltroNivelDinamico(nivel))
    raiz.setLevel(logging.DEBUG)
    for ruidoso in ("uvicorn.access",):
        logging.getLogger(ruidoso).setLevel("WARNING")


def req_id() -> str:
    """Identificador de requisição: 16 caracteres hexadecimais."""
    return secrets.token_hex(8)


# ---------------------------------------------------------------------------------------------------
# Correlação com o Postgres (ADR do item): a requisição corrente guarda o próprio req_id num contextvar;
# app.db._preparar lê daqui e faz `SET application_name` na conexão ANTES de qualquer consulta do pedido,
# sem que cada rota precise passar o req_id explicitamente. Starlette copia o contexto para o threadpool
# das rotas síncronas (é o mecanismo oficial para isto), então o valor chega até lá.
_REQ_ID_ATUAL: contextvars.ContextVar[str | None] = contextvars.ContextVar("plat_req_id_atual", default=None)


def definir_req_id_atual(rid: str | None) -> contextvars.Token:
    return _REQ_ID_ATUAL.set(rid)


def limpar_req_id_atual(token: contextvars.Token) -> None:
    _REQ_ID_ATUAL.reset(token)


def req_id_atual() -> str | None:
    return _REQ_ID_ATUAL.get()


def nome_aplicacao_pg(rid: str | None) -> str:
    """`application_name` da conexão: até 12 hex do req_id (Postgres corta em 64 bytes; 12 já correlaciona
    sem poluir `pg_stat_activity`/`log_line_prefix %a`) prefixados para não colidir com outro produto da
    casa que também usa o `iagro_sat` compartilhado."""
    return f"plat:{rid[:12]}" if rid else "plat"
