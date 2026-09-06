"""Regras de negócio da fila, chamadas pelas rotas (ADR 0003 seção 9): criar (validação do tipo e dos parâmetros,
perfil mínimo, cotas), listar (admin vê o inquilino, os demais só os próprios), obter, cancelar, repetir, log,
resumo, agendas. Tudo sob RLS pela sessão; nenhuma função do worker é chamada aqui."""

import datetime
import decimal
import json
import uuid

import psycopg2
import psycopg2.errors
import psycopg2.extras
from pydantic import ValidationError

from app import db as banco
from app.jobs import agenda as mod_agenda
from app.jobs.contexto import ErroServico, Sessao
from app.jobs.registro import REGISTRO, Tarefa, chave_de, descrever, ordem_perfil, validar_parametros
from app.jobs.tipos import REGISTRO as _registro_carregado  # noqa: F401 — garante os tipos registrados

UTC = datetime.UTC
ESTADOS = ("pendente", "rodando", "concluido", "falhou", "cancelado")
FINAIS = ("concluido", "falhou", "cancelado")
ORDENAR = {"criado_em", "iniciado_em", "terminado_em", "estado", "tipo", "progresso", "prioridade"}
LIMITE_MAX = 200
LOG_LIMITE_MAX = 2000
PENDENTES_MAX = 200
NIVEIS = ("DEBUG", "INFO", "AVISO", "ERRO")

SQL_JOB = """
SELECT j.id, j.tipo, j.estado, j.progresso, j.mensagem, j.prioridade, j.pesado, j.executor, j.usuario_id,
       u.login AS usuario_login, j.criado_em, j.agendado_para, j.iniciado_em, j.heartbeat_em, j.terminado_em,
       CASE WHEN j.iniciado_em IS NULL THEN NULL
            ELSE extract(epoch FROM (coalesce(j.terminado_em, now()) - j.iniciado_em)) END AS duracao_s,
       j.tentativa, j.max_tentativas, j.reinicios, j.cancelar_solicitado, j.cancelado_por, j.cancelado_em,
       j.worker, j.chave, j.agenda_id, j.programado_para, j.resultado, j.erro, j.linhas_log, j.parametros,
       j.proveniencia, j.memoria_mb, j.timeout_s
FROM plat.job j LEFT JOIN plat.usuario u ON u.id = j.usuario_id
"""
SQL_AGENDA = """
SELECT a.id, a.nome, a.tipo, a.parametros, a.cron, a.fuso, a.ativa, a.proxima_em, a.ultima_em, a.ultimo_job_id,
       a.ultimo_estado, a.falhas_seguidas, a.expira_em, a.criado_em, a.usuario_id, u.login AS usuario_login
FROM plat.agenda a LEFT JOIN plat.usuario u ON u.id = a.usuario_id
"""


# ---------------------------------------------------------------- utilidades
def _valor(v):
    if isinstance(v, datetime.datetime):
        return v.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, decimal.Decimal):
        return round(float(v), 1)
    return v


def serializar(linha: dict) -> dict:
    return {k: _valor(v) for k, v in dict(linha).items()}


def tipo_registrado(nome: str) -> Tarefa:
    t = REGISTRO.get(nome)
    if t is None:
        raise ErroServico(422, "tipo_desconhecido", f"tipo de job não registrado: {nome!r}",
                          {"tipos": sorted(REGISTRO)})
    return t


def _parametros(t: Tarefa, dados) -> dict:
    if dados is None:
        dados = {}
    if not isinstance(dados, dict):
        raise ErroServico(422, "parametros_invalidos", "parametros deve ser um objeto JSON")
    try:
        return validar_parametros(t, dados)
    except ValidationError as e:
        detalhe = [{"campo": ".".join(str(x) for x in err["loc"]), "mensagem": err["msg"]} for err in e.errors()]
        raise ErroServico(422, "parametros_invalidos", f"parâmetros inválidos para {t.nome}", detalhe) from e


def _exigir_perfil(sessao: Sessao, minimo: str, acao: str) -> None:
    if sessao.superadmin:
        return
    if ordem_perfil(sessao.perfil) < ordem_perfil(minimo):
        raise ErroServico(403, "perfil_insuficiente",
                          f"{acao} exige perfil {minimo} ou superior (o seu é {sessao.perfil})")


