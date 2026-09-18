"""Carga das unidades consumidoras e dos transformadores do arquivo BDGD da cooperativa de teste como
ELEMENTOS DE REDE (`plat.rede_no`), para medir o item L4-10-continuidade-dec-fec em dado real.

`carga_bdgd_uc.py` (item L4-04-c) carrega as mesmas linhas como FEIÇÕES editáveis
(`plat.rede_feicao_ponto`). A continuidade não lê feição: ela lê o elemento de rede, que é onde o
importador BDGD (L4-01-c) preserva os campos da fonte em `atributos` — e é de `atributos` que saem as
três chaves deste item: `CONJ` (conjunto de unidades consumidoras da ANEEL), `CTMT` (alimentador) e
`UNI_TR_MT` (o transformador que alimenta a unidade). DIC e FIC vêm da própria camada de baixa tensão.

O schema do ativo vem de `PLAT_REDE_REFERENCIA_ESQUEMA` (ver `carga_bdgd.esquema()`); sem a variável, quem
depende dele é pulado dizendo essa razão. O nome do schema nunca é escrito no repositório: é o nome de um
parceiro e este repositório é público.
"""

from __future__ import annotations

import time

from tests.dados.carga_bdgd import esquema

# a camada de baixa tensão desta extração traz DIC e FIC já somados no ano (colunas `dic_sum`/`fic_sum`);
# o módulo aceita tanto isso quanto as doze colunas mensais da BDGD publicada
ATRIBUTOS_UC = (
    "jsonb_build_object('COD_ID', u.cod_id, 'CTMT', u.ctmt, 'CONJ', u.conj::text, "
    "'UNI_TR_MT', u.uni_tr_mt, 'DIC_SUM', u.dic_sum::text, 'FIC_SUM', u.fic_sum::text, "
    "'ENE_SUM', u.ene_sum::text)"
)
ATRIBUTOS_TRAFO = (
    "jsonb_build_object('COD_ID', t.cod_id, 'CTMT', t.ctmt, 'CONJ', t.conj::text, "
    "'POT_NOM', t.pot_nom::text, 'TIP_TRAFO', t.tip_trafo)"
)


def _tipo(cur, rede_id: str, grupo: str) -> str:
    cur.execute(
        "SELECT tp.id FROM plat.rede_tipo tp JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE tp.rede_id = %s::uuid AND g.codigo = %s ORDER BY tp.codigo LIMIT 1",
        (rede_id, grupo),
    )
    return str(cur.fetchone()["id"])


def carregar_uc_e_trafo(cur, tenant_id: int, rede_id: str) -> dict:
    """Insere as unidades consumidoras e os transformadores da cooperativa de teste como elementos da
    rede, com os campos da fonte preservados em `atributos`. Devolve contagem e tempo de cada camada."""
    esq = esquema()
    cron: dict[str, dict] = {}

    def rodar(rotulo: str, sql: str, params: tuple) -> None:
        t0 = time.perf_counter()
        cur.execute(sql, params)
        n = cur.fetchone()["n"]
        cron[rotulo] = {"linhas": n, "segundos": round(time.perf_counter() - t0, 3)}

    rodar("ucbt", f"""
        WITH carga AS (
          INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id, codigo_externo, atributos)
          SELECT %s, %s::uuid, 'consumidor', %s::uuid, u.cod_id, {ATRIBUTOS_UC}
          FROM {esq}.ucbt u
          ON CONFLICT (rede_id, papel, codigo_externo) DO NOTHING
          RETURNING 1
        ) SELECT count(*) AS n FROM carga
    """, (tenant_id, rede_id, _tipo(cur, rede_id, "unidade_consumidora")))

    rodar("untrmt", f"""
        WITH carga AS (
          INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id, codigo_externo, geom, atributos)
          SELECT %s, %s::uuid, 'dispositivo', %s::uuid, t.cod_id,
                 ST_SetSRID(ST_MakePoint(t.x, t.y), 4326), {ATRIBUTOS_TRAFO}
          FROM {esq}.trafo t
          ON CONFLICT (rede_id, papel, codigo_externo) DO NOTHING
          RETURNING 1
        ) SELECT count(*) AS n FROM carga
    """, (tenant_id, rede_id, _tipo(cur, rede_id, "transformador_de_distribuicao")))

    return cron
