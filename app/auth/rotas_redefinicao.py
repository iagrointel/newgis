"""Redefinição de senha por e-mail (item L0-07-d-smtp-convites; ADR 0002 seção 6.3, ADR 0013): três rotas
públicas, sem sessão — `POST /api/senha/redefinir/solicitar` (SEMPRE responde `{"ok": true}` exceto quando o
limite de taxa estourou, para não denunciar por status se o e-mail existe), `GET /api/senha/redefinir/resolver`
(só para a tela decidir se mostra o formulário) e `POST /api/senha/redefinir/aplicar`. O limite de taxa
(`plat.redefinicao_solicitar`, item `REDEFINICAO_MAX_JANELA` por `REDEFINICAO_JANELA_MIN` minutos, chave
inquilino+e-mail) é a defesa contra a refutação do item ("1.000 pedidos para o mesmo e-mail em 1 minuto")."""

from fastapi import APIRouter, Request

from app import db, limites
from app.auth.comum import registrar_evento
from app.auth.modelos_redefinicao import (
    RedefinicaoAplicada,
    RedefinicaoAplicarEntrada,
    RedefinicaoResolvida,
    RedefinicaoSolicitarEntrada,
    RedefinicaoSolicitarSaida,
)
from app.auth.politica import mensagem_da_regra, politica_de, regra_da_senha
from app.auth.sessao import ip_de, sha256_hex
from app.correio import textos
from app.correio.config import smtp_efetivo
from app.erros import ErroAPI
from app.jobs import sistema as jobs_sistema
from app.senha import gerar_hash, verificar
from app.settings import settings

router = APIRouter(prefix="/api/senha/redefinir", tags=["redefinicao"])
PUBLICO = {"x-auth": "-", "x-privilegio": "publico"}


def _link(token: str) -> str:
    return f"{settings.PLAT_URL_PUBLICA}/redefinir-senha?token={token}"


@router.post("/solicitar", response_model=RedefinicaoSolicitarSaida, status_code=202, openapi_extra=PUBLICO)
def solicitar(corpo: RedefinicaoSolicitarEntrada, request: Request):
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.redefinicao_solicitar(%s, %s, %s, %s, %s, %s)",
                    (corpo.inquilino.strip(), corpo.email.strip(), ip_de(request),
                     limites.REDEFINICAO_JANELA_MIN, limites.REDEFINICAO_MAX_JANELA,
                     limites.REDEFINICAO_VALIDADE_HORAS))
        r = cur.fetchone()
    if not r["permitido"]:
        raise ErroAPI(429, "muitas_tentativas",
                      f"muitos pedidos de redefinição para este e-mail; aguarde {limites.REDEFINICAO_JANELA_MIN} "
                      "minutos e tente de novo")
    if r["token"] is None:
        return {"ok": True}  # e-mail não encontrado: mesma resposta, sem enfileirar nada (não revela existência)
    with db.db() as cur:
        cur.execute("SELECT config FROM plat.tenant WHERE id = %s", (r["tenant_id"],))
        config = cur.fetchone()["config"]
    if smtp_efetivo(config, settings) is not None:
        jobs_sistema.enfileirar(
            r["tenant_id"], "correio.enviar",
            {"destinatario": corpo.email.strip(), "assunto": textos.redefinicao_assunto(r["tenant_nome"]),
             "texto": textos.redefinicao_texto(r["tenant_nome"], r["login"], _link(r["token"]),
                                                limites.REDEFINICAO_VALIDADE_HORAS),
             "categoria": "redefinicao_senha"},
            usuario_id=r["usuario_id"],
        )
    # sem SMTP: não há caminho manual para "esqueci a senha" (ADR 0002 seção 6.3) — o pedido fica registrado
    # (rate limit já contou) mas sem e-mail o convidado precisa pedir ao admin (POST /api/usuarios/{id}/senha)
    return {"ok": True}


