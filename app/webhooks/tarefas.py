"""Job `webhooks.entregar` (item L7-08-a).

O job é `somente_sistema`: a entrega nasce do GATILHO de despacho (migração 20260909T0345) dentro da
transação do fato de domínio, e o reenvio manual (`rotas.py`) re-enfileira a MESMA entrega — nenhum
`POST /api/jobs` cria este tipo (o mesmo racional de `correio.enviar`, L0-07-d). A retentativa é a do
worker: a tarefa levanta exceção comum e o pai devolve o job com espera `2**tentativa` s (006) até
`limites.WEBHOOK_TENTATIVAS_MAX`; na última tentativa a entrega vai a `falhou` e conta UMA falha para a
desativação automática (`falhas_consecutivas` conta ENTREGAS falhadas, não tentativas). Estourado o
limite (config do inquilino `webhooks.desativar_apos`, teto em limites), o webhook desativa, o fato
`webhooks/desativar` entra em `plat.evento` e os admins com e-mail levam um aviso pela MESMA fila
(`correio.enviar`); sem SMTP configurado o aviso falha como melhor-esforço e fica no log do job.

O corpo sai EXATAMENTE como foi assinado (`content` = bytes assinados); `webhook-id` é o id da ENTREGA,
então reenvio repete o mesmo id e o receptor deduplica (idempotência do portão)."""

import json

from pydantic import BaseModel

from app import limites
from app.conexao import seguranca
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.webhooks import assinatura
from app.webhooks.periodicos import webhooks_expurgar  # noqa: F401 — importação registra o periódico


class EntregarParametros(BaseModel):
    entrega_id: str


def _desativar_apos(config: dict | None) -> int:
    bruto = (config or {}).get("webhooks") or {}
    try:
        valor = int(bruto.get("desativar_apos", limites.WEBHOOK_FALHAS_DESATIVAR_PADRAO))
    except (TypeError, ValueError):
        return limites.WEBHOOK_FALHAS_DESATIVAR_PADRAO
    return max(limites.WEBHOOK_FALHAS_DESATIVAR_MIN, min(limites.WEBHOOK_FALHAS_DESATIVAR_MAX, valor))


def _avisar_admins(ctx, webhook_nome: str, limite: int) -> int:
    """Aviso de desativação para os admins com e-mail do inquilino, pela MESMA fila (correio.enviar).
    Falha de e-mail nunca derruba a entrega em curso: só vira linha de log do job."""
    with ctx.db() as cur:
        cur.execute("SELECT email FROM plat.usuario WHERE ativo AND perfil = 'admin' AND email IS NOT NULL")
        destinatarios = [u["email"] for u in cur.fetchall()]
    enviados = 0
    for email in destinatarios:
        try:
            from app.jobs import sistema  # import tardio: `app.jobs.tipos` importa este módulo
            # enquanto `app.jobs.servico` ainda está a meio da inicialização, e `app.jobs.sistema`
            # lê `PENDENTES_MAX` de lá — importar no topo fecha o ciclo e a aplicação não sobe
            # (medido no resgate de 17/09/2026, contra o master do dia).
            sistema.enfileirar(
                ctx.tenant_id, "correio.enviar",
                {
                    "destinatario": email,
                    "assunto": f"Webhook desativado por falhas: {webhook_nome}",
                    "texto": (
                        f"O webhook '{webhook_nome}' foi desativado automaticamente após {limite} "
                        f"entregas seguidas sem sucesso. Corrija o receptor e reative o webhook; o "
                        f"segredo de assinatura não mudou."
                    ),
                    "categoria": "webhook_desativado",
                },
                prioridade=4,
            )
            enviados += 1
        except Exception as e:  # noqa: BLE001 — aviso é melhor-esforço, registrado no log do job
            ctx.log("AVISO", f"aviso de desativação não enfileirado para {email}: {e}")
    return enviados


def _desativar_se_preciso(ctx, webhook_id: str, webhook_nome: str, entrega_id: str) -> None:
    """Conta a falha da ENTREGA (não da tentativa) e desativa ao estourar o limite do inquilino.
    A conta acontece uma única vez por entrega porque só é chamada quando a entrega passa a 'falhou'."""
    with ctx.db() as cur:
        cur.execute(
            "UPDATE plat.webhook SET falhas_consecutivas = falhas_consecutivas + 1 "
            "WHERE id = %s AND ativo RETURNING falhas_consecutivas AS n",
            (webhook_id,),
        )
        r = cur.fetchone()
    if r is None:
        return  # webhook já desativado por outra entrega em paralelo
    limite = _desativar_apos(linha_config(ctx))
    if r["n"] < limite:
        return
    with ctx.db() as cur:
        # uma entrega ainda pendente pode entregar e zerar a conta: só desativa se não houver outra em curso
        cur.execute(
            "SELECT count(*) AS n FROM plat.webhook_entrega "
            "WHERE webhook_id = %s AND estado = 'pendente' AND id <> %s::uuid",
            (webhook_id, entrega_id),
        )
        if cur.fetchone()["n"] > 0:
            return
        cur.execute(
            "UPDATE plat.webhook SET ativo = false, desativada_em = now(), desativada_motivo = %s "
            "WHERE id = %s AND ativo",
            (f"{limite} entregas seguidas sem sucesso", webhook_id),
        )
        cur.execute(
            "SELECT plat.evento_registrar('webhooks/desativar', 'webhook', %s, %s::jsonb, NULL, NULL)",
            (webhook_id, json.dumps({"motivo": "falhas_consecutivas", "limite": limite,
                                     "entrega_id": entrega_id})),
        )
    avisos = _avisar_admins(ctx, webhook_nome, limite)
    ctx.log("AVISO", f"webhook {webhook_nome} desativado ({limite} entregas seguidas sem sucesso); "
                     f"{avisos} aviso(s) enfileirado(s)")