def _data(valor: str | None, campo: str) -> datetime.datetime | None:
    if valor in (None, ""):
        return None
    try:
        dt = datetime.datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError as e:
        raise ErroServico(422, "data_invalida", f"{campo} deve ser ISO 8601 (ex.: 2026-09-05T12:00:00Z)") from e
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _filtro_dono(sessao: Sessao) -> tuple[str, list]:
    if sessao.admin:
        return "", []
    return " AND j.usuario_id = %s", [sessao.usuario_id]


# ---------------------------------------------------------------- jobs
def criar(sessao: Sessao, tipo: str, parametros, prioridade: int = 5, agendado_para: str | None = None,
          repetido_de: str | None = None, agenda_id=None, programado_para=None) -> dict:
    t = tipo_registrado(tipo)
    if t.somente_sistema:
        # item L0-07-d-smtp-convites: tipo que só o backend enfileira (app/jobs/sistema.py) — nunca por esta rota,
        # nem para admin (evita usar o SMTP do inquilino como canhão de e-mail arbitrário via /api/jobs).
        raise ErroServico(403, "tipo_somente_sistema", f"{t.nome} só é criado internamente, nunca por esta rota")
    _exigir_perfil(sessao, t.perfil_minimo, f"criar job {t.nome}")
    params = _parametros(t, parametros)
    if not isinstance(prioridade, int) or not 1 <= prioridade <= 9:
        raise ErroServico(422, "prioridade_invalida", "prioridade deve ser inteiro de 1 (primeiro) a 9")
    quando = _data(agendado_para, "agendado_para")
    prov = {"repetido_de": str(repetido_de)} if repetido_de else None
    with banco.db(sessao.ctx) as cur:
        cur.execute("SELECT plat.cota_jobs_dia(%s) AS cota, "
                    "(SELECT count(*) FROM plat.job WHERE criado_em >= "
                    "date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC') AS hoje, "
                    "(SELECT count(*) FROM plat.job WHERE estado = 'pendente') AS pendentes", (sessao.tenant_id,))
        r = cur.fetchone()
        if r["hoje"] >= r["cota"]:
            # 429 (não 413): cota de TAXA diária, não de tamanho — portão do item L0-07-c-cotas-uso; a
            # mensagem diz o uso atual e o limite, como toda recusa de cota da plataforma
            raise ErroServico(429, "cota_jobs_dia",
                              f"cota diária de jobs esgotada: uso atual {r['hoje']} de {r['cota']} jobs hoje",
                              {"cota": r["cota"], "hoje": r["hoje"]})
        if r["pendentes"] >= PENDENTES_MAX:
            raise ErroServico(429, "fila_cheia",
                              f"o inquilino já tem {r['pendentes']} jobs pendentes (máximo {PENDENTES_MAX})")
        cur.execute(
            "INSERT INTO plat.job(tenant_id, usuario_id, tipo, parametros, prioridade, chave, pesado, memoria_mb, "
            "timeout_s, executor, max_tentativas, agendado_para, proveniencia, agenda_id, programado_para) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s, now()), %s, %s, %s) RETURNING id",
            (sessao.tenant_id, sessao.usuario_id, t.nome, psycopg2.extras.Json(params), prioridade, chave_de(t, params),
             t.pesado, t.memoria_mb, t.timeout_s, t.executor, t.tentativas, quando,
             psycopg2.extras.Json(prov) if prov else None, agenda_id, programado_para),
        )
        novo = cur.fetchone()["id"]
    return obter(sessao, novo)


def obter(sessao: Sessao, job_id) -> dict:
    dono, params = _filtro_dono(sessao)
    with banco.db(sessao.ctx) as cur:
        cur.execute(SQL_JOB + " WHERE j.id = %s" + dono, [str(job_id), *params])
        linha = cur.fetchone()
    if linha is None:
        raise ErroServico(404, "job_inexistente", "job não encontrado")
    return serializar(linha)


