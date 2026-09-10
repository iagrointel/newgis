"""Destruidores por tipo (ADR 0004 seção 9.1): o expurgo chama o destruidor do tipo ANTES do DELETE físico do item.
camada_vetorial → plat.camada_apagar(schema, tabela) quando a função do L0-04 existir, senão DROP TABLE direto (a
tabela pertence a plat_app); arquivo e miniatura → objeto pelo adaptador; raster → recusa até o L1-01 entregar
(o item fica na lixeira com aviso no log, nunca se apaga o registro sem o dado)."""

import re

from app import objetos

NOME = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
# contrato de plat.camada_tile_garantir/camada_tile_apagar (migração 20260906T1546): schema do inquilino e
# tabela de camada hospedada. Fora deste par não existe função de tile a apagar.
TILE_SCHEMA = re.compile(r"^d_[a-z0-9_]{1,60}$")
TILE_TABELA = re.compile(r"^c_[0-9a-f]{16}$")


class Recusado(Exception):
    """O destruidor não sabe apagar o dado físico: o item não é expurgado nesta rodada."""


def _camada_vetorial(cur, dados: dict, log) -> int:
    schema, tabela = dados.get("schema"), dados.get("tabela")
    if not schema or not tabela or not NOME.match(schema) or not NOME.match(tabela):
        return 0
    # item L2-04-a: a função de tile não é dona de plat_app e não cai com o DROP TABLE; sai por porta própria.
    # `plat.camada_tile_apagar` só aceita o par (d_<slug>, c_<16 hex>) que ela mesma criou e levanta
    # `nome_de_tabela_invalido` em qualquer outro — e camada publicada por caminho de teste ou de trabalho
    # (schema `plat_trabalho`, nome livre) nunca teve função de tile. Filtra-se AQUI, antes de chamar: sem
    # isso o expurgo inteiro falha por uma camada que não tem tile nenhum para apagar.
    if TILE_SCHEMA.match(schema) and TILE_TABELA.match(tabela):
        cur.execute("SELECT to_regprocedure('plat.camada_tile_apagar(text, text)') IS NOT NULL AS tem")
        if cur.fetchone()["tem"]:
            cur.execute("SELECT plat.camada_tile_apagar(%s, %s)", (schema, tabela))
    cur.execute("SELECT to_regprocedure('plat.camada_apagar(text, text)') IS NOT NULL AS tem")
    if cur.fetchone()["tem"]:
        cur.execute("SELECT plat.camada_apagar(%s, %s)", (schema, tabela))
        return 0
    cur.execute(
        "SELECT pg_total_relation_size(c.oid) AS b FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relname = %s",
        (schema, tabela),
    )
    r = cur.fetchone()
    if r is None:
        log("INFO", f"{schema}.{tabela} já não existia")
        return 0
    cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{tabela}" CASCADE')
    log("INFO", f"tabela {schema}.{tabela} apagada ({r['b']} bytes)")
    return int(r["b"] or 0)


def _arquivo(cur, dados: dict, log) -> int:
    chave = dados.get("chave")
    if chave:
        try:
            if objetos.apagar(chave):
                log("INFO", f"objeto {chave} apagado")
                return int(dados.get("bytes") or 0)
        except objetos.ChaveInvalida:
            log("AVISO", f"chave de objeto fora do padrão: {chave}")
    return 0


def _raster(cur, dados: dict, log) -> int:
    raise Recusado("raster: o destruidor (pgstac + objetos) é do L1-01; o item fica na lixeira")


DESTRUIDORES = {"camada_vetorial": _camada_vetorial, "arquivo": _arquivo, "raster": _raster}


def destruir(cur, tipo: str, dados: dict, miniatura_chave: str | None, log) -> int:
    """Apaga o dado físico do item; devolve bytes liberados. Levanta Recusado quando não sabe."""
    liberados = 0
    f = DESTRUIDORES.get(tipo)
    if f:
        liberados += f(cur, dados or {}, log)
    if miniatura_chave:
        try:
            if objetos.apagar(miniatura_chave):
                log("INFO", f"miniatura {miniatura_chave} apagada")
        except objetos.ChaveInvalida:
            log("AVISO", f"chave de miniatura fora do padrão: {miniatura_chave}")
    return liberados
