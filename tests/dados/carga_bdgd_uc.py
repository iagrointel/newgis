"""Carga do consumo e da geração do arquivo BDGD da cooperativa de teste, para medir o item
L4-04-c-sumarios-por-subrede em escala real.

`tests/dados/carga_bdgd.py` (item L4-01-b) carrega a REDE: trechos de média e baixa tensão, ramais,
transformadores e postes. O sumário por subrede precisa de duas camadas que aquela carga não usa, porque a
topologia não depende delas:

  ucbt → grupo unidade_consumidora / tipo consumidor_de_baixa_tensao (camada UCBT_tab)
  ugbt → grupo geracao_distribuida / tipo geracao_em_baixa_tensao   (camada UGBT_tab)

Nenhuma das duas tem geometria própria no arquivo: as duas apontam o PONTO NOTÁVEL de conexão (`pn_con`) e a
coordenada vem de lá. Medido no ativo de referência: 27.587 de 27.587 unidades consumidoras e 1.385 de 1.385
gerações têm `pn_con` correspondente em `ponnot` — nenhuma coordenada é inventada, e uma linha sem par
simplesmente não entraria.

⛔ UNIDADES, MEDIDAS E NÃO ASSUMIDAS. O dicionário do pacote declara `COMP` em km e `ENE_SUM` em MWh. Nesta
extração os dois estão em outra escala: a soma de `COMP` por alimentador bate com o comprimento geodésico do
próprio traçado em METROS (a maior divergência entre os 20 alimentadores é de −8,5 %, e nos maiores fica
abaixo de 1,3 %), e a média de `ENE_SUM` por unidade consumidora é de 2.950 por ano, coerente com kWh e não
com MWh. O sumário soma o valor como ele está no arquivo; o teste de medição compara com o MESMO valor, de
modo que a conferência vale qualquer que seja a unidade.

O schema do ativo vem de `PLAT_REDE_REFERENCIA_ESQUEMA` (ver `carga_bdgd.esquema()`); sem a variável, quem
depende dele é pulado dizendo essa razão."""

import time

from tests.dados.carga_bdgd import esquema

ATRIBUTOS_UC = (
    "jsonb_build_object('cod_id', u.cod_id, 'pn_con', u.pn_con, 'ctmt', u.ctmt, "
    "'uni_tr_mt', u.uni_tr_mt, 'clas_sub', u.clas_sub, 'gru_ten', u.gru_ten, 'ene', u.ene_sum, "
    "'car_inst', u.car_inst)"
)
ATRIBUTOS_GD = (
    "jsonb_build_object('cod_id', g.cod_id, 'pn_con', g.pn_con, 'ctmt', g.ctmt, "
    "'uni_tr_mt', g.uni_tr_mt, 'pot', g.pot_sum, 'ene', g.ene_sum)"
)


def _tipo(cur, rede_id: str, grupo: str, codigo: int) -> str:
    cur.execute(
        "SELECT tp.id FROM plat.rede_tipo tp JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE tp.rede_id = %s::uuid AND g.codigo = %s AND tp.codigo = %s",
        (rede_id, grupo, codigo),
    )
    return str(cur.fetchone()["id"])


def carregar_consumo_e_geracao(cur, tenant_id: int, rede_id: str) -> dict:
    """Insere unidades consumidoras e gerações de baixa tensão como feições de ponto da rede, com a
    coordenada do ponto notável de conexão. Devolve contagem e tempo de cada uma."""
    esq = esquema()
    cron = {}

    def rodar(rotulo, sql, params):
        t0 = time.perf_counter()
        cur.execute(sql, params)
        n = cur.fetchone()["n"]
        cron[rotulo] = {"linhas": n, "segundos": round(time.perf_counter() - t0, 3)}

    rodar("ucbt", f"""
        WITH carga AS (
          INSERT INTO plat.rede_feicao_ponto(tenant_id, rede_id, tipo_id, geom, atributos)
          SELECT %s, %s::uuid, %s::uuid, ST_SetSRID(ST_MakePoint(p.x, p.y), 4326), {ATRIBUTOS_UC}
          FROM {esq}.ucbt u JOIN {esq}.ponnot p ON p.cod_id = u.pn_con
          RETURNING 1
        ) SELECT count(*) AS n FROM carga
    """, (tenant_id, rede_id, _tipo(cur, rede_id, "unidade_consumidora", 1)))

    rodar("ugbt", f"""
        WITH carga AS (
          INSERT INTO plat.rede_feicao_ponto(tenant_id, rede_id, tipo_id, geom, atributos)
          SELECT %s, %s::uuid, %s::uuid, ST_SetSRID(ST_MakePoint(p.x, p.y), 4326), {ATRIBUTOS_GD}
          FROM {esq}.ugbt g JOIN {esq}.ponnot p ON p.cod_id = g.pn_con
          RETURNING 1
        ) SELECT count(*) AS n FROM carga
    """, (tenant_id, rede_id, _tipo(cur, rede_id, "geracao_distribuida", 1)))

    return cron


