"""Rotas do layout de impressão (item L2-12-b-layouts-elementos-exportacao):

* `GET /api/layouts/modelos` — modelos padrão (código) e do inquilino (itens `layout` com `modelo: true`);
  `GET /api/layouts/modelos/{id}` devolve o documento de um modelo padrão.
* `POST /api/layouts/validar` — normaliza o documento ou 422 nomeando o campo (o formulário do painel usa).
* `POST /api/layouts/previa` — PNG de pré-visualização (≤ 96 DPI), com os quadros de mapa desenhados pelo motor
  de render (`quadros: true`) ou como área cinza (instantâneo, para posicionar elementos).
* `POST /api/layouts/exportar` — cria o job `layout.exportar` (PDF/PNG/JPG/SVG, 72-300 DPI) e devolve o job;
  o arquivo sai em `GET /api/arquivos/{sha256}?classe=layout_exportacao` quando o job termina.
* `GET /render/layout-mapa` + `GET /api/render/layout/estilo` — a página headless do quadro e a rota interna
  (token assinado + host de loopback) que lhe entrega o estilo com tokens de tile cunhados no ato.
* Esri `Export Web Map Task` / `Get Layout Templates Info Task` em `/rest/services/Impressao/GPServer`, para o
  widget Print de apps ArcGIS JS e do Portal: `Web_Map_as_JSON` → layout nosso → PDF/PNG síncrono, com a URL
  de saída servida por `/rest/services/Impressao/GPServer/saida/{sha256}?token=` (mesmo token de serviço)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from app import db, limites, objetos
from app.auth import escopos as esc
from app.auth import sessao as auth_sessao
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import item_ou_404
from app.erros import ErroAPI
from app.jobs import servico as jobs_servico
from app.jobs.contexto import sessao_de
from app.layout import compor as compor_mod
from app.layout import estilo_render
from app.layout import modelos as modelos_mod
from app.layout.geometria import dimensoes_papel
from app.layout.modelos import ErroLayout, validar
from app.layout.tarefas import CLASSE_SAIDA, LayoutExportarParametros, fontes_de, resolver_layout_e_mapa
from app.rotas_arquivos import _linha as _linha_arquivo

log = logging.getLogger("plat.layout")
router = APIRouter(tags=["layout"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
EXECUTAR = {"x-auth": "S/T", "x-privilegio": "jobs.executar"}
WEB = Path(__file__).resolve().parents[2] / "web"
PREFIXO_ESRI = "/rest/services/Impressao/GPServer"
ESCOPO_ESRI = "catalogo:ler"
UUID_PADRAO = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
HOSTS_INTERNOS = frozenset({"127.0.0.1", "::1", "localhost"})


def _erro_layout(e: ErroLayout) -> ErroAPI:
    return ErroAPI(422, "layout_invalido", str(e), {"campo": e.campo})


# ---------------------------------------------------------------- modelos
@router.get("/api/layouts/modelos", openapi_extra=LER)
def listar_modelos(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    padrao = [
        {
            "id": m["id"],
            "nome": m["nome"],
            "papel": m["papel"],
            "orientacao": m["orientacao"],
            "elementos": [e["tipo"] for e in m["elementos"]],
            "origem": "padrao",
        }
        for m in modelos_mod.MODELOS_PADRAO
    ]
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT id::text AS id, titulo, dados FROM plat.item WHERE tipo = 'layout' AND apagado_em IS NULL "
            "AND (dados->>'modelo')::boolean IS TRUE ORDER BY titulo LIMIT 200"
        )
        do_inquilino = [
            {
                "id": r["id"],
                "nome": r["titulo"],
                "papel": (r["dados"] or {}).get("papel"),
                "orientacao": (r["dados"] or {}).get("orientacao"),
                "elementos": [e.get("tipo") for e in ((r["dados"] or {}).get("elementos") or [])],
                "origem": "inquilino",
            }
            for r in cur.fetchall()
        ]
    dimensoes = {p: list(dimensoes_papel(p, "retrato")) for p in modelos_mod.PAPEIS}
    return {
        "padrao": padrao,
        "inquilino": do_inquilino,
        "papeis": sorted(dimensoes),
        "dimensoes_mm": dimensoes,
        "formatos": list(modelos_mod.FORMATOS_EXPORTACAO),
        "dpi": {"min": limites.LAYOUT_DPI_MIN, "max": limites.LAYOUT_DPI_MAX},
        "quadro_pixels_max": limites.LAYOUT_QUADRO_PIXELS_MAX,
    }


@router.get("/api/layouts/modelos/{id}", openapi_extra=LER)
def ler_modelo(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    m = modelos_mod.modelo_padrao(id)
    if m is None:
        with db.db(auth.contexto()) as cur:
            try:
                item = item_ou_404(cur, id)
            except ErroAPI:
                raise ErroAPI(404, "modelo_inexistente", "modelo de layout inexistente") from None
        if item.get("tipo") != "layout":
            raise ErroAPI(404, "modelo_inexistente", "o item não é um layout")
        m = dict(item.get("dados") or {})
        m["nome"] = item.get("titulo")
        m["id"] = item["id"]
    return m


# ---------------------------------------------------------------- validar / prévia / exportar
class LayoutCorpo(BaseModel):
    layout: dict | None = None
    layout_id: str | None = Field(default=None, pattern=UUID_PADRAO)
    mapa: dict | None = None
    mapa_id: str | None = Field(default=None, pattern=UUID_PADRAO)


class PreviaCorpo(LayoutCorpo):
    dpi: int = Field(default=48, ge=24, le=96)
    quadros: bool = Field(
        default=False, description="desenhar os quadros pelo motor de render (mais lento) ou como área cinza"
    )


class ExportarCorpo(LayoutCorpo):
    formato: str = Field(default="pdf", pattern="^(pdf|png|jpg|svg)$")
    dpi: int = Field(default=150, ge=72, le=300)
    nome: str | None = Field(default=None, max_length=120)
    prioridade: int = Field(default=5, ge=1, le=9)


def _tamanho_ok(corpo: BaseModel) -> None:
    if len(json.dumps(corpo.model_dump(exclude_none=True), ensure_ascii=False)) > limites.LAYOUT_INLINE_BYTES_MAX:
        raise ErroAPI(413, "layout_grande_demais", f"documento acima de {limites.LAYOUT_INLINE_BYTES_MAX // 1024} KB")


@router.post("/api/layouts/validar", openapi_extra=LER)
def validar_layout(corpo: LayoutCorpo, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    _tamanho_ok(corpo)
    if not corpo.layout:
        raise ErroAPI(422, "layout_invalido", "informe layout", {"campo": "layout"})
    try:
        doc = validar(corpo.layout)
    except ErroLayout as e:
        raise _erro_layout(e) from e
    largura, altura = dimensoes_papel(doc["papel"], doc["orientacao"])
    return {"layout": doc, "largura_mm": largura, "altura_mm": altura}


@router.post("/api/layouts/previa", openapi_extra=LER, responses={200: {"content": {"image/png": {}}}})
def previa(corpo: PreviaCorpo, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    _tamanho_ok(corpo)
    p = corpo.model_dump()
    with db.db(auth.contexto()) as cur:
        try:
            doc, mapa, nome = resolver_layout_e_mapa(cur, p)
        except ErroLayout as e:
            raise _erro_layout(e) from e
        cinza = (
            None
            if corpo.quadros
            else (lambda q, m, el: compor_mod.png_vazio(min(q.largura_px, 64), min(q.altura_px, 64)))
        )
        fontes = fontes_de(cur, auth.tenant_id, auth.usuario_id, render_quadro=cinza)
        try:
            comp = compor_mod.compor(doc, mapa, fontes, dpi=corpo.dpi, formato="png", nome=nome)
        except compor_mod.ErroComposicao as e:
            raise ErroAPI(422, "composicao_falhou", str(e)) from e
    return Response(
        content=comp.dados,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store",
            "X-Layout-Relatorio": json.dumps(comp.relatorio, ensure_ascii=True)[:4000],
        },
    )


@router.post("/api/layouts/exportar", status_code=201, openapi_extra=EXECUTAR)
def exportar(corpo: ExportarCorpo, request: Request, auth: Auth = autenticado("jobs.executar")):
    _tamanho_ok(corpo)
    p = corpo.model_dump()
    with db.db(auth.contexto()) as cur:
        try:
            doc, mapa, nome = resolver_layout_e_mapa(cur, p)  # valida agora: o erro sai aqui nomeado, não no job
        except ErroLayout as e:
            raise _erro_layout(e) from e
    params = LayoutExportarParametros(
        layout_id=corpo.layout_id,
        layout=doc if not corpo.layout_id else None,
        mapa_id=corpo.mapa_id,
        mapa=None if corpo.mapa_id else (corpo.mapa or mapa),
        formato=corpo.formato,
        dpi=corpo.dpi,
        nome=corpo.nome or doc.get("nome") or nome,
    ).model_dump(exclude_none=True)
    job = jobs_servico.criar(sessao_de(auth), "layout.exportar", params, corpo.prioridade)
    return {"job": job, "classe": CLASSE_SAIDA, "formato": corpo.formato, "dpi": corpo.dpi}


# ---------------------------------------------------------------- página headless e estilo por token
@router.get("/render/layout-mapa", include_in_schema=False, response_class=HTMLResponse)
def pagina_render_layout():
    caminho = WEB / "render_layout_mapa.html"
    return HTMLResponse(
        caminho.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"}
    )


@router.get(
    "/api/render/layout/estilo", include_in_schema=False, openapi_extra={"x-auth": "-", "x-privilegio": "interno"}
)
def estilo_do_quadro(request: Request, token: str):
    host = request.client.host if request.client else None
    if host not in HOSTS_INTERNOS:
        raise ErroAPI(403, "fora_do_host", "esta rota só responde a um chamador no mesmo host")
    payload = estilo_render.ler_token(token)
    if not payload:
        raise ErroAPI(401, "token_invalido", "token interno inválido ou expirado")
    ctx = estilo_render.contexto_do_payload(payload)
    mapa = {"base": payload.get("b") or "osm-guarulhos", "camadas": payload.get("c") or []}
    base = f"{request.url.scheme}://{request.url.netloc}"
    with db.db(ctx) as cur:
        estilo = estilo_render.estilo_para_mapa(cur, int(payload["t"]), int(payload["u"]), mapa, base)
    return estilo


# ---------------------------------------------------------------- Esri: Export Web Map Task / Get Layout Templates Info
def _autenticar_esri(request: Request):
    try:
        auth = auth_sessao.resolver(request)
    except ErroAPI:
        auth = None
    if auth is None:
        tok = request.query_params.get("token")
        if not tok:
            raise ErroAPI(
                401,
                "token_requerido",
                "informe token=<token de serviço plat> (protocolo Esri) ou Authorization: Bearer",
            )
        auth = auth_sessao._auth_de_token(request, tok)  # noqa: SLF001 — mesmo reuso de app/geocodificador/rotas_esri.py
        request.state.auth = auth
    esc.exigir_escopo(auth, ESCOPO_ESRI)
    return auth


async def _parametros_esri(request: Request) -> dict:
    p = dict(request.query_params)
    if request.method == "POST":
        ct = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in ct or "multipart/form-data" in ct:
            form = await request.form()
            p.update({k: str(v) for k, v in form.items()})
        elif "application/json" in ct:
            try:
                corpo = await request.json()
                if isinstance(corpo, dict):
                    p.update({k: (v if isinstance(v, str) else json.dumps(v)) for k, v in corpo.items()})
            except ValueError:
                pass
    return p


def _erro_esri(codigo: int, mensagem: str, detalhes: list[str] | None = None) -> dict:
    return {"error": {"code": codigo, "message": mensagem, "details": detalhes or []}}


def _para_4326(x: float, y: float, wkid: int) -> tuple[float, float]:
    if wkid in (4326, 4674, 4618):
        return x, y
    from pyproj import Transformer

    tr = Transformer.from_crs(f"EPSG:{3857 if wkid == 102100 else wkid}", "EPSG:4326", always_xy=True)
    return tr.transform(x, y)


RE_TILE = re.compile(r"/tiles/(d_[a-z0-9_]{1,60})/t_([0-9a-f]{16})/")
RE_PLAT_CAMADA = re.compile(r"/api/mapa/camadas/([0-9a-f-]{36})")


def web_map_para_layout(cur, wm: dict, modelo_id: str | None, relatorio: list[str]) -> tuple[dict, dict]:
    """Web_Map_as_JSON (spec Export Web Map) → (layout nosso, definição de mapa). O que não tem equivalente vai
    para `relatorio` — nunca some em silêncio."""
    m = modelos_mod.modelo_padrao(modelo_id or "a4-paisagem-legenda") or modelos_mod.modelo_padrao(
        "a4-paisagem-legenda"
    )
    assert m is not None
    opcoes = wm.get("mapOptions") or {}
    ext = opcoes.get("extent") or {}
    wkid = int(
        (
            (ext.get("spatialReference") or {}).get("latestWkid")
            or (ext.get("spatialReference") or {}).get("wkid")
            or 102100
        )
    )
    camadas: list[dict] = []
    for op in wm.get("operationalLayers") or []:
        url = str(op.get("url") or "")
        titulo = op.get("title") or op.get("id") or url
        cid = None
        mt = RE_TILE.search(url)
        if mt:
            cur.execute("SELECT item_id::text AS item_id FROM plat.item_da_tabela(%s)", ("c_" + mt.group(2),))
            r = cur.fetchone()
            cid = r["item_id"] if r else None
        mc = RE_PLAT_CAMADA.search(url)
        if mc and not cid:
            cid = mc.group(1)
        if cid:
            camadas.append(
                {
                    "camada_id": cid,
                    "opacidade": float(op.get("opacity", 1.0)),
                    "visivel": op.get("visibility", True) is not False,
                }
            )
        else:
            relatorio.append(
                f"camada '{titulo}' ({op.get('layerType') or 'tipo desconhecido'}) "
                "sem equivalente nosso: fora do quadro"
            )
    for e in m["elementos"]:
        if e["tipo"] == "mapa":
            if all(k in ext for k in ("xmin", "ymin", "xmax", "ymax")):
                o, s = _para_4326(float(ext["xmin"]), float(ext["ymin"]), wkid)
                le, n = _para_4326(float(ext["xmax"]), float(ext["ymax"]), wkid)
                e["modo"], e["extensao"] = "extensao", [o, s, le, n]
                if opcoes.get("scale"):
                    e["modo"], e["escala"], e["centro"] = "escala", float(opcoes["scale"]), [(o + le) / 2, (s + n) / 2]
                    e.pop("extensao", None)
            else:
                relatorio.append("mapOptions.extent ausente: quadro na extensão padrão do modelo")
                e["modo"], e["extensao"] = "extensao", [-46.70, -23.55, -46.40, -23.35]
            if opcoes.get("rotation"):
                e["rotacao"] = float(opcoes["rotation"])
    lo = wm.get("layoutOptions") or {}
    for e in m["elementos"]:
        if e["tipo"] == "titulo" and lo.get("titleText"):
            e["texto"] = str(lo["titleText"])
        if e["tipo"] == "texto" and lo.get("authorText") and "{autor}" in (e.get("texto") or ""):
            e["texto"] = e["texto"].replace("{autor}", str(lo["authorText"]))
        if e["tipo"] == "atribuicao" and lo.get("copyrightText"):
            e["texto_extra"] = str(lo["copyrightText"])
    for ct in lo.get("customTextElements") or []:
        if isinstance(ct, dict):
            for k, v in ct.items():
                for e in m["elementos"]:
                    if e["tipo"] in ("titulo", "texto") and f"{{{k}}}" in (e.get("texto") or ""):
                        e["texto"] = e["texto"].replace(f"{{{k}}}", str(v))
    if lo.get("scaleBarOptions", {}).get("metricUnit") if isinstance(lo.get("scaleBarOptions"), dict) else False:
        for e in m["elementos"]:
            if e["tipo"] == "escala":
                e["unidade"] = "km" if "kilometer" in str(lo["scaleBarOptions"]["metricUnit"]).lower() else "m"
    leg = (
        (lo.get("legendOptions") or {}).get("operationalLayers") if isinstance(lo.get("legendOptions"), dict) else None
    )
    if isinstance(leg, list) and leg:
        ids = {str(x.get("id")) for x in leg if isinstance(x, dict)}
        relatorio.append(
            f"legendOptions restringe a legenda a {len(ids)} camadas do web map "
            "(aproximado: a legenda nossa lista as camadas convertidas)"
        )
    if wm.get("baseMap"):
        relatorio.append("baseMap do web map substituído pelo mapa-base local (OpenStreetMap) — aproximado")
    mapa = {"titulo": lo.get("titleText") or "Mapa", "camadas": camadas, "base": "osm-guarulhos"}
    doc = validar({k: v for k, v in m.items() if k != "id"})
    return doc, mapa


@router.get(f"{PREFIXO_ESRI}", include_in_schema=False)
@router.get(f"{PREFIXO_ESRI}/", include_in_schema=False)
def info_servico_esri(request: Request):
    _autenticar_esri(request)
    return {
        "currentVersion": 11.4,
        "serviceDescription": "Impressão de layouts do plat (compatível com o Export Web Map Task)",
        "tasks": ["Export Web Map Task", "Get Layout Templates Info Task"],
        "executionType": "esriExecutionTypeSynchronous",
        "resultMapServerName": "",
        "maximumRecords": 1000,
    }


@router.get(f"{PREFIXO_ESRI}/Get Layout Templates Info Task", include_in_schema=False)
def info_tarefa_modelos(request: Request):
    _autenticar_esri(request)
    return {
        "name": "Get Layout Templates Info Task",
        "displayName": "Get Layout Templates Info Task",
        "category": "",
        "helpUrl": "",
        "executionType": "esriExecutionTypeSynchronous",
        "parameters": [
            {
                "name": "Output_JSON",
                "dataType": "GPString",
                "displayName": "Output JSON",
                "direction": "esriGPParameterDirectionOutput",
                "parameterType": "esriGPParameterTypeDerived",
            }
        ],
    }


@router.api_route(
    f"{PREFIXO_ESRI}/Get Layout Templates Info Task/execute", methods=["GET", "POST"], include_in_schema=False
)
async def executar_modelos(request: Request):
    _autenticar_esri(request)
    saida = [modelos_mod.para_dimensoes_esri(m) for m in modelos_mod.MODELOS_PADRAO]
    return {"results": [{"paramName": "Output_JSON", "dataType": "GPString", "value": saida}], "messages": []}


@router.get(f"{PREFIXO_ESRI}/Export Web Map Task", include_in_schema=False)
def info_tarefa_exportar(request: Request):
    _autenticar_esri(request)
    return {
        "name": "Export Web Map Task",
        "displayName": "Export Web Map Task",
        "category": "",
        "helpUrl": "",
        "executionType": "esriExecutionTypeSynchronous",
        "parameters": [
            {
                "name": "Web_Map_as_JSON",
                "dataType": "GPString",
                "displayName": "Web Map as JSON",
                "direction": "esriGPParameterDirectionInput",
                "parameterType": "esriGPParameterTypeRequired",
            },
            {
                "name": "Format",
                "dataType": "GPString",
                "displayName": "Format",
                "direction": "esriGPParameterDirectionInput",
                "parameterType": "esriGPParameterTypeOptional",
                "defaultValue": "PDF",
                "choiceList": ["PDF", "PNG32", "PNG8", "JPG", "SVG"],
            },
            {
                "name": "Layout_Template",
                "dataType": "GPString",
                "displayName": "Layout Template",
                "direction": "esriGPParameterDirectionInput",
                "parameterType": "esriGPParameterTypeOptional",
                "defaultValue": "a4-paisagem-legenda",
                "choiceList": [m["id"] for m in modelos_mod.MODELOS_PADRAO] + ["MAP_ONLY"],
            },
            {
                "name": "Output_File",
                "dataType": "GPDataFile",
                "displayName": "Output File",
                "direction": "esriGPParameterDirectionOutput",
                "parameterType": "esriGPParameterTypeDerived",
            },
        ],
    }


FORMATOS_ESRI = {
    "PDF": "pdf",
    "PNG32": "png",
    "PNG8": "png",
    "JPG": "jpg",
    "SVG": "svg",
    "GIF": "png",
    "EPS": "pdf",
    "SVGZ": "svg",
}


@router.api_route(f"{PREFIXO_ESRI}/Export Web Map Task/execute", methods=["GET", "POST"], include_in_schema=False)
async def executar_export_web_map(request: Request):
    auth = _autenticar_esri(request)
    p = await _parametros_esri(request)
    bruto = p.get("Web_Map_as_JSON")
    if not bruto:
        return _erro_esri(400, "Web_Map_as_JSON é obrigatório")
    try:
        wm = json.loads(bruto) if isinstance(bruto, str) else bruto
    except json.JSONDecodeError as e:
        return _erro_esri(400, "Web_Map_as_JSON inválido", [str(e)])
    formato = FORMATOS_ESRI.get(str(p.get("Format") or "PDF").upper())
    if formato is None:
        return _erro_esri(400, f"Format não suportado: {p.get('Format')}", [f"aceitos: {sorted(FORMATOS_ESRI)}"])
    modelo = p.get("Layout_Template") or "a4-paisagem-legenda"
    if modelo == "MAP_ONLY":
        modelo = "a4-paisagem-legenda"
    dpi = int(((wm.get("exportOptions") or {}).get("dpi")) or 96)
    dpi = max(limites.LAYOUT_DPI_MIN, min(limites.LAYOUT_DPI_MAX, dpi))
    relatorio: list[str] = []
    with db.db(auth.contexto()) as cur:
        try:
            doc, mapa = web_map_para_layout(cur, wm, modelo, relatorio)
        except ErroLayout as e:
            return _erro_esri(400, f"web map não pôde virar layout: {e}")
        fontes = fontes_de(cur, auth.tenant_id, auth.usuario_id)
        try:
            comp = compor_mod.compor(doc, mapa, fontes, dpi=dpi, formato=formato, nome="impressao")
        except compor_mod.ErroComposicao as e:
            return _erro_esri(500, f"composição falhou: {e}")
        o = objetos.guardar(cur, CLASSE_SAIDA, comp.dados, comp.content_type, usuario_id=auth.usuario_id)
    base = f"{request.url.scheme}://{request.url.netloc}"
    url = f"{base}{PREFIXO_ESRI}/saida/{o['sha256']}.{formato}"
    if request.query_params.get("token"):
        url += f"?token={request.query_params['token']}"
    mensagens = [
        {"type": "esriJobMessageTypeWarning", "description": a}
        for a in relatorio + (comp.relatorio.get("avisos") or [])
    ]
    return {
        "results": [{"paramName": "Output_File", "dataType": "GPDataFile", "value": {"url": url}}],
        "messages": mensagens,
    }


@router.get(f"{PREFIXO_ESRI}/saida/{{nome}}", include_in_schema=False)
def baixar_saida_esri(nome: str, request: Request):
    auth = _autenticar_esri(request)
    sha = nome.split(".")[0]
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ErroAPI(404, "objeto_inexistente", "objeto inexistente")
    with db.db(auth.contexto()) as cur:
        r = _linha_arquivo(cur, auth.tenant_id, CLASSE_SAIDA, sha)
    if r is None:
        raise ErroAPI(404, "objeto_inexistente", "objeto inexistente")
    try:
        dados = objetos.ler(r["chave"])
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise ErroAPI(404, "objeto_inexistente", "objeto inexistente") from e
    return Response(
        dados,
        media_type=r["content_type"],
        headers={
            "Cache-Control": "private, max-age=60",
            "X-Robots-Tag": "noindex, nofollow",
            "Content-Disposition": f'inline; filename="{nome}"',
        },
    )