def listar(sessao: Sessao, estado=None, tipo=None, usuario_id=None, de=None, ate=None, agenda_id=None,
           limite: int = 50, deslocamento: int = 0, ordenar: str = "criado_em:desc") -> dict:
    cond, params = [], []
    dono, p = _filtro_dono(sessao)
    if dono:
        cond.append(dono[5:])
        params += p
    if estado:
        if estado not in ESTADOS:
            raise ErroServico(422, "estado_invalido", f"estado deve ser um de {ESTADOS}")
        cond.append("j.estado = %s")
        params.append(estado)
    if tipo:
        cond.append("j.tipo = %s")
        params.append(tipo)
    if usuario_id is not None:
        cond.append("j.usuario_id = %s")
        params.append(int(usuario_id))
    if agenda_id:
        cond.append("j.agenda_id = %s")
        params.append(str(agenda_id))
    d, a = _data(de, "de"), _data(ate, "ate")
    if d:
        cond.append("j.criado_em >= %s")
        params.append(d)
    if a:
        cond.append("j.criado_em <= %s")
        params.append(a)
    campo, _, sentido = (ordenar or "criado_em:desc").partition(":")
    sentido = sentido or "desc"
    if campo not in ORDENAR or sentido not in ("asc", "desc"):
        raise ErroServico(422, "ordenar_invalido",
                          f"ordenar deve ser <campo>:<asc|desc> com campo em {sorted(ORDENAR)}")
    limite = max(1, min(int(limite), LIMITE_MAX))
    deslocamento = max(0, int(deslocamento))
    onde = (" WHERE " + " AND ".join(cond)) if cond else ""
    with banco.db(sessao.ctx) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.job j{onde}", params)
        total = cur.fetchone()["n"]
        cur.execute(f"{SQL_JOB}{onde} ORDER BY j.{campo} {sentido} NULLS LAST, j.criado_em DESC LIMIT %s OFFSET %s",
                    [*params, limite, deslocamento])
        itens = [serializar(r) for r in cur.fetchall()]
    return {"itens": itens, "total": total, "limite": limite, "deslocamento": deslocamento}


def resumo(sessao: Sessao) -> dict:
    dono, params = _filtro_dono(sessao)
    with banco.db(sessao.ctx) as cur:
        cur.execute(
            "SELECT count(*) FILTER (WHERE estado = 'pendente') AS pendente, "
            "count(*) FILTER (WHERE estado = 'rodando') AS rodando, "
            "count(*) FILTER (WHERE estado = 'concluido' AND terminado_em > now() - interval '24 hours') "
            "AS concluido_24h, "
            "count(*) FILTER (WHERE estado = 'falhou' AND terminado_em > now() - interval '24 hours') AS falhou_24h, "
            "count(*) FILTER (WHERE estado = 'cancelado' AND terminado_em > now() - interval '24 hours') "
            "AS cancelado_24h "
            "FROM plat.job j WHERE true" + dono, params)
        return serializar(cur.fetchone())


def tipos() -> list[dict]:
    return [descrever(t) for _, t in sorted(REGISTRO.items())]


def cancelar(sessao: Sessao, job_id) -> dict:
    obter(sessao, job_id)  # 404 e filtro de dono
    with banco.db(sessao.ctx) as cur:  # plat_app não tem UPDATE em plat.job (006): cancela pela função
        cur.execute("SELECT plat.job_cancelar(%s, %s) AS r", (str(job_id), sessao.usuario_id))
        r = cur.fetchone()["r"]
    if r not in ("cancelado", "solicitado"):
        raise ErroServico(409, "estado_final", f"job já está em estado final ({r}); repetir cria job novo")
    return obter(sessao, job_id)


def repetir(sessao: Sessao, job_id, parametros_extra=None) -> dict:
    original = obter(sessao, job_id)
    params = dict(original.get("parametros") or {})
    if parametros_extra:
        if not isinstance(parametros_extra, dict):
            raise ErroServico(422, "parametros_invalidos", "parametros deve ser um objeto JSON")
        params.update(parametros_extra)
    return criar(sessao, original["tipo"], params, int(original["prioridade"]), repetido_de=original["id"])


