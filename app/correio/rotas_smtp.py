"""SMTP por inquilino (item L0-07-d-smtp-convites; ADR 0013): `GET/PUT /api/org/smtp` sobre
`tenant.config->'smtp'` (mesmo padrão de merge parcial de `app/auth/rotas_org.py`: esta rota nunca reescreve
`config` inteiro) e `POST /api/org/smtp/testar`, envio SÍNCRONO (não pela fila) para que o erro volte na
mesma resposta, legível, sem senha. Privilégio único `org.integracoes` (semeado na migração 003, descrição
"SSO, SMTP, webhooks, CORS" — já previsto para este item)."""

import json

from fastapi import APIRouter, Request

from app import db, limites
from app.auth.comum import registrar_evento
from app.auth.sessao import Auth, autenticado
from app.correio import cliente
from app.correio.cifra import cifrar
from app.correio.config import config_tenant_bruta, decifrar_senha, smtp_efetivo
from app.correio.modelos import SMTPEntrada, SMTPSaida, SMTPTestarEntrada, SMTPTestarSaida
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(prefix="/api/org/smtp", tags=["smtp"])
PRIV = {"x-auth": "S/T", "x-privilegio": "org.integracoes"}


def _saida(config: dict | None) -> dict:
    bruta = config_tenant_bruta(config)
    cfg = smtp_efetivo(config, settings)
    if cfg is None:
        return {"configurado": False, "origem": "nenhum"}
    return {
        "configurado": True,
        "origem": cfg.origem,
        "host": cfg.host,
        "porta": cfg.porta,
        "tls": cfg.tls,
        "usuario": cfg.usuario,
        "remetente": cfg.remetente,
        "rotulo": cfg.rotulo,
        # a senha da instalação (.env/systemd) nunca é "configurada pelo inquilino": só a cifra por-inquilino conta
        "senha_configurada": bool(bruta.get("senha_cifrada")) if cfg.origem == "inquilino" else bool(cfg.senha_cifrada),
    }


@router.get("", response_model=SMTPSaida, openapi_extra=PRIV)
def smtp_ler(auth: Auth = autenticado("org.integracoes")):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT config FROM plat.tenant WHERE id = plat.tenant_atual()")
        t = cur.fetchone()
    return _saida(t["config"])


@router.put("", response_model=SMTPSaida, openapi_extra=PRIV)
def smtp_gravar(corpo: SMTPEntrada, request: Request, auth: Auth = autenticado("org.integracoes", so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT config FROM plat.tenant WHERE id = plat.tenant_atual()")
        atual = config_tenant_bruta(cur.fetchone()["config"])
        if not corpo.host.strip():
            # host vazio: apaga o override inteiro do inquilino (volta para a instalação/caminho manual)
            cur.execute("UPDATE plat.tenant SET config = config - 'smtp' WHERE id = plat.tenant_atual() "
                        "RETURNING config")
            novo = cur.fetchone()["config"]
            registrar_evento(cur, request, "org/smtp_remover", "tenant", auth.tenant_id, {})
            return _saida(novo)
        if not corpo.remetente.strip():
            raise ErroAPI(422, "validacao", "remetente é obrigatório quando host é informado", {"campo": "remetente"})
        if corpo.senha is None:
            senha_cifrada = atual.get("senha_cifrada")
        elif corpo.senha == "":
            senha_cifrada = None
        else:
            senha_cifrada = cifrar(corpo.senha, settings.PLAT_SECRET)
        smtp = {
            "host": corpo.host.strip(),
            "porta": corpo.porta,
            "tls": corpo.tls,
            "usuario": corpo.usuario.strip() or None,
            "senha_cifrada": senha_cifrada,
            "remetente": corpo.remetente.strip(),
            "rotulo": corpo.rotulo.strip() or None,
        }
        cur.execute(
            "UPDATE plat.tenant SET config = config || jsonb_build_object('smtp', %s::jsonb) "
            "WHERE id = plat.tenant_atual() RETURNING config",
            (json.dumps(smtp),),
        )
        novo = cur.fetchone()["config"]
        registrar_evento(cur, request, "org/smtp_configurar", "tenant", auth.tenant_id,
                         {"host": smtp["host"], "porta": smtp["porta"], "tls": smtp["tls"],
                          "senha_alterada": corpo.senha is not None})  # nunca a senha em si
    return _saida(novo)


@router.post("/testar", response_model=SMTPTestarSaida, openapi_extra=PRIV)
def smtp_testar(corpo: SMTPTestarEntrada, request: Request,
                 auth: Auth = autenticado("org.integracoes", so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT config FROM plat.tenant WHERE id = plat.tenant_atual()")
        config = cur.fetchone()["config"]
    cfg = smtp_efetivo(config, settings)
    if cfg is None:
        raise ErroAPI(422, "smtp_nao_configurado", "configure o SMTP do inquilino (ou da instalação) antes de testar")
    destinatario = corpo.destinatario or auth.email
    if not destinatario:
        raise ErroAPI(422, "validacao", "informe um destinatário (o seu usuário não tem e-mail cadastrado)",
                      {"campo": "destinatario"})
    senha = decifrar_senha(cfg, settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR)
    try:
        cliente.enviar(cfg, senha, destinatario, "Teste de envio SMTP",
                       f"Este é um envio de teste do SMTP configurado para {auth.tenant_nome}.",
                       timeout=limites.SMTP_CONECTAR_TIMEOUT_S)
    except cliente.ErroSMTP as e:
        with db.db(auth.contexto()) as cur:
            registrar_evento(cur, request, "org/smtp_testar", "tenant", auth.tenant_id,
                             {"ok": False, "destinatario": destinatario, "erro": str(e)})
        raise ErroAPI(502, "smtp_falhou", str(e)) from e
    finally:
        senha = None  # noqa: F841
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "org/smtp_testar", "tenant", auth.tenant_id,
                         {"ok": True, "destinatario": destinatario})
    return {"ok": True, "destinatario": destinatario}
