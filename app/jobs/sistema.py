"""Enfileiramento de job pelo PRÓPRIO backend, sem uma `Sessao` de usuário (item L0-07-d-smtp-convites):
convite e redefinição de senha disparam e-mail antes de existir sessão (a conta ainda não existe, ou o pedido
é anônimo), e o admin que cria um convite já gastou o privilégio dele na PRÓPRIA rota — o e-mail em si é
disparo interno. Só tipos `somente_sistema=True` entram por aqui (o registro recusa os outros: nenhum outro
efeito colateral externo deveria nascer sem o dono do job saber). Reusa a MESMA cota diária e o MESMO teto de
pendentes de `app/jobs/servico.py::criar` — um flood de convites/redefinições não fura a cota do inquilino."""

import psycopg2.extras

from app import db as banco
from app.jobs.contexto import ErroServico
from app.jobs.registro import REGISTRO, Tarefa, chave_de, validar_parametros
from app.jobs.servico import PENDENTES_MAX


def _tipo_de_sistema(tipo: str) -> Tarefa:
    t = REGISTRO.get(tipo)
    if t is None or not t.somente_sistema:
        raise ErroServico(500, "tipo_invalido_para_sistema", f"{tipo!r} não é um tipo somente_sistema registrado")
    return t


def enfileirar(tenant_id: int, tipo: str, parametros: dict, usuario_id: int | None = None,
               prioridade: int = 5) -> str:
    """Insere o job e devolve o id (str). `usuario_id` é só atribuição (quem o job representa: o admin que
    convidou, ou o dono da conta que pediu a redefinição) — nunca controla privilégio aqui."""
    t = _tipo_de_sistema(tipo)
    params = validar_parametros(t, parametros)
    ctx = banco.Contexto(tenant_id, usuario_id or 0, "sistema")
    with banco.db(ctx) as cur:
        cur.execute(
            "SELECT plat.cota_jobs_dia(%s) AS cota, "
            "(SELECT count(*) FROM plat.job WHERE tenant_id = %s AND criado_em >= "
            "date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC') AS hoje, "
            "(SELECT count(*) FROM plat.job WHERE tenant_id = %s AND estado = 'pendente') AS pendentes",
            (tenant_id, tenant_id, tenant_id),
        )
        r = cur.fetchone()
        if r["hoje"] >= r["cota"]:
            # 429 como em app/jobs/servico.py::criar (item L0-07-c-cotas-uso), com uso atual e limite
            raise ErroServico(429, "cota_jobs_dia",
                              f"cota diária de jobs esgotada: uso atual {r['hoje']} de {r['cota']} jobs hoje",
                              {"cota": r["cota"], "hoje": r["hoje"]})
        if r["pendentes"] >= PENDENTES_MAX:
            raise ErroServico(429, "fila_cheia",
                              f"o inquilino já tem {r['pendentes']} jobs pendentes (máximo {PENDENTES_MAX})")
        cur.execute(
            "INSERT INTO plat.job(tenant_id, usuario_id, tipo, parametros, prioridade, chave, pesado, memoria_mb, "
            "timeout_s, executor, max_tentativas) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "RETURNING id",
            (tenant_id, usuario_id, t.nome, psycopg2.extras.Json(params), prioridade, chave_de(t, params),
             t.pesado, t.memoria_mb, t.timeout_s, t.executor, t.tentativas),
        )
        novo = cur.fetchone()["id"]
    return str(novo)
