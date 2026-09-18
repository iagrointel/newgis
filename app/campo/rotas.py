"""Rotas do módulo campo: duas frentes no mesmo pacote.

PWA de campo (item L2-07-a-pwa-instalavel-cache): aplicação instalável em `/campo/` para coleta em área sem
rede. Reusa o token de serviço genérico do L0-02-d (`plat.token_servico`) com o escopo `campo:usar` já reservado
no vocabulário (`app/auth/escopos.py`) — `router_pwa` só acrescenta o emissor de conveniência (`POST
/api/campo/sessao`, sessão → token de 30 dias, sem escolha de escopo/validade) e a listagem mínima de mapas
(`GET /api/campo/mapas`, reaproveitando `plat.item`/RLS do L0-03: nenhuma tabela nova). Todo o resto do item —
manifest, ícone, service worker, shell — é servido por rotas próprias em vez de `/static/` porque a trilha de
teste roda só `uvicorn` sem nginx na frente (ADR 0001 seção 4.3 vale para produção; aqui a app se basta).

Cache do shell: o nome do cache no service worker inclui `versao_shell()` (arquivo `web/campo/VERSAO_SHELL`,
não o git sha do repo inteiro — trocar só essa linha já é "nova versão do app" sem exigir commit; o campo lê o
arquivo a cada resposta, então o teste de invalidação de cache troca o conteúdo e recarrega, sem reiniciar o
servidor).

Fila de trabalho, roteiro do dia e visita com foto (item L2-07-campo): `router`, prefixo `/api/campo`, portado
do SIG anterior (`app/main.py`, rotas `/api/filas*`, `/api/rotas*`, `/api/visitas*`, `/api/fotos/{nome}`).
Privilégio único `campo.coletar` (já existe na casa desde a migração 003 — perfil `campo` inteiro foi
desenhado para isto) para toda escrita; leitura é `rls:visibilidade` (qualquer sessão válida do inquilino, a
RLS de cada tabela `plat.campo_*` já isola por `tenant_id`). Todas as rotas (leitura e escrita) exigem token
com o escopo `campo:usar` (item de seguimento de L0-04-a/L0-11: o vocabulário já tem `campo:usar` — usado por
`router_pwa` desde a origem —, mas este `router` continuava no padrão `admin:inquilino` de `autenticado()`
quando `escopo_token` não é passado, e o perfil `campo` nunca é admin do inquilino: o próprio operador de
campo não conseguia emitir um token para o próprio trabalho).

Dois `APIRouter` porque os dois nasceram em ramos diferentes com desenhos incompatíveis (um sem prefixo e
paths totalmente qualificados, o outro com `prefix="/api/campo"`); `app/main.py` inclui os dois
(`rotas_campo_pwa` e `rotas_campo.router`). Não há colisão de caminho entre eles — conferido na fusão."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from app import db, limites, objetos
from app.auth.escopos import cobre
from app.auth.sessao import Auth, autenticado, iso, opcional, sha256_hex
from app.campo import fotos, servico
from app.campo.modelos import (
    FilaAlvosAdicionar,
    FilaCriar,
    FilaOrdem,
    RoteiroCriar,
    VisitaCriar,
    VisitaFotoEntrada,
)
from app.catalogo.comum import registrar_evento, uuid_ok
from app.erros import ErroAPI
from app.formulario import motor as form_motor
from app.formulario import servico as form_servico

ROOT = Path(__file__).resolve().parents[2]
WEB_CAMPO = ROOT / "web" / "campo"
VERSAO_SHELL_ARQUIVO = WEB_CAMPO / "VERSAO_SHELL"

router_pwa = APIRouter(tags=["campo"])

CAMPO_TOKEN_DIAS = 30
CAMPO_TOKEN_NOME = "PWA de campo"


def versao_shell() -> str:
    try:
        return VERSAO_SHELL_ARQUIVO.read_text(encoding="utf-8").strip() or "0"
    except OSError:
        return "0"


def _sem_cache_json(corpo: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(corpo, status_code=status, headers={"Cache-Control": "no-store"})


def _inserir_token(cur, auth: Auth, nome: str, escopos: list[str], dias: int) -> tuple[dict, str]:
    """Cópia mínima de `app.auth.rotas_tokens._inserir` (mesma tabela, mesmo formato de valor `plat_<url-safe>`):
    campo é o único chamador com escopo fixo, e importar uma função privada de outro pacote acoplaria dois
    módulos que hoje mudam por trilhas diferentes — a redundância é 8 linhas, o acoplamento seria pior."""
    valor = "plat_" + secrets.token_urlsafe(32)
    cur.execute(
        "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos, restricao, "
        "expira_em) VALUES (%s, %s, %s, %s, %s, %s, '{}'::jsonb, now() + make_interval(days => %s)) "
        "RETURNING id, prefixo, escopos, expira_em",
        (auth.tenant_id, auth.usuario_id, nome, sha256_hex(valor), valor[:12], escopos, dias),
    )
    return cur.fetchone(), valor


def _arquivo(nome: str, media_type: str, cabecalhos: dict | None = None) -> FileResponse:
    caminho = WEB_CAMPO / nome
    if not caminho.is_file():
        raise ErroAPI(404, "arquivo_inexistente", "arquivo do PWA de campo inexistente")
    return FileResponse(caminho, media_type=media_type, headers=cabecalhos or {})


# ---------------------------------------------------------------- shell (HTML/CSS/JS/ícone), sem /static/
@router_pwa.api_route("/campo", methods=["GET", "HEAD"], include_in_schema=False)
@router_pwa.api_route("/campo/", methods=["GET", "HEAD"], include_in_schema=False)
def campo_shell():
    """`Cache-Control: no-store` na resposta HTTP não impede o service worker de guardar o corpo no Cache
    Storage (são mecanismos diferentes: `cache.put()` grava o que o `fetch()` devolveu, sem olhar o cabeçalho
    de cache do navegador) — por isso o shell pode ficar `no-store` (a versão de rede é sempre a mais nova) E
    aberto offline pelo service worker (a versão cacheada é sempre a que o `install` gravou). O atributo
    `data-versao-shell` deixa a versão visível no DOM para o teste de invalidação conferir sem ler o cache
    diretamente."""
    caminho = WEB_CAMPO / "index.html"
    if not caminho.is_file():
        raise ErroAPI(404, "arquivo_inexistente", "shell do PWA de campo inexistente")
    corpo = caminho.read_text(encoding="utf-8").replace("__VERSAO_SHELL__", versao_shell())
    return Response(corpo, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})


@router_pwa.get("/campo/campo.css", include_in_schema=False)
def campo_css():
    return _arquivo("campo.css", "text/css; charset=utf-8")


@router_pwa.get("/campo/app.js", include_in_schema=False)
def campo_app_js():
    return _arquivo("app.js", "text/javascript; charset=utf-8", {"Cache-Control": "no-store"})


@router_pwa.get("/campo/idb.js", include_in_schema=False)
def campo_idb_js():
    return _arquivo("idb.js", "text/javascript; charset=utf-8", {"Cache-Control": "no-store"})


@router_pwa.get("/campo/icone-192.png", include_in_schema=False)
def campo_icone_192():
    return _arquivo("icone-192.png", "image/png", {"Cache-Control": "public, max-age=86400"})


@router_pwa.get("/campo/icone-512.png", include_in_schema=False)
def campo_icone_512():
    return _arquivo("icone-512.png", "image/png", {"Cache-Control": "public, max-age=86400"})


@router_pwa.get("/campo/manifest.webmanifest", include_in_schema=False)
def campo_manifest(request: Request):
    """Manifest dinâmico: nome do inquilino e cor quando há sessão (o usuário chega aqui já logado na app
    principal); sem sessão (primeira visita direta, ou revisita do manifest pelo SO com cookie ausente) cai no
    nome/cor genéricos do produto — nunca falha, o manifest tem de existir para o navegador oferecer instalar."""
    nome = "plat · campo"
    cor = "#1f3a5f"
    auth = opcional(request)
    if auth is not None:
        nome = f"{auth.tenant_nome} · campo"
        cor = (auth.config or {}).get("cor") or cor
    corpo = {
        "id": "/campo/",
        "name": nome[: limites.ORG_NOME_MAX + 9],  # + " · campo"
        "short_name": "Campo",
        "description": "PWA de campo para coleta sem rede (análise / beta privado).",
        "start_url": "/campo/",
        "scope": "/campo/",
        "display": "standalone",
        "background_color": "#0b1622",
        "theme_color": cor,
        "lang": "pt-BR",
        "dir": "ltr",
        "icons": [
            {"src": "/campo/icone-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/campo/icone-192.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": "/campo/icone-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/campo/icone-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return JSONResponse(
        corpo,
        media_type="application/manifest+json",
        headers={"Cache-Control": "private, max-age=300"},
    )


_SW_MODELO = """// plat — service worker do PWA de campo (item L2-07-a-pwa-instalavel-cache). Gerado pela API
// (app/campo/rotas.py::campo_sw) para embutir a versão do shell; sem workbox, sem CDN. Escopo /campo/ pelo
// caminho do próprio script (registrado com scope explícito) e por Service-Worker-Allowed no cabeçalho HTTP.
const VERSAO = {versao!r};
const CACHE = `campo-shell-${{VERSAO}}`;
const SHELL = [
  '/campo/',
  '/campo/campo.css',
  '/campo/app.js',
  '/campo/idb.js',
  '/campo/manifest.webmanifest',
  '/campo/icone-192.png',
  '/campo/icone-512.png',
];