@router.get("/resolver", response_model=RedefinicaoResolvida, openapi_extra=PUBLICO)
def resolver(token: str):
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.redefinicao_resolver(%s)", (sha256_hex(token),))
        r = cur.fetchone()
    if r["motivo"] != "ok":
        raise ErroAPI(410, f"redefinicao_{r['motivo']}", "este link não pode mais ser usado",
                      {"motivo": r["motivo"]})
    return {"motivo": "ok"}


@router.post("/aplicar", response_model=RedefinicaoAplicada, openapi_extra=PUBLICO)
def aplicar(corpo: RedefinicaoAplicarEntrada, request: Request):
    token_hash = sha256_hex(corpo.token)
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.redefinicao_contexto(%s)", (token_hash,))
        c = cur.fetchone()
    if c["motivo"] != "ok":
        raise ErroAPI(410, f"redefinicao_{c['motivo']}", "este link não pode mais ser usado",
                      {"motivo": c["motivo"]})
    politica = politica_de(c["config"], c["tenant_slug"])
    regra = regra_da_senha(corpo.senha, politica, c["login"], c["tenant_slug"], "")
    if regra:
        raise ErroAPI(422, "senha_fraca", mensagem_da_regra(regra, politica), {"regra": regra})
    ctx = db.Contexto(c["tenant_id"], c["usuario_id"], c["login"])
    with db.db(ctx) as cur:
        # trava o token DENTRO do contexto do próprio usuário-alvo (RLS já isola por tenant_id): fecha a
        # corrida de duplo-envio do MESMO link (dois POST /aplicar quase simultâneos) sem duplicar a lógica
        # de troca de senha/histórico de app/auth/rotas_eu.py::trocar_senha.
        cur.execute("SELECT plat.redefinicao_marcar_usada(%s, %s) AS ok", (token_hash, c["usuario_id"]))
        if not cur.fetchone()["ok"]:
            raise ErroAPI(410, "redefinicao_usado", "este link não pode mais ser usado", {"motivo": "usado"})
        n = politica.senha_historico
        cur.execute("SELECT senha_hash FROM plat.usuario WHERE id = %s", (c["usuario_id"],))
        atual = cur.fetchone()["senha_hash"]
        cur.execute(
            "SELECT senha_hash FROM plat.senha_historico WHERE usuario_id = %s ORDER BY criado_em DESC LIMIT %s",
            (c["usuario_id"], max(n - 1, 0)),
        )
        anteriores = ([atual] + [r["senha_hash"] for r in cur.fetchall()]) if n > 0 and atual else []
        if any(verificar(corpo.senha, h) for h in anteriores):
            raise ErroAPI(422, "senha_fraca", mensagem_da_regra("historico", politica), {"regra": "historico"})
        cur.execute(
            "UPDATE plat.usuario SET senha_hash = %s, senha_alterada_em = now(), trocar_senha = false, "
            "bloqueado_ate = NULL, falhas_login = 0, falhas_desde = NULL WHERE id = %s",
            (gerar_hash(corpo.senha), c["usuario_id"]),
        )
        if n > 0 and atual:
            cur.execute("INSERT INTO plat.senha_historico(usuario_id, senha_hash) VALUES (%s, %s)",
                        (c["usuario_id"], atual))
            cur.execute(
                "DELETE FROM plat.senha_historico WHERE usuario_id = %s AND id NOT IN "
                "(SELECT id FROM plat.senha_historico WHERE usuario_id = %s ORDER BY criado_em DESC LIMIT %s)",
                (c["usuario_id"], c["usuario_id"], n),
            )
        cur.execute("SELECT plat.sessoes_encerrar_usuario(%s, NULL)", (c["usuario_id"],))
        registrar_evento(cur, request, "usuarios/redefinir_senha_email", "usuario", c["usuario_id"],
                         {"ip": ip_de(request)})
    return {"ok": True}