def log(sessao: Sessao, job_id, apos: int = 0, nivel: str | None = None, limite: int = 500) -> dict:
    obter(sessao, job_id)
    if nivel and nivel.upper() not in NIVEIS:
        raise ErroServico(422, "nivel_invalido", f"nivel deve ser um de {NIVEIS}")
    limite = max(1, min(int(limite), LOG_LIMITE_MAX))
    cond, params = ["job_id = %s", "id > %s"], [str(job_id), int(apos or 0)]
    if nivel:
        cond.append("nivel = %s")
        params.append(nivel.upper())
    onde = " WHERE " + " AND ".join(cond)
    with banco.db(sessao.ctx) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.job_log{onde}", params)
        total = cur.fetchone()["n"]
        cur.execute(f"SELECT id, em, nivel, mensagem FROM plat.job_log{onde} ORDER BY id LIMIT %s", [*params, limite])
        linhas = [serializar(r) for r in cur.fetchall()]
    return {"linhas": linhas, "total": total}


# ---------------------------------------------------------------- agendas
def _agenda_filtro_dono(sessao: Sessao) -> tuple[str, list]:
    if sessao.admin:
        return "", []
    return " AND a.usuario_id = %s", [sessao.usuario_id]


def _agenda_serializar(linha: dict) -> dict:
    d = serializar(linha)
    if isinstance(d.get("parametros"), str):
        d["parametros"] = json.loads(d["parametros"])
    return d


def agenda_obter(sessao: Sessao, agenda_id) -> dict:
    dono, params = _agenda_filtro_dono(sessao)
    with banco.db(sessao.ctx) as cur:
        cur.execute(SQL_AGENDA + " WHERE a.id = %s" + dono, [str(agenda_id), *params])
        linha = cur.fetchone()
    if linha is None:
        raise ErroServico(404, "agenda_inexistente", "agenda não encontrada")
    return _agenda_serializar(linha)


def agendas_listar(sessao: Sessao, ativa=None, tipo=None, limite: int = 50, deslocamento: int = 0) -> dict:
    cond, params = [], []
    dono, p = _agenda_filtro_dono(sessao)
    if dono:
        cond.append(dono[5:])
        params += p
    if ativa is not None:
        cond.append("a.ativa = %s")
        params.append(bool(ativa))
    if tipo:
        cond.append("a.tipo = %s")
        params.append(tipo)
    onde = (" WHERE " + " AND ".join(cond)) if cond else ""
    limite = max(1, min(int(limite), LIMITE_MAX))
    with banco.db(sessao.ctx) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.agenda a{onde}", params)
        total = cur.fetchone()["n"]
        cur.execute(f"{SQL_AGENDA}{onde} ORDER BY a.nome LIMIT %s OFFSET %s",
                    [*params, limite, max(0, int(deslocamento))])
        itens = [_agenda_serializar(r) for r in cur.fetchall()]
    return {"itens": itens, "total": total}


def _validar_agenda(sessao: Sessao, dados: dict, parcial: dict | None = None) -> dict:
    base = dict(parcial or {})
    base.update({k: v for k, v in dados.items() if k in ("nome", "tipo", "parametros", "cron", "fuso", "expira_em")})
    nome = str(base.get("nome") or "").strip()
    if not 1 <= len(nome) <= 120:
        raise ErroServico(422, "nome_invalido", "nome da agenda deve ter de 1 a 120 caracteres")
    t = tipo_registrado(str(base.get("tipo") or ""))
    _exigir_perfil(sessao, t.perfil_minimo, f"agendar {t.nome}")
    params = _parametros(t, base.get("parametros"))
    cron = str(base.get("cron") or "").strip()
    fuso = str(base.get("fuso") or "America/Sao_Paulo").strip()
    try:
        proximas = mod_agenda.validar_cron(cron, fuso)
    except mod_agenda.ErroAgenda as e:
        raise ErroServico(422, e.codigo, e.mensagem) from e
    expira = _data(base.get("expira_em"), "expira_em")
    return {"nome": nome, "tipo": t.nome, "parametros": params, "cron": cron, "fuso": fuso, "expira_em": expira,
            "proxima_em": proximas[0]}


