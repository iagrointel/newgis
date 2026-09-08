"""Destruidores por tipo (ADR 0004 seção 9.1): o expurgo chama o destruidor do tipo ANTES do DELETE físico do item.
camada_vetorial → plat.camada_apagar(schema, tabela) quando a função do L0-04 existir, senão DROP TABLE direto (a
tabela pertence a plat_app); arquivo e miniatura → objeto pelo adaptador; raster → recusa até o L1-01 entregar
(o item fica na lixeira com aviso no log, nunca se apaga o registro sem o dado)."""

import re

from app import objetos

NOME = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


class Recusado(Exception):
    """O destruidor não sabe apagar o dado físico: o item não é expurgado nesta rodada."""


def _vista_de_camada(cur, dados: dict, log) -> int:
    """A vista (item L5-32) é uma VIEW: não ocupa bytes de dado e some com um DROP VIEW. `DROP TABLE`
    falharia aqui, e `CASCADE` na tabela-mãe deixaria o item órfão — por isso a vista tem porta própria."""
    schema, tabela = dados.get("schema"), dados.get("tabela")
    if not schema or not tabela or not NOME.match(schema) or not NOME.match(tabela):
        return 0
    cur.execute(f'DROP VIEW IF EXISTS "{schema}"."{tabela}"')
    log("INFO", f"vista {schema}.{tabela} apagada")
    return 0


def _camada_vetorial(cur, dados: dict, log) -> int:
    schema, tabela = dados.get("schema"), dados.get("tabela")
    if not schema or not tabela or not NOME.match(schema) or not NOME.match(tabela):
        return 0
    # item L2-04-a: a função de tile não é dona de plat_app e não cai com o DROP TABLE; sai por porta própria
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


DESTRUIDORES = {"camada_vetorial": _camada_vetorial, "vista_de_camada": _vista_de_camada,
                "arquivo": _arquivo, "raster": _raster}


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
