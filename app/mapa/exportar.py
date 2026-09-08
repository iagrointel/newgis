"""Exportação a partir do mapa que NÃO passa por arquivo de camada (item L2-01-l).

Três coisas que o usuário faz na tela do mapa e que não são "gerar um arquivo de dado":

    GET /api/mapa/camadas/{id}/feicoes/{fid}?formato=geojson|wkt   copiar a feição (área de transferência)
    GET /api/mapa/camadas/{id}/estilo?formato=maplibre|sld         o estilo da camada, nos dois formatos
    POST /api/mapa/pacotes/importar                                reimportar um pacote de mapa

A geração do arquivo de dado (12 formatos, seleção/filtro/camada inteira) e a geração do PACOTE são job
(`POST /api/exportacoes`, `app/exportacao/`), com link de validade de 7 dias — aqui ficam só as respostas
que cabem numa requisição.

Por que a cópia de feição é uma rota e não trabalho do navegador: o mapa desenha TILE (geometria já
recortada e generalizada por zoom, item L2-01-b). Copiar o que está no tile devolveria uma geometria
cortada na borda do tile — o que se copia tem de vir da tabela. `ST_AsGeoJSON`/`ST_AsText` do PostGIS
fazem a conversão; a rota nunca monta a geometria em Python.

O import do pacote é síncrono de propósito, com teto de tamanho (`limites.PACOTE_IMPORTAR_MAX_BYTES`):
é a operação inversa do job de exportação e roda `ogr2ogr` uma vez por camada do GeoPackage. Pacote
maior que o teto é 413, nunca uma requisição que segura um trabalhador por minutos.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app import db, limites
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import jsonb, registrar_evento
from app.erros import ErroAPI
from app.exportacao import motor
from app.mapa import simbologia as simb_mod
from app.mapa import sld as sld_mod
from app.mapa.pacote import (
    ErroPacote,
    ler_manifesto,
)
from app.mapa.rotas import SQL_CAMADA

router = APIRouter(tags=["mapa", "exportacao"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}
IMPORTAR = {"x-auth": "S/T", "x-privilegio": "conteudo.criar"}
FORMATOS_FEICAO = ("geojson", "wkt")
FORMATOS_ESTILO = ("maplibre", "sld")


def _camada_ou_404(cur, id: str) -> dict:
    cur.execute(SQL_CAMADA + " AND i.id = %s::uuid", (id,))
    linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(404, "camada_inexistente", "camada inexistente ou sem permissão de leitura")
    return linha


@router.get("/api/mapa/camadas/{id}/feicoes/{fid}", openapi_extra=X)
def copiar_feicao(id: str, fid: int, formato: str = "geojson",
                  auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """A feição inteira (geometria da TABELA, não do tile) como texto para a área de transferência."""
    if formato not in FORMATOS_FEICAO:
        raise ErroAPI(422, "formato_invalido", f"formato precisa ser um de {list(FORMATOS_FEICAO)}")
    with db.db(auth.contexto()) as cur:
        linha = _camada_ou_404(cur, id)
        dados = linha["dados"] or {}
        esquema, tabela = dados.get("schema"), dados.get("tabela")
        if not (esquema and tabela and motor.where_ast.IDENT_RE.match(esquema)
                and motor.where_ast.IDENT_RE.match(tabela)):
            raise ErroAPI(422, "camada_sem_tabela", "esta camada não é hospedada: não há feição a copiar")
        campos = [c["nome"] for c in (dados.get("campos") or [])
                  if isinstance(c, dict) and motor.where_ast.IDENT_RE.match(str(c.get("nome") or ""))]
        propriedades = ", ".join("'%s', t.\"%s\"" % (c, c) for c in campos) or "'fid', t.fid"
        if formato == "wkt":
            cur.execute(f'SELECT ST_AsText(ST_Transform(t.geom, 4326)) AS texto FROM "{esquema}"."{tabela}" t '
                        "WHERE t.fid = %s", (fid,))
        else:
            cur.execute(
                "SELECT json_build_object('type','Feature','id', t.fid, "
                "'geometry', ST_AsGeoJSON(ST_Transform(t.geom, 4326))::json, "
                f"'properties', json_build_object({propriedades}))::text AS texto "
                f'FROM "{esquema}"."{tabela}" t WHERE t.fid = %s', (fid,),
            )
        r = cur.fetchone()
    if r is None or r["texto"] is None:
        raise ErroAPI(404, "feicao_inexistente", "feição inexistente nesta camada")
    return {"camada_id": id, "fid": fid, "formato": formato, "crs": "EPSG:4326", "texto": r["texto"]}


@router.get("/api/mapa/camadas/{id}/estilo", openapi_extra=X,
            responses={200: {"content": {"application/json": {}, "application/vnd.ogc.sld+xml": {}}}})
def estilo(id: str, formato: str = "maplibre", auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """`maplibre` devolve as camadas de estilo da Style Spec; `sld` devolve SLD 1.0.0 (mesmas classes)."""
    if formato not in FORMATOS_ESTILO:
        raise ErroAPI(422, "formato_invalido", f"formato precisa ser um de {list(FORMATOS_ESTILO)}")
    with db.db(auth.contexto()) as cur:
        linha = _camada_ou_404(cur, id)
    dados = linha["dados"] or {}
    geometria = dados.get("geometria") or "Point"
    simb = simb_mod.normalizar(dados.get("simbologia"), geometria)
    tabela = dados.get("tabela") or ""
    funcao = ("t_" + tabela[2:]) if tabela.startswith("c_") else "camada"
    if formato == "sld":
        texto = sld_mod.gerar(simb, geometria, nome=str(linha["id"]), titulo=linha["titulo"] or "")
        return Response(content=texto, media_type="application/vnd.ogc.sld+xml",
                        headers={"Content-Disposition": f'attachment; filename="estilo-{linha["id"]}.sld"'})
    fonte = f"plat-{linha['id']}"
    return {"camada_id": str(linha["id"]), "titulo": linha["titulo"], "simbologia": simb,
            "legenda": simb_mod.legenda(simb, geometria),
            "camadas": simb_mod.camadas_maplibre(simb, geometria, fonte, fonte, funcao),
            "sld": f"/api/mapa/camadas/{linha['id']}/estilo?formato=sld"}


# ------------------------------------------------------------------ importação do pacote de mapa
@router.post("/api/mapa/pacotes/importar", status_code=201, openapi_extra=IMPORTAR)
async def importar_pacote(request: Request, auth: Auth = autenticado("conteudo.criar")):
    """Recria, NESTE inquilino, o mapa que outro pacote levou: as camadas do GeoPackage viram tabelas
    novas do inquilino, cada uma com a sua simbologia, e o documento de mapa volta a apontar para elas.

    O corpo é o zip CRU (`application/zip`), não multipart: é o mesmo caminho de `app/uploads/rotas.py`
    e de `app/rotas_arquivos.py` nesta casa, e evita uma dependência nova só para envelopar um arquivo
    (o `python-multipart` não está instalado, e o brief proíbe mexer no venv compartilhado por isto)."""
    with tempfile.TemporaryDirectory(prefix="plat-pacote-") as tmp:
        destino = Path(tmp) / "pacote.zip"
        lidos = 0
        with destino.open("wb") as saida:
            async for bloco in request.stream():
                lidos += len(bloco)
                if lidos > limites.PACOTE_IMPORTAR_MAX_BYTES:
                    raise ErroAPI(413, "pacote_grande",
                                  f"pacote acima de {limites.PACOTE_IMPORTAR_MAX_BYTES // (1024 * 1024)} MB; "
                                  "importe pela ingestão de camada")
                saida.write(bloco)
        if lidos == 0:
            raise ErroAPI(422, "pacote_vazio", "corpo vazio: envie o zip do pacote como corpo da requisição")
        try:
            manifesto = ler_manifesto(destino)
        except ErroPacote as e:
            raise ErroAPI(422, "pacote_invalido", str(e)) from e
        with zipfile.ZipFile(destino) as z:
            gpkg = Path(tmp) / "dados.gpkg"
            with z.open("dados.gpkg") as origem, gpkg.open("wb") as saida:
                while bloco := origem.read(1024 * 1024):
                    saida.write(bloco)
        return _recriar(request, auth, manifesto, gpkg)


def _recriar(request: Request, auth: Auth, manifesto: dict, gpkg: Path) -> dict:
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (auth.tenant_id,))
        linha = cur.fetchone()
        if linha is None:
            raise ErroAPI(403, "inquilino_desconhecido", "inquilino sem schema de dado")
        slug = linha["slug"]
        cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
    esquema = f"d_{slug}"
    novas: list[dict] = []
    for camada in manifesto["camadas"]:
        tabela = "c_" + uuid.uuid4().hex[:16]
        argv = ["ogr2ogr", "-f", "PostgreSQL", motor.conninfo_pg(auth.tenant_id, auth.usuario_id),
                str(gpkg), camada["tabela_no_pacote"], "-nln", f"{esquema}.{tabela}",
                "-lco", "GEOMETRY_NAME=geom", "-lco", "FID=fid", "-lco", "SPATIAL_INDEX=NONE",
                "-nlt", camada.get("geometria") or "GEOMETRY"]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=limites.PACOTE_OGR_TIMEOUT_S)
        if r.returncode != 0:
            detalhe = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
            raise ErroAPI(422, "pacote_camada_invalida",
                          f"não foi possível carregar a camada {camada['titulo']!r}: "
                          f"{(detalhe[-1] if detalhe else 'sem detalhe')[:300]}")
        with db.db(auth.contexto()) as cur:
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                        (esquema, tabela, int(camada.get("srid") or 4326),
                         camada.get("geometria") or "Geometry", auth.usuario_id))
            dados = {"schema": esquema, "tabela": tabela, "fonte": "hospedada",
                     "geometria": camada.get("geometria") or "Geometry",
                     "srid": int(camada.get("srid") or 4326), "campos": camada.get("campos") or [],
                     "simbologia": camada.get("simbologia"),
                     "proveniencia": {"pacote": manifesto.get("gerado_em"),
                                      "mapa_de_origem": manifesto["mapa"].get("titulo")}}
            cur.execute(
                "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, dados, criado_por, modificado_por) "
                "VALUES (%s, 'camada_vetorial', %s, %s, %s, %s, %s) RETURNING id",
                (auth.tenant_id, camada["titulo"][:250], auth.usuario_id, jsonb(dados),
                 auth.usuario_id, auth.usuario_id),
            )
            novas.append({"id": str(cur.fetchone()["id"]), "titulo": camada["titulo"],
                          "id_no_pacote": camada["id_no_pacote"], "tabela": tabela})
    de_para = {c["id_no_pacote"]: c["id"] for c in novas}
    corpo = json.loads(json.dumps(manifesto["mapa"].get("corpo") or {}))
    for c in corpo.get("camadas") or []:
        if c.get("camada_id") in de_para:
            c["camada_id"] = de_para[c["camada_id"]]
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, descricao, dados, criado_por, "
            "modificado_por) VALUES (%s, 'mapa', %s, %s, %s, %s, %s, %s) RETURNING id",
            (auth.tenant_id, (manifesto["mapa"].get("titulo") or "Mapa importado")[:250], auth.usuario_id,
             manifesto["mapa"].get("descricao"), jsonb({"esquema_versao": 1, "corpo": corpo}),
             auth.usuario_id, auth.usuario_id),
        )
        mapa_id = str(cur.fetchone()["id"])
        registrar_evento(cur, request, "mapas/importar_pacote", "item", mapa_id,
                         {"camadas": len(novas)})
    return {"mapa_id": mapa_id, "camadas": novas, "titulo": manifesto["mapa"].get("titulo")}
