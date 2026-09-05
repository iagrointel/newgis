"""Agendamento por cron (ADR 0003 seção 7): croniter 6.2.4 + fuso IANA; intervalo mínimo de 15 min; o worker é o
relógio (`tick` a cada 30 s: `agenda_vencidas` FOR UPDATE SKIP LOCKED → `agenda_enfileirar` UMA ocorrência, a mais
recente vencida, e avança); periódicos da plataforma sincronizados no inquilino técnico `plataforma`."""

import datetime
import json
import logging
import zoneinfo

from croniter import CroniterBadCronError, CroniterBadDateError, CroniterNotAlphaError, croniter

from app.jobs.registro import REGISTRO, Tarefa, chave_de

log = logging.getLogger("plat.agenda")
INTERVALO_MINIMO_S = 15 * 60
UTC = datetime.UTC


class ErroAgenda(ValueError):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


def validar_fuso(fuso: str) -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo(fuso)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError, TypeError) as e:
        raise ErroAgenda("fuso_invalido",
                         f"fuso desconhecido: {fuso!r} (use um nome IANA, ex.: America/Sao_Paulo)") from e


def _iterador(expr: str, base: datetime.datetime) -> croniter:
    if not isinstance(expr, str) or len(expr.split()) != 5:
        raise ErroAgenda("cron_invalida", f"expressão cron deve ter 5 campos: {expr!r}")
    try:
        return croniter(expr, base, ret_type=datetime.datetime)
    except (CroniterBadCronError, CroniterBadDateError, CroniterNotAlphaError, ValueError) as e:
        raise ErroAgenda("cron_invalida", f"expressão cron inválida: {expr!r} ({e})") from e


def ocorrencias(expr: str, fuso: str, apos: datetime.datetime, n: int = 3) -> list[datetime.datetime]:
    """As n próximas ocorrências depois de `apos`, em UTC."""
    tz = validar_fuso(fuso)
    it = _iterador(expr, apos.astimezone(tz))
    return [it.get_next(datetime.datetime).astimezone(UTC) for _ in range(n)]


def validar_cron(expr: str, fuso: str, apos: datetime.datetime | None = None) -> list[datetime.datetime]:
    """Valida expressão e fuso e devolve as 3 próximas ocorrências; recusa intervalo < 15 min entre elas."""
    apos = apos or datetime.datetime.now(UTC)
    proximas = ocorrencias(expr, fuso, apos, 3)
    for a, b in zip(proximas, proximas[1:], strict=False):
        if (b - a).total_seconds() < INTERVALO_MINIMO_S:
            raise ErroAgenda("intervalo_minimo", f"intervalo entre ocorrências de {expr!r} é menor que 15 min")
    return proximas


def proxima(expr: str, fuso: str, apos: datetime.datetime) -> datetime.datetime:
    return ocorrencias(expr, fuso, apos, 1)[0]


def ultima_vencida(expr: str, fuso: str, agora: datetime.datetime) -> datetime.datetime:
    """A ocorrência mais recente <= agora (o que se enfileira depois de uma parada longa)."""
    tz = validar_fuso(fuso)
    it = _iterador(expr, (agora + datetime.timedelta(seconds=1)).astimezone(tz))
    return it.get_prev(datetime.datetime).astimezone(UTC)


def agora_do_worker(settings) -> datetime.datetime:
    """now() ou, só em PLAT_AMBIENTE=dev, o instante de PLAT_RELOGIO_TESTE."""
    if settings.PLAT_RELOGIO_TESTE:
        if settings.producao:
            log.warning("PLAT_RELOGIO_TESTE ignorado em producao")
        else:
            return datetime.datetime.fromisoformat(settings.PLAT_RELOGIO_TESTE).astimezone(UTC)
    return datetime.datetime.now(UTC)


def _limites(t: Tarefa, parametros: dict) -> tuple:
    return (t.pesado, t.memoria_mb, t.timeout_s, t.executor, t.tentativas, chave_de(t, parametros))


def tick(con, agora: datetime.datetime, registro: dict[str, Tarefa] | None = None) -> list[str]:
    """Um passo do relógio sobre uma conexão plat_app autocommit. Transação explícita para o SKIP LOCKED valer entre
    dois workers; a UNIQUE (agenda_id, programado_para) é a segunda trava. Devolve os ids dos jobs enfileirados."""
    registro = REGISTRO if registro is None else registro
    criados: list[str] = []
    cur = con.cursor()
    cur.execute("BEGIN")
    try:
        cur.execute("SELECT * FROM plat.agenda_vencidas(%s)", (agora,))
        vencidas = cur.fetchall()
        for a in vencidas:
            a = dict(a) if not isinstance(a, dict) else a
            t = registro.get(a["tipo"])
            try:
                prox = proxima(a["cron"], a["fuso"], agora)
                programado = ultima_vencida(a["cron"], a["fuso"], agora)
            except ErroAgenda as e:
                log.warning("agenda %s com cron/fuso inválidos: %s; pausada", a["id"], e)
                cur.execute("UPDATE plat.agenda SET ativa = false, proxima_em = NULL WHERE id = %s", (a["id"],))
                continue
            if t is None:
                log.warning("agenda %s: tipo %s não registrado; ocorrência pulada", a["id"], a["tipo"])
                cur.execute("SELECT plat.agenda_enfileirar(%s, %s, %s, false, false, 0, 0, 'local', 0, NULL)",
                            (a["id"], programado, prox))
                continue
            cur.execute("SELECT plat.jobs_no_dia(%s) AS n, plat.cota_jobs_dia(%s) AS cota",
                        (a["tenant_id"], a["tenant_id"]))
            r = cur.fetchone()
            r = dict(r) if not isinstance(r, dict) else r
            if r["n"] >= r["cota"]:
                log.warning("agenda %s: cota_jobs_dia (%s) esgotada no inquilino %s; ocorrência pulada",
                            a["id"], r["cota"], a["tenant_id"])
                cur.execute("SELECT plat.agenda_enfileirar(%s, %s, %s, false, false, 0, 0, 'local', 0, NULL)",
                            (a["id"], programado, prox))
                continue
            parametros = a["parametros"] if isinstance(a["parametros"], dict) else json.loads(a["parametros"] or "{}")
            cur.execute("SELECT plat.agenda_enfileirar(%s, %s, %s, true, %s, %s, %s, %s, %s, %s) AS id",
                        (a["id"], programado, prox, *_limites(t, parametros)))
            jid = cur.fetchone()
            jid = (jid["id"] if isinstance(jid, dict) else jid[0]) if jid else None
            if jid:
                criados.append(str(jid))
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise
    finally:
        cur.close()
    return criados


def sincronizar_periodicos(con, agora: datetime.datetime) -> int:
    """Upsert das linhas de app/jobs/periodicos.py no inquilino técnico `plataforma`."""
    from app.jobs.periodicos import PERIODICOS

    cur = con.cursor()
    n = 0
    try:
        for nome, cron, tipo, parametros in PERIODICOS:
            prox = proxima(cron, "America/Sao_Paulo", agora)
            cur.execute("SELECT plat.agenda_periodica_sincronizar(%s, %s, %s, %s, %s, %s)",
                        (nome, tipo, json.dumps(parametros), cron, "America/Sao_Paulo", prox))
            n += 1
    finally:
        cur.close()
    return n
