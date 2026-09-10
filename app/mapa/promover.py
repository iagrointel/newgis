""""Promover a camada" (item L2-01-k-desenho-anotacoes): transforma um conjunto de feições da camada de
desenho local (`corpo.desenho`, GeoJSON + estilo, sem tabela — ver `app/catalogo/documento.py`) numa camada
hospedada de verdade, do mesmo jeito que o resto da casa hospeda camada (`plat.camada_schema_garantir` +
`plat.camada_preparar`, migração 029, e a mesma convenção de nome de tabela do L0-04: `tabela_de(item_id)`).

Por que não o job `ingestao.carregar` (ADR 0005): aquele caminho existe para ARQUIVO (upload → objeto → fila →
`ogr2ogr`), com fila e "neto" isolado por RLIMIT porque o arquivo pode ter qualquer tamanho. Um desenho tem no
máximo `DESENHO_FEATURES_MAX` (5.000) feições que JÁ estão em memória como JSON — gerar um arquivo, subir para
o objeto e reler pelo `ogr2ogr` seria voltar e ir sem necessidade (degrau 1 do PONYTAIL: "precisa mesmo
construir?"). Aqui o INSERT é direto, síncrono, na mesma transação, e reusa os DOIS primitivos de banco que o
L0-04 já expõe para o resto virar tabela de verdade (schema por inquilino e DDL/RLS/índice pós-carga).
"""

from __future__ import annotations

import json
import uuid as uuid_mod

import psycopg2.extras
from fastapi import APIRouter, Body, Request
from pydantic import BaseModel, Field

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import item_ou_404, jsonb, registrar_evento
from app.erros import ErroAPI
from app.ingestao.inspecionar import tabela_de

router = APIRouter(tags=["mapa"])
X = {"x-auth": "S/T", "x-privilegio": "conteudo.publicar_camada"}

_CAMPOS_PROMOVIDOS = [
    {"nome": "tipo_desenho", "tipo": "text"},
    {"nome": "rotulo", "tipo": "text"},
    {"nome": "texto", "tipo": "text"},
    {"nome": "raio_m", "tipo": "double precision"},
    {"nome": "estilo", "tipo": "jsonb"},
    {"nome": "origem_feature_id", "tipo": "text"},
]


class PromoverEntrada(BaseModel):
    titulo: str = Field(min_length=1, max_length=250)
    ids: list[str] | None = None  # subconjunto de corpo.desenho.features[].id; None = todas


def _geometria_da_selecao(features: list[dict]) -> str:
    tipos_geo = set()
    for f in features:
        tipos_geo.add((f.get("geometry") or {}).get("type"))
    tipos_geo.discard(None)
    return tipos_geo.pop() if len(tipos_geo) == 1 else "Geometry"


@router.post("/api/mapa/{mapa_id}/desenho/promover", status_code=201, openapi_extra=X)
def promover(
    mapa_id: str,
    request: Request,
    entrada: PromoverEntrada = Body(...),  # noqa: B008
    auth: Auth = autenticado("conteudo.publicar_camada"),
):
    with db.db(auth.contexto()) as cur:
        item_mapa = item_ou_404(cur, mapa_id)
        if item_mapa["tipo"] not in ("mapa", "cena"):
            raise ErroAPI(422, "tipo_invalido", "só um documento de mapa/cena tem camada de desenho a promover")
        desenho = ((item_mapa["dados"] or {}).get("corpo") or {}).get("desenho") or {}
        todas = [f for f in (desenho.get("features") or []) if isinstance(f, dict)]
        if entrada.ids is not None:
            quero = set(entrada.ids)
            selecionadas = [f for f in todas if f.get("id") in quero]
            faltando = quero - {f.get("id") for f in selecionadas}
            if faltando:
                raise ErroAPI(404, "feicao_inexistente",
                              "feição de desenho inexistente neste documento", sorted(faltando))
        else:
            selecionadas = todas
        if not selecionadas:
            raise ErroAPI(422, "nada_para_promover", "nenhuma feição de desenho para promover")

        cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (auth.tenant_id,))
        slug = cur.fetchone()["slug"]
        item_id = str(uuid_mod.uuid4())
        tabela = tabela_de(item_id)
        schema = f"d_{slug}"
        geometria = _geometria_da_selecao(selecionadas)

        cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
        cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{tabela}" CASCADE')
        cur.execute(
            f'CREATE TABLE "{schema}"."{tabela}" (fid bigserial PRIMARY KEY, '
            f'geom geometry(Geometry, 4326) NOT NULL, '
            + ", ".join(f'{c["nome"]} {c["tipo"]}' for c in _CAMPOS_PROMOVIDOS)
            + ")"
        )
        linhas_inseridas = 0
        for f in selecionadas:
            props = f.get("properties") if isinstance(f.get("properties"), dict) else {}
            cur.execute(
                f'INSERT INTO "{schema}"."{tabela}" '
                f"(geom, tipo_desenho, rotulo, texto, raio_m, estilo, origem_feature_id) "
                f"VALUES (ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s, %s, %s, %s, %s, %s)",
                (
                    json.dumps(f.get("geometry")),
                    props.get("tipo_desenho"),
                    props.get("rotulo"),
                    props.get("texto"),
                    props.get("raio_m"),
                    psycopg2.extras.Json(props.get("estilo") or {}),
                    f.get("id"),
                ),
            )
            linhas_inseridas += 1

        cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                    (schema, tabela, 4326, geometria, auth.usuario_id))
        cur.execute(f'SELECT count(*) FILTER (WHERE NOT ST_IsValid(geom)) AS invalidas, count(*) AS n '
                    f'FROM "{schema}"."{tabela}"')
        conferido = cur.fetchone()
        if conferido["invalidas"]:
            cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{tabela}" CASCADE')
            raise ErroAPI(
                422, "geometria_invalida",
                f"{conferido['invalidas']} de {conferido['n']} geometrias continuaram inválidas após ST_MakeValid",
            )

        campos_item = [{"nome": "fid", "tipo": "bigint", "alias": "id"}, *_CAMPOS_PROMOVIDOS]
        dados_camada = {
            "schema": schema,
            "tabela": tabela,
            "geometria": geometria,
            "srid": 4326,
            "campos": campos_item,
            "fonte": "hospedada",
            "procedencia": {
                "origem": "desenho_promovido",
                "mapa_id": mapa_id,
                "promovido_por": auth.usuario_id,
                "n_feicoes": linhas_inseridas,
            },
        }
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dados, dono_id, criado_por, modificado_por) "
            "VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, %s, %s)",
            (item_id, auth.tenant_id, entrada.titulo.strip(), jsonb(dados_camada),
             auth.usuario_id, auth.usuario_id, auth.usuario_id),
        )
        registrar_evento(
            cur, request, "mapa/desenho_promovido", "item", item_id,
            {"mapa_id": mapa_id, "n_feicoes": linhas_inseridas, "tabela": tabela},
        )
        return {
            "camada_id": item_id,
            "schema": schema,
            "tabela": tabela,
            "n_feicoes": linhas_inseridas,
            "geometria": geometria,
            "todas_validas": conferido["invalidas"] == 0,
        }
