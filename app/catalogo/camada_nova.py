"""Cria uma camada vetorial hospedada a partir de uma LISTA DE CAMPOS (sem arquivo): tabela `d_<slug>.c_<uuid16>`
com o mesmo preparo da ingestão (`plat.camada_preparar`: globalid, versao, tenant_id, rastreio, RLS FORCE,
índices, gatilhos) e o item `camada_vetorial` no catálogo com o mesmo `dados` que `app/ingestao/carregar.py`
grava. Usado pelo formulário de coleta (L2-07-b: camada de destino e camada filha de repetição) e pela clonagem
de camadas hospedadas (L2-08-b). Deve rodar dentro de um contexto de inquilino (`db.db(ctx)`).

ponytail: a coluna `geom` existe sempre, mesmo em tabela só de atributos — `plat.camada_preparar` cria o índice
GiST sem condição, e uma coluna nula custa menos que uma segunda função de preparo."""

from __future__ import annotations

import json
import uuid

import psycopg2.extras

from app.erros import ErroAPI
from app.ingestao import nomes
from app.ingestao.inspecionar import tabela_de

TIPOS_PG = frozenset({
    "text", "integer", "bigint", "smallint", "double precision", "real", "numeric", "boolean",
    "date", "time", "timestamptz", "uuid",
})
GEOMETRIAS = ("Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon", "Geometry",
              "PointZ", "MultiPointZ", "LineStringZ", "MultiLineStringZ", "PolygonZ", "MultiPolygonZ")


def _jsonb(valor):
    return psycopg2.extras.Json(valor, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str))


def tenant_atual(cur) -> tuple[int, str]:
    cur.execute("SELECT id, slug FROM plat.tenant WHERE id = plat.tenant_atual()")
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(409, "sem_inquilino", "contexto de inquilino ausente")
    return int(r["id"]), r["slug"]


def normalizar_campos(campos: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """Sanea nomes na ordem dada (minúsculo, sem acento, <= 63 bytes, reservados com sufixo, duplicados com
    _2/_3) e devolve (campos com `nome` final, mapa original -> nome final). `tipo` tem de ser um de TIPOS_PG."""
    usados: set[str] = set()
    saida, mapa = [], {}
    for posicao, c in enumerate(campos):
        if c.get("tipo") not in TIPOS_PG:
            raise ErroAPI(422, "tipo_de_campo_invalido", f"tipo de campo fora da lista: {c.get('tipo')!r}",
                          {"campo": c.get("nome"), "tipo": c.get("tipo")})
        nome, _motivo = nomes.normalizar(str(c.get("nome") or ""), usados, posicao=posicao)
        mapa[str(c.get("nome") or "")] = nome
        campo = {"nome": nome, "tipo": c["tipo"], "alias": c.get("alias") or c.get("nome") or nome}
        for extra in ("tamanho", "nulavel", "padrao"):
            if c.get(extra) is not None:
                campo[extra] = c[extra]
        saida.append(campo)
    return saida, mapa


def criar_camada(
    cur, usuario_id: int, titulo: str, campos: list[dict], *, geometria: str = "Point", srid: int = 4326,
    regras_campo: dict | None = None, extra_dados: dict | None = None, edicao_habilitada: bool = True,
) -> tuple[str, dict]:
    """Devolve (item_id, dados do item). `campos`: [{nome, tipo, alias?, tamanho?, nulavel?, padrao?}]."""
    if geometria not in GEOMETRIAS:
        raise ErroAPI(422, "geometria_invalida", f"tipo de geometria fora da lista: {geometria!r}")
    tenant_id, slug = tenant_atual(cur)
    campos_ok, mapa = normalizar_campos(campos)
    item_id = str(uuid.uuid4())
    schema, tabela = f"d_{slug}", tabela_de(item_id)
    cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
    colunas = "".join(
        f', "{c["nome"]}" {c["tipo"]}' + ("" if c.get("nulavel", True) else " NOT NULL") for c in campos_ok
    )
    cur.execute(f'CREATE TABLE "{schema}"."{tabela}" (fid bigserial PRIMARY KEY, '
                f'geom geometry({geometria}, {int(srid)}){colunas})')
    cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)", (schema, tabela, int(srid), geometria, usuario_id))
    dados = {
        "schema": schema, "tabela": tabela, "geometria": geometria, "srid": int(srid),
        "campos": campos_ok, "fonte": "hospedada",
        "edicao": {"habilitada": bool(edicao_habilitada)},
        "estatisticas": {"feicoes": 0, "extent_nativo": None, "por_campo": {}, "calculadas_em": None},
        "mapa_nomes": mapa,
    }
    if regras_campo:
        dados["regras_campo"] = regras_campo
    if extra_dados:
        dados.update(extra_dados)
    cur.execute(
        "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, acesso, criado_por, modificado_por) "
        "VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, 'inquilino', %s, %s)",
        (item_id, tenant_id, (titulo or "camada")[:250], usuario_id, _jsonb(dados), usuario_id, usuario_id),
    )
    return item_id, dados