self.addEventListener('install', (evento) => {{
  evento.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
}});

self.addEventListener('activate', (evento) => {{
  evento.waitUntil(
    caches.keys()
      .then((nomes) => nomes.filter((n) => n.startsWith('campo-shell-') && n !== CACHE))
      .then((velhos) => Promise.all(velhos.map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
}});

// cache-first só para o shell (mesma origem, GET, sem /api/): dado de negócio nunca passa pelo Cache Storage
// do service worker — o app.js guarda mapas e fila no IndexedDB (idb.js), que é a fonte offline de verdade.
self.addEventListener('fetch', (evento) => {{
  const req = evento.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;
  if (!SHELL.includes(url.pathname)) return;
  evento.respondWith(
    caches.match(req).then((resposta) => resposta || fetch(req))
  );
}});
"""


@router_pwa.get("/campo/sw.js", include_in_schema=False)
def campo_sw():
    corpo = _SW_MODELO.format(versao=versao_shell())
    return Response(
        corpo,
        media_type="text/javascript; charset=utf-8",
        # CSP própria, sem a qual o middleware fecha com CSP_DADO (`default-src 'none'`): o worker herda a
        # política do script e todo `fetch` dele cai como connect-src 'none' (TypeError: Failed to fetch no
        # install, cache.addAll falha, e o Chromium apaga o registro recém-criado). Só precisa de connect-src.
        headers={
            "Cache-Control": "no-cache",
            "Service-Worker-Allowed": "/campo/",
            "Content-Security-Policy": "default-src 'none'; connect-src 'self'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        },
    )


# ---------------------------------------------------------------- API: sessão de campo e mapas
@router_pwa.post("/api/campo/sessao", status_code=201, openapi_extra={"x-auth": "S", "x-privilegio": "proprio"})
def campo_sessao(request: Request, auth: Auth = autenticado(escopo_token=None, so_sessao=True)):
    """Token de campo (L0-02-d): sempre escopo `campo:usar`, sempre `CAMPO_TOKEN_DIAS` dias, sem escolha —
    é a única forma de emitir esse escopo (a rota genérica `/api/tokens` também aceitaria, mas o PWA sempre
    chama esta para não expor o formulário completo de tokens a quem só quer entrar em campo). Revogável como
    qualquer token de serviço, por `DELETE /api/tokens/{id}` (mesma tabela, sem rota própria de revogar)."""
    dias = min(CAMPO_TOKEN_DIAS, auth.politica.token_max_dias)
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT count(*) AS n FROM plat.token_servico WHERE usuario_id = %s AND revogado_em IS NULL "
            "AND (expira_em IS NULL OR expira_em > now())",
            (auth.usuario_id,),
        )
        if cur.fetchone()["n"] >= limites.TOKENS_POR_USUARIO:
            raise ErroAPI(422, "limite_tokens", f"no máximo {limites.TOKENS_POR_USUARIO} tokens ativos por usuário")
        r, valor = _inserir_token(cur, auth, CAMPO_TOKEN_NOME, ["campo:usar"], dias)
        # nunca gravar `valor` (o token em claro) no evento — só metadado, mesmo padrão de tokens/criar
        registrar_evento(cur, request, "campo/sessao", "token", r["id"], {"validade_dias": dias})
    return {
        "token": valor,
        "id": r["id"],
        "escopos": list(r["escopos"]),
        "expira_em": iso(r["expira_em"]),
        "tenant_slug": auth.tenant_slug,
    }


@router_pwa.get("/api/campo/mapas", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"})
def campo_mapas(auth: Auth = autenticado(escopo_token="campo:usar")):
    """Mapas de campo (tipo `mapa`, item L2-01-a) legíveis pelo dono do token/sessão — RLS de `plat.item`
    (`plat.pode_ler`) já resolve a visibilidade; aqui só filtra o tipo e projeta o mínimo para caber no
    orçamento do shell offline (o documento inteiro fica pesado; a área/tiles por mapa é o L2-07-d, não este
    item — aqui cacheamos só o que identifica e localiza o mapa, não a base cartográfica)."""
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT id, titulo, resumo, dados, ST_AsGeoJSON(extent) AS extent, tamanho_bytes, "
            "modificado_em FROM plat.item WHERE tipo = 'mapa' AND apagado_em IS NULL "
            "ORDER BY modificado_em DESC LIMIT %s",
            (limites.CAMPO_MAPAS_MAX,),
        )
        linhas = cur.fetchall()
    return {
        "mapas": [
            {
                "id": str(r["id"]),
                "titulo": r["titulo"],
                "resumo": r["resumo"],
                # `dados` do tipo `mapa` (migração 011) é {"esquema_versao": int, "corpo": object livre} — o
                # conteúdo de `corpo` (camadas por uuid) é de um item de EDIÇÃO de mapa ainda não construído
                # (L2-03/L2-01 seguintes); aqui só projeta o que já existe hoje, sem inventar uma forma.
                "camadas": ((r["dados"] or {}).get("corpo") or {}).get("camadas", []),
                "extent": json.loads(r["extent"]) if r["extent"] else None,
                "tamanho_bytes": r["tamanho_bytes"],
                "modificado_em": iso(r["modificado_em"]),
            }
            for r in linhas
        ],
        "cobre": cobre(auth.escopos, "admin:inquilino") if auth.modo == "token" else True,
    }


router = APIRouter(prefix="/api/campo", tags=["campo"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ESCREVER = {"x-auth": "S/T", "x-privilegio": "campo.coletar"}
SEM_CACHE = {"Cache-Control": "no-store, must-revalidate"}


def _foto_url(chave: str) -> str:
    return objetos.url_assinada(chave, 3600)


def _fila_json(f: dict, extra: dict | None = None) -> dict:
    j = {
        "id": str(f["id"]),
        "titulo": f["titulo"],
        "camada_id": str(f["camada_id"]),
        "status": f["status"],
        "criado_em": iso(f.get("criado_em")),
        "atualizado_em": iso(f.get("atualizado_em")),
    }
    if extra:
        j.update(extra)
    return j


def _alvo_json(a: dict) -> dict:
    return {
        "id": str(a["id"]),
        "globalid": str(a["globalid"]),
        "ordem": a["ordem"],
        "nota": a["nota"],
        "status": a["status"],
    }


def _visita_json(v: dict) -> dict:
    fotos_json = [
        {**{k: f[k] for k in ("id", "sha256", "bytes", "largura", "altura") if k in f}, "url": _foto_url(f["chave"])}
        for f in (v.get("fotos") or [])
    ]
    return {
        "id": str(v["id"]),
        "cliente_uuid": str(v["cliente_uuid"]) if v.get("cliente_uuid") else None,
        "fila_id": str(v["fila_id"]) if v.get("fila_id") else None,
        "alvo_id": str(v["alvo_id"]) if v.get("alvo_id") else None,
        "roteiro_id": str(v["roteiro_id"]) if v.get("roteiro_id") else None,
        "camada_id": str(v["camada_id"]),
        "globalid": str(v["globalid"]),
        "status": v["status"],
        "texto": v.get("texto"),
        "usuario_id": v.get("usuario_id"),
        "usuario_login": v.get("usuario_login"),
        "lat": v.get("lat"),
        "lon": v.get("lon"),
        "gps_acc_m": v.get("gps_acc_m"),
        "capturado_em": v.get("capturado_em"),
        "recebido_em": iso(v.get("recebido_em")),
        "dados": v.get("dados") or {},
        "fotos": fotos_json,
    }


# ---------------------------------------------------------------------- camada de origem (apoio da tela de criação)
@router.get("/camadas/{camada_id}/globalids", openapi_extra=LER)
def camada_globalids(camada_id: str, limite: int = 200, auth: Auth = autenticado(escopo_token="campo:usar")) -> dict:
    """Lista curta de feições da camada (globalid + rótulo) para a tela de criação de fila escolher os
    alvos sem precisar de um visualizador de mapa completo."""
    cid = uuid_ok(camada_id, "item_inexistente", "item de camada inexistente")
    limite = max(1, min(limite, 1000))
    with db.db(auth.contexto()) as cur:
        _item, dados = servico.camada_ou_404(cur, cid)
        return {"feicoes": servico.listar_globalids(cur, dados, limite)}


# ---------------------------------------------------------------------- fila
@router.post("/filas", status_code=201, openapi_extra=ESCREVER)
def criar_fila(
    corpo: FilaCriar, request: Request, auth: Auth = autenticado("campo.coletar", escopo_token="campo:usar")
):
    camada_id = uuid_ok(corpo.camada_id, "item_inexistente", "item de camada inexistente")
    with db.db(auth.contexto()) as cur:
        r = servico.fila_criar(cur, auth, corpo.titulo, camada_id, corpo.globalids)
        registrar_evento(
            cur,
            request,
            "campo/fila_criar",
            "campo_fila",
            r["id"],
            {
                "camada_id": camada_id,
                "adicionados": r["adicionados"],
                "ignorados": len(r["ignorados"]),
            },
        )
    return r


@router.get("/filas", openapi_extra=LER)
def listar_filas(auth: Auth = autenticado(escopo_token="campo:usar")) -> dict:
    with db.db(auth.contexto()) as cur:
        linhas = servico.filas_listar(cur)
    return {
        "filas": [
            _fila_json(f, {"n_alvos": f["n_alvos"], "n_visitados": f["n_visitados"], "n_roteiros": f["n_roteiros"]})
            for f in linhas
        ]
    }


@router.get("/filas/{fila_id}", openapi_extra=LER)
def ver_fila(fila_id: str, auth: Auth = autenticado(escopo_token="campo:usar")) -> dict:
    fid = uuid_ok(fila_id, "fila_inexistente", "fila inexistente")
    with db.db(auth.contexto()) as cur:
        f = servico.fila_ou_404(cur, fid)
        alvos = servico.fila_alvos_listar(cur, fid)
        roteiros = servico.roteiros_listar(cur, fid)
    return {
        "fila": _fila_json(f),
        "alvos": [_alvo_json(a) for a in alvos],
        "roteiros": [
            {
                "id": str(r["id"]),
                "titulo": r["titulo"],
                "motor": r["motor"],
                "n_paradas": r["n_paradas"],
                "distancia_m": r["distancia_m"],
                "duracao_s": r["duracao_s"],
                "criado_em": iso(r["criado_em"]),
            }
            for r in roteiros
        ],
    }


@router.get("/filas/{fila_id}/alvos.geojson", openapi_extra=LER)
def alvos_geojson(fila_id: str, auth: Auth = autenticado(escopo_token="campo:usar")) -> JSONResponse:
    """Camada de alvos da fila (item 4 do pedido: `GET /api/rede/{id}/feicoes/*.geojson` é o molde já usado
    pela rede de utilidades; aqui a MESMA forma para os alvos de uma fila de campo, com o estado de visita em
    cada feição para colorir no mapa)."""
    fid = uuid_ok(fila_id, "fila_inexistente", "fila inexistente")
    with db.db(auth.contexto()) as cur:
        f = servico.fila_ou_404(cur, fid)
        alvos = servico.fila_alvos_listar(cur, fid)
        _item, dados_camada = servico.camada_ou_404(cur, str(f["camada_id"]))
        fc = servico.feicoes_geojson(cur, dados_camada, [str(a["globalid"]) for a in alvos])
    por_globalid = {str(a["globalid"]): a for a in alvos}
    for feat in fc["features"]:
        a = por_globalid.get(feat["properties"]["globalid"])
        if a:
            feat["properties"].update({"alvo_id": str(a["id"]), "ordem": a["ordem"], "status": a["status"]})
    return JSONResponse(fc, headers=SEM_CACHE)


@router.post("/filas/{fila_id}/alvos", status_code=201, openapi_extra=ESCREVER)
def adicionar_alvos(
    fila_id: str,
    corpo: FilaAlvosAdicionar,
    request: Request,
    auth: Auth = autenticado("campo.coletar", escopo_token="campo:usar"),
):
    fid = uuid_ok(fila_id, "fila_inexistente", "fila inexistente")
    with db.db(auth.contexto()) as cur:
        f = servico.fila_ou_404(cur, fid)
        _item, dados_camada = servico.camada_ou_404(cur, str(f["camada_id"]))
        adicionados, ignorados = servico.fila_alvos_adicionar(cur, auth, fid, dados_camada, corpo.globalids)
        registrar_evento(
            cur,
            request,
            "campo/fila_alvos_adicionar",
            "campo_fila",
            fid,
            {
                "adicionados": adicionados,
                "ignorados": len(ignorados),
            },
        )
    return {"adicionados": adicionados, "ignorados": ignorados}


@router.put("/filas/{fila_id}/ordem", openapi_extra=ESCREVER)
def reordenar_fila(
    fila_id: str,
    corpo: FilaOrdem,
    request: Request,
    auth: Auth = autenticado("campo.coletar", escopo_token="campo:usar"),
):
    fid = uuid_ok(fila_id, "fila_inexistente", "fila inexistente")
    with db.db(auth.contexto()) as cur:
        servico.fila_ou_404(cur, fid)
        n = servico.fila_ordem_atualizar(cur, fid, [uuid_ok(a) for a in corpo.alvo_ids])
        registrar_evento(cur, request, "campo/fila_ordem_atualizar", "campo_fila", fid, {"reordenados": n})
    return {"reordenados": n}


# ---------------------------------------------------------------------- roteiro
@router.post("/roteiros", status_code=201, openapi_extra=ESCREVER)
def criar_roteiro(
    corpo: RoteiroCriar, request: Request, auth: Auth = autenticado("campo.coletar", escopo_token="campo:usar")
):
    fid = uuid_ok(corpo.fila_id, "fila_inexistente", "fila inexistente")
    origem = {"lon": corpo.origem.lon, "lat": corpo.origem.lat}
    with db.db(auth.contexto()) as cur:
        r = servico.roteiro_criar(
            cur, auth, fid, origem, corpo.titulo, [uuid_ok(a) for a in corpo.alvo_ids], corpo.maximo
        )
        registrar_evento(
            cur,
            request,
            "campo/roteiro_criar",
            "campo_roteiro",
            r["id"],
            {
                "fila_id": fid,
                "motor": r["motor"],
                "n_paradas": r["n_paradas"],
            },
        )
    return {**r, "criado_em": iso(r["criado_em"])}


@router.get("/roteiros", openapi_extra=LER)
def listar_roteiros(fila_id: str | None = None, auth: Auth = autenticado(escopo_token="campo:usar")) -> dict:
    fid = uuid_ok(fila_id) if fila_id else None
    with db.db(auth.contexto()) as cur:
        linhas = servico.roteiros_listar(cur, fid)
    return {
        "roteiros": [
            {
                "id": str(r["id"]),
                "fila_id": str(r["fila_id"]),
                "titulo": r["titulo"],
                "motor": r["motor"],
                "distancia_m": r["distancia_m"],
                "duracao_s": r["duracao_s"],
                "n_paradas": r["n_paradas"],
                "criado_em": iso(r["criado_em"]),
            }
            for r in linhas
        ]
    }


@router.get("/roteiros/{roteiro_id}", openapi_extra=LER)
def ver_roteiro(roteiro_id: str, auth: Auth = autenticado(escopo_token="campo:usar")) -> dict:
    rid = uuid_ok(roteiro_id, "roteiro_inexistente", "roteiro inexistente")
    with db.db(auth.contexto()) as cur:
        r = servico.roteiro_ou_404(cur, rid)
        paradas = servico.roteiro_paradas(cur, rid)
    return {
        "id": str(r["id"]),
        "fila_id": str(r["fila_id"]),
        "titulo": r["titulo"],
        "origem": {"lon": r["origem_lon"], "lat": r["origem_lat"]},
        "motor": r["motor"],
        "distancia_m": r["distancia_m"],
        "duracao_s": r["duracao_s"],
        "aviso": r["aviso"],
        "criado_em": iso(r["criado_em"]),
        "paradas": [
            {
                "ordem": p["ordem"],
                "alvo_id": str(p["alvo_id"]),
                "globalid": str(p["globalid"]),
                "status": p["status"],
                "nota": p["nota"],
                "trecho_m": p["trecho_m"],
                "trecho_s": p["trecho_s"],
                "visita_id": str(p["visita_id"]) if p["visita_id"] else None,
            }
            for p in paradas
        ],
    }


@router.get("/roteiros/{roteiro_id}/trajeto.geojson", openapi_extra=LER)
def roteiro_trajeto_geojson(roteiro_id: str, auth: Auth = autenticado(escopo_token="campo:usar")) -> JSONResponse:
    rid = uuid_ok(roteiro_id, "roteiro_inexistente", "roteiro inexistente")
    with db.db(auth.contexto()) as cur:
        r = servico.roteiro_ou_404(cur, rid)
    feature = {
        "type": "Feature",
        "id": str(r["id"]),
        "properties": {
            "titulo": r["titulo"],
            "motor": r["motor"],
            "distancia_m": r["distancia_m"],
            "duracao_s": r["duracao_s"],
            "aviso": r["aviso"],
        },
        "geometry": r["geometria"],
    }
    return JSONResponse({"type": "FeatureCollection", "features": [feature]}, headers=SEM_CACHE)


# ---------------------------------------------------------------------- visita
@router.post("/visitas", status_code=201, openapi_extra=ESCREVER)
def criar_visita(
    corpo: VisitaCriar, request: Request, auth: Auth = autenticado("campo.coletar", escopo_token="campo:usar")
):
    # existência de alvo/fila/roteiro é conferida aqui (404 antes de tocar a tabela de visita); a feição em si
    # NUNCA é exigida existir ainda na camada — visitar algo que já sumiu da camada continua sendo um FATO
    if corpo.fila_id:
        with db.db(auth.contexto()) as cur:
            servico.fila_ou_404(cur, uuid_ok(corpo.fila_id))
    if corpo.alvo_id:
        with db.db(auth.contexto()) as cur:
            cur.execute("SELECT 1 FROM plat.campo_alvo WHERE id = %s::uuid", (uuid_ok(corpo.alvo_id),))
            if cur.fetchone() is None:
                raise ErroAPI(404, "alvo_inexistente", "alvo inexistente")
    cid = uuid_ok(corpo.camada_id, "item_inexistente", "item de camada inexistente")
    with db.db(auth.contexto()) as cur:
        servico.camada_ou_404(cur, cid)
        # item L5-03-form-builder: se a camada tem formulário PUBLICADO, `dados` (jsonb livre da visita)
        # passa pelo MESMO motor que valida `POST /api/camadas/{id}/edicoes` (obrigatório/domínio) mais
        # condicional/cálculo (que a edição já compila em regras_campo/form_condicionais/form_calculados,
        # e aqui roda direto sobre o desenho — ver app/formulario/motor.py::validar_dados_livre). Sem
        # formulário publicado, o comportamento é o de sempre (dados livre, sem validação nenhuma).
        desenho = form_servico.desenho_publicado(cur, cid)
        if desenho:
            corpo.dados, _avisos_form = form_motor.validar_dados_livre(desenho, corpo.dados)
        visita, criada = servico.visita_criar(cur, auth, corpo)
        if criada:
            registrar_evento(
                cur,
                request,
                "campo/visita_registrar",
                "campo_visita",
                str(visita["id"]),
                {
                    "status": corpo.status,
                    "fila_id": corpo.fila_id,
                    "alvo_id": corpo.alvo_id,
                },
            )
    return JSONResponse(
        {**_visita_json(visita), "ja_existia": not criada},
        status_code=201 if criada else 200,
    )


@router.get("/visitas", openapi_extra=LER)
def listar_visitas(
    fila_id: str | None = None,
    alvo_id: str | None = None,
    roteiro_id: str | None = None,
    limite: int = 500,
    auth: Auth = autenticado(escopo_token="campo:usar"),
) -> dict:
    with db.db(auth.contexto()) as cur:
        linhas = servico.visitas_listar(
            cur,
            fila_id=uuid_ok(fila_id) if fila_id else None,
            alvo_id=uuid_ok(alvo_id) if alvo_id else None,
            roteiro_id=uuid_ok(roteiro_id) if roteiro_id else None,
            limite=limite,
        )
    return {
        "visitas": [
            {
                "id": str(v["id"]),
                "fila_id": str(v["fila_id"]) if v["fila_id"] else None,
                "alvo_id": str(v["alvo_id"]) if v["alvo_id"] else None,
                "camada_id": str(v["camada_id"]),
                "globalid": str(v["globalid"]),
                "status": v["status"],
                "texto": v["texto"],
                "usuario_login": v["usuario_login"],
                "lat": v["lat"],
                "lon": v["lon"],
                "capturado_em": v["capturado_em"],
                "recebido_em": iso(v["recebido_em"]),
                "n_fotos": v["n_fotos"],
            }
            for v in linhas
        ]
    }


@router.get("/visitas/{visita_id}", openapi_extra=LER)
def ver_visita(visita_id: str, auth: Auth = autenticado(escopo_token="campo:usar")) -> dict:
    vid = uuid_ok(visita_id, "visita_inexistente", "visita inexistente")
    with db.db(auth.contexto()) as cur:
        v = servico.visita_ou_404(cur, vid)
    return _visita_json(v)


@router.post("/visitas/{visita_id}/fotos", status_code=201, openapi_extra=ESCREVER)
def enviar_foto(
    visita_id: str,
    corpo: VisitaFotoEntrada,
    request: Request,
    auth: Auth = autenticado("campo.coletar", escopo_token="campo:usar"),
):
    vid = uuid_ok(visita_id, "visita_inexistente", "visita inexistente")
    dados = fotos.decodificar_base64(corpo.conteudo)
    with db.db(auth.contexto()) as cur:
        servico.visita_ou_404(cur, vid)
        f = servico.visita_foto_guardar(cur, auth, vid, dados)
        registrar_evento(
            cur,
            request,
            "campo/visita_foto_enviar",
            "campo_visita",
            vid,
            {
                "foto_id": f["id"],
                "bytes": f["bytes"],
            },
        )
    return {**{k: v for k, v in f.items() if k != "chave"}, "url": _foto_url(f["chave"])}


__all__ = ["router", "router_pwa"]