def agenda_criar(sessao: Sessao, dados: dict) -> dict:
    _exigir_perfil(sessao, "editor", "criar agenda")
    v = _validar_agenda(sessao, dados)
    with banco.db(sessao.ctx) as cur:
        cur.execute("SELECT plat.cota_agendas(%s) AS cota, (SELECT count(*) FROM plat.agenda) AS n",
                    (sessao.tenant_id,))
        r = cur.fetchone()
        if r["n"] >= r["cota"]:
            raise ErroServico(413, "cota_agendas", f"cota de agendas do inquilino esgotada ({r['cota']})",
                              {"cota": r["cota"]})
        try:
            cur.execute("INSERT INTO plat.agenda(tenant_id, usuario_id, nome, tipo, parametros, cron, fuso, expira_em, "
                        "proxima_em) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                        (sessao.tenant_id, sessao.usuario_id, v["nome"], v["tipo"],
                         psycopg2.extras.Json(v["parametros"]), v["cron"], v["fuso"], v["expira_em"], v["proxima_em"]))
        except psycopg2.errors.UniqueViolation as e:
            raise ErroServico(409, "nome_repetido", f"já existe agenda com o nome {v['nome']!r} neste inquilino") from e
        novo = cur.fetchone()["id"]
    return agenda_obter(sessao, novo)


def agenda_atualizar(sessao: Sessao, agenda_id, dados: dict) -> dict:
    atual = agenda_obter(sessao, agenda_id)
    v = _validar_agenda(sessao, dados, atual)
    recalcular = v["cron"] != atual["cron"] or v["fuso"] != atual["fuso"]
    with banco.db(sessao.ctx) as cur:
        try:
            cur.execute("UPDATE plat.agenda SET nome = %s, tipo = %s, parametros = %s, cron = %s, fuso = %s, "
                        "expira_em = %s, proxima_em = CASE WHEN %s AND ativa THEN %s ELSE proxima_em END WHERE id = %s",
                        (v["nome"], v["tipo"], psycopg2.extras.Json(v["parametros"]), v["cron"], v["fuso"],
                         v["expira_em"], recalcular, v["proxima_em"], str(agenda_id)))
        except psycopg2.errors.UniqueViolation as e:
            raise ErroServico(409, "nome_repetido", f"já existe agenda com o nome {v['nome']!r} neste inquilino") from e
    return agenda_obter(sessao, agenda_id)


def agenda_apagar(sessao: Sessao, agenda_id) -> None:
    agenda_obter(sessao, agenda_id)
    with banco.db(sessao.ctx) as cur:
        cur.execute("DELETE FROM plat.agenda WHERE id = %s", (str(agenda_id),))


def agenda_pausar(sessao: Sessao, agenda_id) -> dict:
    a = agenda_obter(sessao, agenda_id)
    if not a["ativa"]:
        raise ErroServico(409, "ja_pausada", "agenda já está pausada")
    with banco.db(sessao.ctx) as cur:
        cur.execute("UPDATE plat.agenda SET ativa = false, proxima_em = NULL WHERE id = %s", (str(agenda_id),))
    return agenda_obter(sessao, agenda_id)


def agenda_retomar(sessao: Sessao, agenda_id) -> dict:
    a = agenda_obter(sessao, agenda_id)
    if a["ativa"]:
        raise ErroServico(409, "ja_ativa", "agenda já está ativa")
    try:
        prox = mod_agenda.proxima(a["cron"], a["fuso"], datetime.datetime.now(UTC))
    except mod_agenda.ErroAgenda as e:
        raise ErroServico(422, e.codigo, e.mensagem) from e
    with banco.db(sessao.ctx) as cur:
        cur.execute("UPDATE plat.agenda SET ativa = true, falhas_seguidas = 0, proxima_em = %s WHERE id = %s",
                    (prox, str(agenda_id)))
    return agenda_obter(sessao, agenda_id)


def agenda_rodar_agora(sessao: Sessao, agenda_id) -> dict:
    a = agenda_obter(sessao, agenda_id)
    return criar(sessao, a["tipo"], a["parametros"], agenda_id=str(agenda_id),
                 programado_para=datetime.datetime.now(UTC))