def carregar_media_tensao_e_trafos(cur, tenant_id: int, rede_id: str) -> dict:
    """Só o que o sumário por alimentador precisa: os trechos de média tensão e os transformadores. É a
    carga de `carga_bdgd.carregar` sem a baixa tensão nem os postes — que pesam 90 mil feições e não entram
    em nenhuma cláusula deste item."""
    esq = esquema()
    cron = {}

    def rodar(rotulo, sql, params):
        t0 = time.perf_counter()
        cur.execute(sql, params)
        n = cur.fetchone()["n"]
        cron[rotulo] = {"linhas": n, "segundos": round(time.perf_counter() - t0, 3)}

    fase = ("(CASE WHEN fas_con ILIKE '%%A%%' THEN 1 ELSE 0 END) + "
            "(CASE WHEN fas_con ILIKE '%%B%%' THEN 2 ELSE 0 END) + "
            "(CASE WHEN fas_con ILIKE '%%C%%' THEN 4 ELSE 0 END)")
    rodar("ssdmt", f"""
        WITH carga AS (
          INSERT INTO plat.rede_feicao_linha(tenant_id, rede_id, tipo_id, geom, fase_bitmask, atributos)
          SELECT %s, %s::uuid, %s::uuid, ST_GeometryN(ST_GeomFromText(wkt, 4326), 1), {fase},
                 jsonb_build_object('cod_id', cod_id, 'ctmt', ctmt, 'uni_tr_at', uni_tr_at, 'sub', sub,
                                    'conj', conj, 'fas_con', fas_con, 'comp', comp, 'pos', pos)
          FROM {esq}.ssdmt WHERE wkt IS NOT NULL
          RETURNING 1
        ) SELECT count(*) AS n FROM carga
    """, (tenant_id, rede_id, _tipo(cur, rede_id, "trecho_de_media_tensao", 1)))

    rodar("trafo", f"""
        WITH carga AS (
          INSERT INTO plat.rede_feicao_ponto(tenant_id, rede_id, tipo_id, geom, atributos)
          SELECT %s, %s::uuid, %s::uuid, ST_SetSRID(ST_MakePoint(x, y), 4326),
                 jsonb_build_object('cod_id', cod_id, 'pot_nom', pot_nom, 'tip_trafo', tip_trafo,
                                    'ctmt', ctmt, 'uni_tr_at', uni_tr_at)
          FROM {esq}.trafo
          RETURNING 1
        ) SELECT count(*) AS n FROM carga
    """, (tenant_id, rede_id, _tipo(cur, rede_id, "transformador_de_distribuicao", 1)))

    return cron


def esperado_por_ctmt(cur) -> dict:
    """O que o ARQUIVO diz por alimentador, lido direto das tabelas do ativo: comprimento declarado e
    número de trechos de média tensão, transformadores e potência, unidades consumidoras e energia,
    gerações e potência. Caminho independente do sumário da plataforma — nenhuma consulta a `plat.*`."""
    esq = esquema()
    cur.execute(f"SELECT cod_id FROM {esq}.ctmt ORDER BY cod_id")
    por_ctmt = {r["cod_id"]: {"ssdmt": 0, "comp_m": 0.0, "trafos": 0, "kva": 0.0,
                              "ucbt": 0, "ene": 0.0, "ugbt": 0, "pot_kw": 0.0}
                for r in cur.fetchall()}

    cur.execute(f"SELECT ctmt, count(*) AS n, sum(comp) AS comp FROM {esq}.ssdmt GROUP BY 1")
    for r in cur.fetchall():
        por_ctmt[r["ctmt"]]["ssdmt"] = r["n"]
        por_ctmt[r["ctmt"]]["comp_m"] = float(r["comp"] or 0.0)
    cur.execute(f"SELECT ctmt, count(*) AS n, sum(pot_nom) AS pot FROM {esq}.trafo GROUP BY 1")
    for r in cur.fetchall():
        por_ctmt[r["ctmt"]]["trafos"] = r["n"]
        por_ctmt[r["ctmt"]]["kva"] = float(r["pot"] or 0.0)
    cur.execute(f"SELECT ctmt, count(*) AS n, sum(ene_sum) AS ene FROM {esq}.ucbt GROUP BY 1")
    for r in cur.fetchall():
        por_ctmt[r["ctmt"]]["ucbt"] = r["n"]
        por_ctmt[r["ctmt"]]["ene"] = float(r["ene"] or 0.0)
    cur.execute(f"SELECT ctmt, count(*) AS n, sum(pot_sum) AS pot FROM {esq}.ugbt GROUP BY 1")
    for r in cur.fetchall():
        por_ctmt[r["ctmt"]]["ugbt"] = r["n"]
        por_ctmt[r["ctmt"]]["pot_kw"] = float(r["pot"] or 0.0)
    return por_ctmt


def totais_arquivo(cur) -> dict:
    esq = esquema()
    saida = {}
    for tabela in ("ssdmt", "trafo", "ucbt", "ugbt", "ctmt"):
        cur.execute(f"SELECT count(*) AS n FROM {esq}.{tabela}")
        saida[tabela] = cur.fetchone()["n"]
    return saida
