"""Job `layout.exportar` (item L2-12-b-layouts-elementos-exportacao): compõe um layout em PDF/PNG/JPG/SVG no worker
e guarda o arquivo como objeto do inquilino (classe `layout_exportacao`, L0-11) — o resultado do job traz o sha256 e
a URL de download (`GET /api/arquivos/{sha256}?classe=layout_exportacao`, sob a sessão de quem pediu).

O quadro de mapa é desenhado pelo motor de render do L2-12-a rodando NESTE processo do worker (pool de chromium
próprio, nasce no primeiro uso e morre com o processo); a página headless recebe um token interno assinado com o
inquilino/usuário do job (`app/layout/estilo_render.py`). O documento de layout pode vir por `layout_id` (item do
catálogo) ou inline (`layout`, o formulário do painel antes de gravar); o mapa idem (`mapa_id` ou `mapa`)."""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from app import objetos
from app.catalogo.comum import item_ou_404
from app.erros import ErroAPI
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.layout import compor as compor_mod
from app.layout import estilo_render
from app.layout.modelos import FORMATOS_EXPORTACAO, ErroLayout, validar
from app.rotas_arquivos import _linha as _linha_arquivo

UUID_PADRAO = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
CLASSE_SAIDA = "layout_exportacao"


class LayoutExportarParametros(BaseModel):
    layout_id: str | None = Field(default=None, pattern=UUID_PADRAO, description="item `layout` do catálogo")
    layout: dict | None = Field(default=None, description="documento de layout inline (quando ainda não foi gravado)")
    mapa_id: str | None = Field(
        default=None, pattern=UUID_PADRAO, description="item `mapa` cujas camadas entram no quadro"
    )
    mapa: dict | None = Field(
        default=None, description="definição de mapa inline: {camadas:[{camada_id, opacidade}], base, titulo}"
    )
    formato: str = Field(default="pdf", pattern="^(pdf|png|jpg|svg)$")
    dpi: int = Field(default=150, ge=72, le=300)
    nome: str | None = Field(default=None, max_length=120)


def fontes_de(cur, tenant_id: int, usuario_id: int, render_quadro=None) -> compor_mod.Fontes:
    """Liga o compositor ao banco (fichas, logotipo, imagens, tabela) e ao motor de render."""
    cur.execute("SELECT nome, config FROM plat.tenant WHERE id = %s", (tenant_id,))
    t = cur.fetchone() or {}
    cur.execute("SELECT nome FROM plat.usuario WHERE id = %s", (usuario_id,))
    u = cur.fetchone() or {}
    config = t.get("config") or {}

    def logo_png():
        sha = config.get("logo")
        if not sha:
            return None
        r = _linha_arquivo(cur, tenant_id, "org_logo", sha)
        if r is None:
            return None
        try:
            return objetos.ler(r["chave"])
        except (FileNotFoundError, objetos.ChaveInvalida):
            return None

    def imagem_por_sha(sha, classe):
        if not sha or len(sha) != 64:
            return None
        r = _linha_arquivo(cur, tenant_id, classe, sha)
        if r is None:
            return None
        try:
            return objetos.ler(r["chave"]), r["content_type"]
        except (FileNotFoundError, objetos.ChaveInvalida):
            return None

    def linhas_tabela(el):
        camada_id = el.get("camada_id")
        ids = None
        if el.get("selecao_id"):
            try:
                sel = item_ou_404(cur, el["selecao_id"])
            except ErroAPI:
                return [], []
            d = sel.get("dados") or {}
            camada_id = camada_id or d.get("camada_id")
            ids = [v for v in (d.get("ids") or []) if isinstance(v, (int, str))][: el.get("linhas_max", 20) * 5]
        if not camada_id:
            return [], []
        ficha = estilo_render.ficha_camada(cur, str(camada_id))
        if not ficha or not ficha.get("esquema") or not (ficha["dados"].get("tabela")):
            return [], []
        campos = [c["nome"] for c in (ficha["dados"].get("campos") or []) if isinstance(c, dict) and c.get("nome")]
        pedidos = [c for c in (el.get("campos") or campos) if c in campos][:12]
        if not pedidos:
            return [], []
        colunas_sql = ", ".join(f'"{c}"' for c in pedidos)
        tabela_sql = f'"{ficha["esquema"]}"."{ficha["dados"]["tabela"]}"'
        limite = int(el.get("linhas_max", 20))
        if ids:
            ids_int = [int(v) for v in ids if str(v).isdigit()]
            cur.execute(
                f"SELECT {colunas_sql} FROM {tabela_sql} WHERE fid = ANY(%s) ORDER BY fid LIMIT %s", (ids_int, limite)
            )
        else:
            cur.execute(f"SELECT {colunas_sql} FROM {tabela_sql} ORDER BY fid LIMIT %s", (limite,))
        return pedidos, [[r[c] for c in pedidos] for r in cur.fetchall()]

    def render(quadro, mapa, elemento):
        if render_quadro is not None:
            return render_quadro(quadro, mapa, elemento)
        return estilo_render.render_quadro(quadro, mapa, elemento, tenant_id, usuario_id)

    return compor_mod.Fontes(
        ficha_camada=lambda cid: estilo_render.ficha_camada(cur, cid),
        render_quadro=render,
        logo_png=logo_png,
        imagem_por_sha=imagem_por_sha,
        linhas_tabela=linhas_tabela,
        inquilino_nome=t.get("nome") or "",
        autor=u.get("nome") or "",
    )