def linha_config(ctx) -> dict | None:
    """Config do inquilino do job (o despacho roda dentro dele; `ctx.db()` já fixa o inquilino)."""
    with ctx.db() as cur:
        cur.execute("SELECT config FROM plat.tenant WHERE id = plat.tenant_atual()")
        t = cur.fetchone()
    return (t or {}).get("config")


@tarefa(
    nome="webhooks.entregar",
    descricao="Entrega um evento de plat.evento no URL do webhook, assinado (Standard Webhooks); "
              "somente o gatilho de despacho e o reenvio manual criam este job",
    parametros=EntregarParametros,
    pesado=False,
    memoria_mb=256,
    timeout_s=60,
    tentativas=limites.WEBHOOK_TENTATIVAS_MAX,
    perfil_minimo="visualizador",
    somente_sistema=True,
)
def webhooks_entregar(ctx, entrega_id: str) -> dict:
    with ctx.db() as cur:
        cur.execute(
            "SELECT e.id, e.estado, e.tentativas, e.payload, e.webhook_id, w.url, w.nome, w.ativo, "
            "w.segredo_cifrado FROM plat.webhook_entrega e JOIN plat.webhook w ON w.id = e.webhook_id "
            "WHERE e.id = %s::uuid",
            (entrega_id,),
        )
        linha = cur.fetchone()
    if linha is None:
        raise FalhaDefinitiva("entrega inexistente ou inquilino invisível")
    if linha["estado"] == "entregue":
        return {"pulado": "já entregue"}  # corrida de reenvio: idempotente
    if linha["estado"] == "desativada":
        return {"pulado": "webhook desativado"}
    if not linha["ativo"]:
        with ctx.db() as cur:
            cur.execute("UPDATE plat.webhook_entrega SET estado = 'desativada' WHERE id = %s::uuid "
                        "AND estado = 'pendente'", (entrega_id,))
        return {"pulado": "webhook desativado"}

    try:
        segredo = assinatura.decifrar_segredo(linha["segredo_cifrado"])
    except Exception as e:  # noqa: BLE001 — segredo ilegível não se conserta com retentativa
        raise FalhaDefinitiva(f"segredo ilegível ({type(e).__name__}); rotacione o webhook") from e

    corpo = json.dumps(linha["payload"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    erro = None
    status = None
    try:
        validada = assinatura.validar_url(linha["url"])  # de novo no despacho: DNS e políticas mudam
        cabecalhos = assinatura.cabecalhos(segredo, entrega_id, corpo)
        with seguranca.cliente_pinado(validada, timeout_conectar=limites.WEBHOOK_TIMEOUT_CONECTAR_S,
                                      timeout_ler=limites.WEBHOOK_TIMEOUT_LER_S) as cliente:
            resposta = cliente.post(validada.url, content=corpo, headers=cabecalhos)
    except seguranca.ErroURLInsegura as e:
        erro, status = f"url_insegura:{e.motivo}", None
    except Exception as e:  # noqa: BLE001 — rede/HTTP: tudo é tentativa repetível
        erro, status = f"{type(e).__name__}: {e}"[:limites.WEBHOOK_ENTREGA_ERRO_MAX], None
    else:
        status = resposta.status_code
        if 200 <= status < 300:
            with ctx.db() as cur:
                cur.execute(
                    "UPDATE plat.webhook_entrega SET estado = 'entregue', tentativas = tentativas + 1, "
                    "ultima_status = %s, ultima_erro = NULL, entregue_em = now() WHERE id = %s::uuid",
                    (status, entrega_id),
                )
                cur.execute("UPDATE plat.webhook SET falhas_consecutivas = 0 WHERE id = %s",
                            (linha["webhook_id"],))
            ctx.progresso(100, f"entregue (HTTP {status})")
            return {"estado": "entregue", "status": status}
        erro = f"HTTP {status}"[:limites.WEBHOOK_ENTREGA_ERRO_MAX]

    # tentativa falhada: registra e decide se é a última (ctx.tentativa é 1-based; última = teto do job)
    ultima = ctx.tentativa >= limites.WEBHOOK_TENTATIVAS_MAX
    with ctx.db() as cur:
        cur.execute(
            "UPDATE plat.webhook_entrega SET tentativas = tentativas + 1, ultima_status = %s, "
            "ultima_erro = %s, estado = CASE WHEN %s THEN 'falhou' ELSE estado END WHERE id = %s::uuid",
            (status, erro, ultima, entrega_id),
        )
    ctx.log("AVISO", f"tentativa {ctx.tentativa}/{limites.WEBHOOK_TENTATIVAS_MAX} falhou: {erro}")
    if ultima:
        _desativar_se_preciso(ctx, linha["webhook_id"], linha["nome"], entrega_id)
        raise FalhaDefinitiva(f"entrega falhou após {limites.WEBHOOK_TENTATIVAS_MAX} tentativas: {erro}")
    # exceção comum: o pai devolve o job com espera 2**tentativa s (006) e a fila repete
    raise RuntimeError(f"entrega não confirmada: {erro}")
