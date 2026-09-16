"""Enfileiramento de job pelo PRÓPRIO backend, sem uma `Sessao` de usuário (item L0-07-d-smtp-convites):
convite e redefinição de senha disparam e-mail antes de existir sessão (a conta ainda não existe, ou o pedido
é anônimo), e o admin que cria um convite já gastou o privilégio dele na PRÓPRIA rota — o e-mail em si é
disparo interno. Só tipos `somente_sistema=True` entram por aqui (o registro recusa os outros: nenhum outro
efeito colateral externo deveria nascer sem o dono do job saber). Reusa a MESMA cota diária e o MESMO teto de
pendentes de `app/jobs/servico.py::criar` — um flood de convites/redefinições não fura a cota do inquilino."""

import datetime
import logging

import psycopg2.extras

from app import db as banco
from app.jobs.contexto import ErroServico
from app.jobs.registro import REGISTRO, Tarefa, chave_de, validar_parametros
from app.jobs.servico import PENDENTES_MAX

log = logging.getLogger("plat.jobs.sistema")


def _tipo_de_sistema(tipo: str) -> Tarefa:
    t = REGISTRO.get(tipo)
    if t is None or not t.somente_sistema:
        raise ErroServico(500, "tipo_invalido_para_sistema", f"{tipo!r} não é um tipo somente_sistema registrado")
    return t


def _checar_cota(cur, tenant_id: int) -> None:
    """Mesma cota diária e mesmo teto de pendentes da rota pública (`servico.criar`): o disparo interno
    não fura o que o inquilino tem direito."""
    cur.execute(
        "SELECT plat.cota_jobs_dia(%s) AS cota, "
        "(SELECT count(*) FROM plat.job WHERE tenant_id = %s AND criado_em >= "
        "date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC') AS hoje, "
        "(SELECT count(*) FROM plat.job WHERE tenant_id = %s AND estado = 'pendente') AS pendentes",
        (tenant_id, tenant_id, tenant_id),
    )
    r = cur.fetchone()
    if r["hoje"] >= r["cota"]:
        raise ErroServico(413, "cota_jobs_dia", f"cota diária de jobs do inquilino esgotada ({r['cota']})",
                          {"cota": r["cota"], "hoje": r["hoje"]})
    if r["pendentes"] >= PENDENTES_MAX:
        raise ErroServico(429, "fila_cheia",
                          f"o inquilino já tem {r['pendentes']} jobs pendentes (máximo {PENDENTES_MAX})")


def _inserir(cur, tenant_id: int, t, params: dict, usuario_id: int | None, prioridade: int,
             agendado_para: datetime.datetime | None) -> str:
    cur.execute(
        "INSERT INTO plat.job(tenant_id, usuario_id, tipo, parametros, prioridade, chave, pesado, memoria_mb, "
        "timeout_s, executor, max_tentativas, agendado_para) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "RETURNING id",
        (tenant_id, usuario_id, t.nome, psycopg2.extras.Json(params), prioridade, chave_de(t, params),
         t.pesado, t.memoria_mb, t.timeout_s, t.executor, t.tentativas,
         agendado_para or datetime.datetime.now(datetime.UTC)),
    )
    return str(cur.fetchone()["id"])


def enfileirar(tenant_id: int, tipo: str, parametros: dict, usuario_id: int | None = None,
               prioridade: int = 5, agendado_para: datetime.datetime | None = None) -> str:
    """Insere o job e devolve o id (str). `usuario_id` é só atribuição (quem o job representa: o admin que
    convidou, ou o dono da conta que pediu a redefinição) — nunca controla privilégio aqui.
    `agendado_para` agenda a execução para o futuro (o coletor do worker só pega a partir de então); o
    apagamento dos objetos de imagem usa isto para respeitar a retenção da lixeira."""
    t = _tipo_de_sistema(tipo)
    params = validar_parametros(t, parametros)
    ctx = banco.Contexto(tenant_id, usuario_id or 0, "sistema")
    with banco.db(ctx) as cur:
        _checar_cota(cur, tenant_id)
        novo = _inserir(cur, tenant_id, t, params, usuario_id, prioridade, agendado_para)
    return novo


def registrar_concluido(tenant_id: int, tipo: str, parametros: dict, resultado: dict) -> str:
    """Registra um job JÁ CONCLUÍDO — é o que a CLI usa quando ela MESMA executou o trabalho (coleta de
    lixo) e quer o relatório visível em Tarefas. O gatilho `plat.job_transicao` não aceita job nascendo
    'concluido', então o caminho é o mesmo da máquina de estados do worker: nasce pendente, vira 'rodando'
    e termina por `plat.job_terminar`. INSERT e transição são NA MESMA transação (com o GUC
    `plat.via_worker` ligado só nela): um worker de verdade nunca vê a linha pendente no meio do caminho,
    então não há corrida em que ele tome o job e o relatório da CLI fique preso em 'rodando'."""
    t = _tipo_de_sistema(tipo)
    params = validar_parametros(t, parametros)
    worker = f"cli-{t.nome}"
    ctx = banco.Contexto(tenant_id, 0, "sistema")
    with banco.db(ctx) as cur:
        _checar_cota(cur, tenant_id)
        job_id = _inserir(cur, tenant_id, t, params, None, 5, None)
        # a transição pendente->rodando->concluido é feita no banco por `plat.job_registrar_concluido`
        # (SECURITY DEFINER, migração 20260908T1932_raster_gc_apoio.sql): nasce pendente por causa do
        # gatilho `plat.job_transicao`, e a conclusão reusa `plat.job_terminar`, com os mesmos disparos
        # de notificação do worker
        cur.execute(
            "SELECT plat.job_registrar_concluido(%s::uuid, %s, %s, %s) AS ok",
            (job_id, worker, psycopg2.extras.Json(resultado), psycopg2.extras.Json({"origem": "cli"})),
        )
        if not cur.fetchone()["ok"]:
            # defensivo: com INSERT + transição na mesma transação o worker não toma o job; se um dia
            # voltar a acontecer, o aviso nomeia o id em vez de deixar 'rodando' sem ninguém cuidando
            log.warning("registrar_concluido: job %s não foi concluído pela função do banco", job_id)
    return job_id