def resolver_layout_e_mapa(cur, p: dict[str, Any]) -> tuple[dict, dict, str]:
    """(layout validado, definição de mapa, nome do arquivo) a partir dos parâmetros; erros nomeados."""
    if p.get("layout_id"):
        item = item_ou_404(cur, p["layout_id"])
        if item.get("tipo") != "layout":
            raise ErroLayout("o item indicado não é um layout", "layout_id")
        doc = item.get("dados") or {}
        nome = p.get("nome") or item.get("titulo") or "layout"
    elif p.get("layout"):
        doc = p["layout"]
        nome = p.get("nome") or doc.get("nome") or "layout"
    else:
        raise ErroLayout("informe layout_id ou layout", "layout")
    layout = validar(doc)
    if p.get("mapa_id"):
        mapa = compor_mod.mapa_de_item(item_ou_404(cur, p["mapa_id"]))
    elif p.get("mapa"):
        m = p["mapa"] or {}
        mapa = {"titulo": m.get("titulo"), "camadas": m.get("camadas") or [], "base": m.get("base") or "osm-guarulhos"}
    elif layout.get("mapa_id"):
        mapa = compor_mod.mapa_de_item(item_ou_404(cur, layout["mapa_id"]))
    else:
        mapa = {"titulo": layout.get("nome"), "camadas": [], "base": "osm-guarulhos"}
    return layout, mapa, "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(nome))[:80] or "layout"


@tarefa(
    nome="layout.exportar",
    descricao="Exporta um layout (papel, quadro de mapa, legenda, escala, norte, grade, "
    "texto) em PDF, PNG, JPG ou SVG e guarda o arquivo como objeto do inquilino",
    parametros=LayoutExportarParametros,
    pesado=False,
    memoria_mb=1024,
    timeout_s=900,
    tentativas=1,
    perfil_minimo="visualizador",
    versao=1,
)
def layout_exportar(
    ctx, layout_id=None, layout=None, mapa_id=None, mapa=None, formato="pdf", dpi=150, nome=None
) -> dict:
    if formato not in FORMATOS_EXPORTACAO:
        raise FalhaDefinitiva(f"formato não suportado: {formato}")
    p = {"layout_id": layout_id, "layout": layout, "mapa_id": mapa_id, "mapa": mapa, "nome": nome}
    inicio = time.perf_counter()
    with ctx.db() as cur:
        try:
            doc, mapa_def, nome_arq = resolver_layout_e_mapa(cur, p)
        except ErroLayout as e:
            raise FalhaDefinitiva(f"layout inválido ({e.campo}): {e}") from e
        except ErroAPI as e:
            raise FalhaDefinitiva(f"{e.erro}: {e.mensagem}") from e
        ctx.log(
            "INFO",
            f"layout {doc['papel']} {doc['orientacao']}, {len(doc['elementos'])} elementos, "
            f"{len(mapa_def.get('camadas') or [])} camadas, {formato} a {dpi} DPI",
        )
        ctx.progresso(5, "resolvendo quadro e camadas")
        fontes = fontes_de(cur, ctx.tenant_id, ctx.usuario_id or 0)
        comp = compor_mod.compor(doc, mapa_def, fontes, dpi=dpi, formato=formato, nome=nome_arq)
        ctx.progresso(85, "arquivo composto; guardando")
        o = objetos.guardar(cur, CLASSE_SAIDA, comp.dados, comp.content_type, usuario_id=ctx.usuario_id)
    ms = round((time.perf_counter() - inicio) * 1000)
    for a in comp.relatorio.get("avisos") or []:
        ctx.log("AVISO", a)
    ctx.log("INFO", f"{comp.nome_arquivo}: {o['bytes']} bytes em {ms} ms")
    return {
        "sha256": o["sha256"],
        "bytes": o["bytes"],
        "content_type": comp.content_type,
        "nome_arquivo": comp.nome_arquivo,
        "classe": CLASSE_SAIDA,
        "url": f"/api/arquivos/{o['sha256']}?classe={CLASSE_SAIDA}",
        "relatorio": comp.relatorio,
        "ms": ms,
    }
