"""Rotas da integração ArcGIS Online do cliente (item L2-08-migracao-agol; portado das rotas
`/api/integracoes/agol` e `/api/integracoes/agol/publicar` e do script de publicação AGOL do SIG
anterior). Diferenças do original, por causa do multi-inquilino do
PLAT: (1) a credencial fica cifrada em `tenant.config.agol` por INQUILINO (o original usava AGOL_USER/
AGOL_PASSWORD do `.env` do servidor, uma credencial só, compartilhada por todos os clientes que o processo
atendia — aqui isso seria um vazamento entre inquilinos); (2) a publicação roda na FILA de jobs (`agol.
publicar`, com progresso/log/cancelamento — o original disparava uma `threading.Thread` solta, sem fila, sem
RLS, sem retentativa); (3) o estado por camada fica em `plat.agol_publicacao` (RLS por tenant_id), não num
arquivo `data/agol_<tenant>.json` no disco do servidor. GET /api/agol/credencial e GET /api/agol/publicacoes
NUNCA devolvem a credencial cifrada nem em claro; POST /api/agol/testar decifra em memória, só para autenticar
o teste, e nunca a inclui na resposta nem em log."""

import datetime
import json

from fastapi import APIRouter, Request

from app import db
from app.agol import cliente, publicacao
from app.agol.cifra import cifrar as agol_cifrar
from app.agol.config import agol_efetivo, config_tenant_bruta, decifrar_credencial
from app.agol.modelos import (
    CredencialEntrada,
    CredencialSaida,
    PublicacaoJobSaida,
    PublicacaoSaida,
    PublicacoesPagina,
    PublicarEntrada,
    TesteSaida,
)
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento, uuid_ok
from app.erros import ErroAPI
from app.jobs import servico as jobs_servico
from app.jobs.contexto import sessao_de
from app.settings import settings

router = APIRouter(prefix="/api/agol", tags=["agol"])
PRIV_CREDENCIAL = {"x-auth": "S/T", "x-privilegio": "org.integracoes"}
PRIV_PUBLICAR = {"x-auth": "S/T", "x-privilegio": "conteudo.publicar_camada"}
PRIV_LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}


def _credencial_saida(config: dict | None) -> dict:
    cfg = agol_efetivo(config)
    if cfg is None:
        return {"configurado": False}
    return {"configurado": True, "portal": cfg.portal, "usuario": cfg.usuario, "tipo": cfg.tipo,
            "rotulo": cfg.rotulo}


@router.get("/credencial", response_model=CredencialSaida, openapi_extra=PRIV_CREDENCIAL)
def credencial_ler(auth: Auth = autenticado("org.integracoes")):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT config FROM plat.tenant WHERE id = plat.tenant_atual()")
        t = cur.fetchone()
    return _credencial_saida(t["config"] if t else None)


@router.put("/credencial", response_model=CredencialSaida, openapi_extra=PRIV_CREDENCIAL)
def credencial_gravar(corpo: CredencialEntrada, request: Request,
                      auth: Auth = autenticado("org.integracoes", so_sessao=True)):
    if corpo.credencial is not None and corpo.tipo is None:
        raise ErroAPI(422, "validacao", "informe tipo ('senha' ou 'token') junto da credencial",
                     {"campo": "tipo"})
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT config FROM plat.tenant WHERE id = plat.tenant_atual()")
        atual = config_tenant_bruta(cur.fetchone()["config"])

        tipo = atual.get("tipo")
        credencial_cifrada = atual.get("credencial_cifrada")
        credencial_alterada = False
        if corpo.remover_credencial:
            tipo = None
            credencial_cifrada = None
            credencial_alterada = True
        elif corpo.credencial:
            credencial_cifrada = agol_cifrar(corpo.credencial, settings.PLAT_SECRET)
            tipo = corpo.tipo
            credencial_alterada = True

        # portal/usuario/rotulo são SUBSTITUIÇÃO TOTAL a cada PUT (mesmo desenho de `app/correio/rotas_smtp.py`
        # para SMTP): quem chama sempre reenvia o estado inteiro que quer (a tela pré-preenche com o GET
        # anterior). Só `credencial`/`tipo` têm o desenho "None preserva a cifra, string vazia apaga" — o
        # valor em claro não pode ser reexibido para conferência, ao contrário de portal/usuario/rotulo.
        usuario = corpo.usuario.strip() or None
        if tipo == "senha" and not usuario:
            raise ErroAPI(422, "validacao", "credencial por senha exige o usuário da organização",
                         {"campo": "usuario"})
        agol = {
            "portal": corpo.portal.strip().rstrip("/") or None,
            "usuario": usuario,
            "tipo": tipo,
            "credencial_cifrada": credencial_cifrada,
            "rotulo": corpo.rotulo.strip() or None,
        }
        cur.execute(
            "UPDATE plat.tenant SET config = config || jsonb_build_object('agol', %s::jsonb) "
            "WHERE id = plat.tenant_atual() RETURNING config",
            (json.dumps(agol),),
        )
        novo = cur.fetchone()["config"]
        registrar_evento(cur, request, "org/agol_configurar", "tenant", auth.tenant_id,
                         {"portal": agol["portal"], "tipo": agol["tipo"], "credencial_alterada": credencial_alterada})
    return _credencial_saida(novo)


