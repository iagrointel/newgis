"""Feições da rede (item L4-01-b-topologia-derivada): as tabelas genéricas `plat.rede_feicao_ponto`
(dispositivo) e `plat.rede_feicao_linha` (trecho) que a topologia deriva. São camadas NORMAIS e EDITÁVEIS —
esta passagem não as une ao catálogo geral (`camada_vetorial`, tabela dinâmica `d_<slug>.c_<uuid>`); ver
docs/rede/TOPOLOGIA.md seção "fronteira" para a fronteira honesta dessa decisão.

Cada feição pertence a um `plat.rede_tipo` (por `grupo`+`tipo_codigo`, o vocabulário do pacote importado); a
geometria (ponto/linha) tem de bater com `rede_grupo.geometria`, senão a gravação é recusada — uma feição de
linha num grupo de ponto não tem terminal, não tem topologia."""

import json

import psycopg2
import psycopg2.extras

from app.auth import comum as auth_comum
from app.erros import ErroAPI


def _jsonb(v: dict) -> str:
    return json.dumps(v, ensure_ascii=False)


def _tipo_do_grupo(cur, rede_id: str, grupo_codigo: str, tipo_codigo: int, geometria_esperada: str) -> str:
    cur.execute(
        "SELECT tp.id, g.geometria FROM plat.rede_tipo tp JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE tp.rede_id = %s::uuid AND g.codigo = %s AND tp.codigo = %s",
        (rede_id, grupo_codigo, tipo_codigo),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "tipo_inexistente", f"o grupo/tipo {grupo_codigo}/{tipo_codigo} não existe nesta rede "
                      "(a rede tem pacote de ativos importado?)")
    if r["geometria"] != geometria_esperada:
        raise ErroAPI(422, "geometria_incompativel",
                      f"o grupo {grupo_codigo} é de geometria '{r['geometria']}', não '{geometria_esperada}'")
    return r["id"]


def criar_ponto(cur, tenant_id: int, rede_id: str, corpo) -> dict:
    tipo_id = _tipo_do_grupo(cur, rede_id, corpo.grupo, corpo.tipo_codigo, "ponto")
    try:
        cur.execute(
            "INSERT INTO plat.rede_feicao_ponto(tenant_id, rede_id, tipo_id, geom, fase_bitmask, atributos) "
            "VALUES (%s, %s::uuid, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s::jsonb) "
            "RETURNING id, tipo_id, fase_bitmask, atributos, criado_em",
            (tenant_id, rede_id, tipo_id, corpo.lon, corpo.lat, corpo.fase_bitmask, _jsonb(corpo.atributos)),
        )
    except psycopg2.Error as e:
        raise auth_comum.erro_do_banco(e) from e
    return cur.fetchone()


def criar_linha(cur, tenant_id: int, rede_id: str, corpo) -> dict:
    tipo_id = _tipo_do_grupo(cur, rede_id, corpo.grupo, corpo.tipo_codigo, "linha")
    wkt = "LINESTRING(" + ", ".join(f"{lon} {lat}" for lon, lat in corpo.coordenadas) + ")"
    try:
        cur.execute(
            "INSERT INTO plat.rede_feicao_linha(tenant_id, rede_id, tipo_id, geom, fase_bitmask, atributos) "
            "VALUES (%s, %s::uuid, %s, ST_SetSRID(ST_GeomFromText(%s), 4326), %s, %s::jsonb) "
            "RETURNING id, tipo_id, fase_bitmask, atributos, criado_em",
            (tenant_id, rede_id, tipo_id, wkt, corpo.fase_bitmask, _jsonb(corpo.atributos)),
        )
    except psycopg2.Error as e:
        raise auth_comum.erro_do_banco(e) from e
    return cur.fetchone()


def listar_pontos(cur, rede_id: str, limite: int) -> list[dict]:
    cur.execute(
        "SELECT id, tipo_id, fase_bitmask, atributos, criado_em FROM plat.rede_feicao_ponto "
        "WHERE rede_id = %s::uuid ORDER BY criado_em LIMIT %s",
        (rede_id, limite),
    )
    return cur.fetchall()


def listar_linhas(cur, rede_id: str, limite: int) -> list[dict]:
    cur.execute(
        "SELECT id, tipo_id, fase_bitmask, atributos, criado_em FROM plat.rede_feicao_linha "
        "WHERE rede_id = %s::uuid ORDER BY criado_em LIMIT %s",
        (rede_id, limite),
    )
    return cur.fetchall()