@router.post("/testar", response_model=TesteSaida, openapi_extra=PRIV_CREDENCIAL)
def credencial_testar(request: Request, auth: Auth = autenticado("org.integracoes", so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT config FROM plat.tenant WHERE id = plat.tenant_atual()")
        config = cur.fetchone()["config"]
    cfg = agol_efetivo(config)
    if cfg is None:
        raise ErroAPI(422, "agol_nao_configurado",
                      "configure a credencial ArcGIS Online do inquilino antes de testar (PUT /api/agol/credencial)")
    agora = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    credencial = decifrar_credencial(cfg, settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR)
    try:
        if cfg.tipo == "senha":
            token = cliente.gerar_token(cfg.portal, cfg.usuario or "", credencial)
        else:
            token = credencial
        info = cliente.info_portal(cfg.portal, token)
    except cliente.ErroAGOL as e:
        with db.db(auth.contexto()) as cur:
            registrar_evento(cur, request, "org/agol_testar", "tenant", auth.tenant_id,
                             {"ok": False, "mensagem": str(e)})
        return {"ok": False, "mensagem": str(e), "verificado_em": agora}
    finally:
        credencial = token = None  # noqa: F841 — nunca sobrevive além desta função, nunca vai a log/resposta
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "org/agol_testar", "tenant", auth.tenant_id,
                         {"ok": True, "organizacao": info.get("organizacao")})
    return {
        "ok": True, "mensagem": "credencial válida", "organizacao": info.get("organizacao"),
        "usuario_agol": info.get("usuario"), "creditos_disponiveis": info.get("creditos_disponiveis"),
        "verificado_em": agora,
    }


def _publicacao_saida(item_id: str, registro: dict | None) -> dict:
    if registro is None:
        return {"item_id": item_id, "estado": "nunca_publicado", "atualizado_em": None}
    return registro


@router.post("/publicacoes", response_model=PublicacaoJobSaida, status_code=202, openapi_extra=PRIV_PUBLICAR)
def publicacao_criar(corpo: PublicarEntrada, request: Request,
                     auth: Auth = autenticado("conteudo.publicar_camada")):
    item_id = uuid_ok(corpo.item_id, "item_inexistente", "item de camada vetorial inexistente")
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT id, dados FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial'", (item_id,)
        )
        item = cur.fetchone()
        if item is None:
            raise ErroAPI(404, "item_inexistente", "item de camada vetorial inexistente")
        if (item["dados"] or {}).get("fonte") != "hospedada":
            raise ErroAPI(409, "camada_referenciada",
                          "só camada vetorial hospedada pode ser publicada no ArcGIS Online")
        cur.execute("SELECT config FROM plat.tenant WHERE id = plat.tenant_atual()")
        if agol_efetivo(cur.fetchone()["config"]) is None:
            raise ErroAPI(422, "agol_nao_configurado",
                          "configure a credencial ArcGIS Online do inquilino antes de publicar "
                          "(PUT /api/agol/credencial)")
    job = jobs_servico.criar(sessao_de(auth), "agol.publicar", {"item_id": item_id, "titulo": corpo.titulo})
    with db.db(auth.contexto()) as cur:
        publicacao.registrar(cur, auth.tenant_id, item_id, job_id=job["id"], estado="pendente")
        registrar_evento(cur, request, "agol/publicar_iniciar", "item", item_id, {"job_id": job["id"]})
    return {"job_id": job["id"], "estado": job["estado"], "item_id": item_id}


@router.get("/publicacoes", response_model=PublicacoesPagina, openapi_extra=PRIV_LER)
def publicacoes_listar(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        itens = publicacao.listar(cur, auth.tenant_id)
    return {"itens": itens}


@router.get("/publicacoes/{item_id}", response_model=PublicacaoSaida, openapi_extra=PRIV_LER)
def publicacao_ver(item_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    iid = uuid_ok(item_id, "item_inexistente", "item de camada vetorial inexistente")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT id FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial'", (iid,))
        if cur.fetchone() is None:
            raise ErroAPI(404, "item_inexistente", "item de camada vetorial inexistente")
        registro = publicacao.obter(cur, auth.tenant_id, iid)
    return _publicacao_saida(iid, registro)
