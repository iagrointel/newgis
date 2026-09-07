"""Item L3-07-agregacao — a prova do portão: `app.amc.agregacao.agregar()` (o motor genérico, item novo)
reproduz `cbre.imoveis_fav` (piloto real, só leitura — nunca escrito por este teste) recomputando a mesma
conta que `cbre/pipeline/85_fatores.sql` faz à mão em SQL: média por fator ponderada pela área de
interseção sobre células não vetadas de `cbre.hex_fav`, fração vetada, veto principal e contagem de
células, para as 4.346 feições de `cbre.imoveis_candidatos`.

Por que essa comparação prova o item genérico: `cbre.hex_fav` tem VÁRIOS fatores já na escala 0-100
(`f_decl`, `f_zon`, ...) — o mesmo formato que `agregar()` espera de qualquer conjunto de células — então
a prova cobre o mecanismo geométrico com N fatores reais, não um caso de brinquedo.

Duas exceções documentadas, contadas à parte e não escondidas: (a) 18 imóveis com
`mine_veredito = 'veto_mineracao'` — o pipeline do cbre SOBRESCREVE `pct_vetado`/`veto_principal` com uma
regra de negócio (veredito de mineração por satélite) que não é geometria nenhuma, então não é este
mecanismo que se está provando ali; (b) `NULL` × `0`: quando NENHUMA célula tocada escapa do veto, o SQL
do cbre não tem linha nenhuma no agrupamento (`n_cel`/`f_*` saem `NULL`); `agregar()` devolve `n_cel = 0`
e `fatores_media = {}` para o mesmo caso — os dois dizem a mesma coisa (nenhuma célula não vetada), e o
teste normaliza antes de comparar.

Uma terceira exceção, achada rodando este teste (conferida linha a linha em `pipeline/85_fatores.sql`):
sete fatores (`f_roubo`, `f_trib`, `f_renda`, `f_rlapp`, `f_polos`, `f_se`, `f_cluster`) e o `f_varzea`
NÃO são o resultado da agregação por célula em `cbre.imoveis_fav` — o próprio pipeline do cbre os
SOBRESCREVE depois, com uma consulta por imóvel direto de `cbre.imovel_fatores_extra`/
`cbre.imovel_inundacao` (roubo de carga pelo trajeto do imóvel, tributação do lote, inundação oficial
por imóvel — mais preciso que a média das células que ele toca). Comparar essas colunas testaria O
GANCHO por imóvel do cbre, não a agregação de grade — por isso ficam fora de `FATORES_HEX` (only os 10
fatores que o próprio SQL do cbre lista no `SELECT` de resumo do fim do arquivo, nunca tocados por
UPDATE nenhum depois da agregação)."""

import datetime
import json
import os
import time

import pytest

from app.amc import agregacao

MEDIDAS_ITEM = "L3-07-agregacao"

# os fatores de `cbre.imoveis_fav` que são MESMO o resultado da agregação de área sobre `cbre.hex_fav`
# (a lista do próprio SELECT de resumo no fim de `cbre/pipeline/85_fatores.sql` — nenhum UPDATE depois
# da agregação toca estes dez; ver a nota do módulo sobre os que ficam de fora e por quê).
FATORES_HEX = [
    "f_decl", "f_zon", "f_gru", "f_rod", "f_disp", "f_ener", "f_agua", "f_restr", "f_press", "f_dens",
]

_FEICOES_SQL = "SELECT car_cod AS feicao_id, geom FROM cbre.imoveis_candidatos"
_CELULAS_SQL = (
    "SELECT h.hex_id::text AS cell_id, h.geom_utm AS geom, hf.veto, hf.veto_motivo AS motivo, "
    "jsonb_build_object(" + ", ".join(f"'{f}', hf.{f}" for f in FATORES_HEX) + ") AS fatores "
    "FROM cbre.hex h JOIN cbre.hex_fav hf USING (hex_id)"
)


@pytest.fixture(scope="session")
def _conexao_sessao(env):
    """Conexão dedicada, com escopo de sessão, só para não recalcular a agregação de 4.346 x 73.115
    células a cada teste — `conexao_plat_app` (tests/conftest.py) é escopo função de propósito (rollback
    a cada teste); aqui é tudo leitura, então uma conexão de sessão em modo autocommit é segura."""
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = True
    try:
        yield con
    finally:
        con.close()


@pytest.fixture(scope="module")
def agregado(_conexao_sessao):
    with _conexao_sessao.cursor() as cur:
        t0 = time.monotonic()
        r = agregacao.agregar(cur, _FEICOES_SQL, {}, _CELULAS_SQL, {})
        tempo_python_ms = round((time.monotonic() - t0) * 1000, 1)
    assert len(r["resultados"]) == 4346, f"esperava as 4.346 feições de imoveis_candidatos, veio {len(r['resultados'])}"
    return r, tempo_python_ms


@pytest.fixture(scope="module")
def referencia(_conexao_sessao):
    """`cbre.imoveis_fav`, só leitura — a verdade que o pipeline do cbre já calculou."""
    with _conexao_sessao.cursor() as cur:
        cur.execute(
            "SELECT car_cod, n_cel, pct_vetado, veto_principal, mine_veredito, "
            + ", ".join(FATORES_HEX)
            + " FROM cbre.imoveis_fav"
        )
        linhas = {r["car_cod"]: dict(r) for r in cur.fetchall()}
    assert len(linhas) == 4346
    return linhas


def test_geometria_reproduz_area_total_com_st_area_no_crs_metrico(agregado, _conexao_sessao):
    """Confere, independente da agregação por fator, que a SOMA da área de interseção por imóvel bate com
    uma consulta ST_Area/ST_Intersection escrita direto aqui (não chamando `agregacao.py`), amostrada em
    30 imóveis — a prova de que a interseção usa o CRS métrico (31983), não uma reprojeção implícita."""
    r, _ = agregado
    por_id = {x["feicao_id"]: x for x in r["resultados"]}
    with _conexao_sessao.cursor() as cur:
        cur.execute(
            "SELECT car_cod FROM cbre.imoveis_candidatos TABLESAMPLE SYSTEM (5) ORDER BY car_cod LIMIT 30"
        )
        amostra = [x["car_cod"] for x in cur.fetchall()]
    for cid in amostra:
        with _conexao_sessao.cursor() as cur:
            cur.execute(
                "SELECT sum(ST_Area(ST_Intersection(i.geom, h.geom_utm))) AS a "
                "FROM cbre.imoveis_candidatos i JOIN cbre.hex h ON ST_Intersects(i.geom, h.geom_utm) "
                "WHERE i.car_cod = %s",
                (cid,),
            )
            esperado = cur.fetchone()["a"]
        obtido = por_id[cid]["area_total_m2"]
        if esperado is None:
            assert obtido is None
        else:
            assert obtido == pytest.approx(float(esperado), rel=1e-6)


def test_feicao_que_nao_toca_celula_sai_como_sem_celula(agregado, _conexao_sessao):
    """Nenhum dos 4.346 imóveis de teste fica fora da grade (ela cobre os 9 municípios inteiros) — a
    cláusula 'nunca 0' é provada à parte com uma feição fabricada fora da área de estudo."""
    r, _ = agregado
    assert all(not x["sem_celula"] for x in r["resultados"])  # confere a premissa da amostra usada acima

    longe = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0],
                                                  [0.0, 10.0], [0.0, 0.0]]]}  # meio do Atlântico, SRID 31983
    fsql, fparams = agregacao.feicoes_de_geojson([("fora", longe)], 31983, srid_entrada=31983)
    with _conexao_sessao.cursor() as cur:
        r2 = agregacao.agregar(cur, fsql, fparams, _CELULAS_SQL, {})["resultados"][0]
    assert r2["sem_celula"] is True
    assert r2["area_total_m2"] is None
    assert r2["fracao_vetada"] is None
    assert r2["favorabilidade"] is None
    assert r2["n_cel"] is None  # nunca 0 quando é ausência de célula, para não confundir com "0 favorável"


def test_reproduz_imoveis_fav_com_delta_ate_0_5_em_99_5_por_cento(agregado, referencia, medida):
    r, tempo_python_ms = agregado
    por_id = {x["feicao_id"]: x for x in r["resultados"]}
    tempo_ms_sql = r["tempo_ms"]

    excecoes_mineracao = {cid for cid, ref in referencia.items() if ref["mine_veredito"] == "veto_mineracao"}
    assert len(excecoes_mineracao) == 18  # documentado no docstring do módulo; falha se o piloto mudar

    resumo = {}
    falhas_detalhe = {}
    colunas = [*FATORES_HEX, "n_cel", "pct_vetado", "veto_principal"]
    for coluna in colunas:
        total = 0
        ok = 0
        exemplos = []
        for cid, ref in referencia.items():
            if coluna in ("pct_vetado", "veto_principal") and cid in excecoes_mineracao:
                continue  # veredito de mineração sobrescreve isto no pipeline do cbre; não é geometria
            total += 1
            calc = por_id[cid]
            if coluna == "n_cel":
                esperado = ref["n_cel"] if ref["n_cel"] is not None else 0
                obtido = calc["n_cel"] or 0
                bate = esperado == obtido
            elif coluna == "veto_principal":
                esperado, obtido = ref["veto_principal"], calc["veto_principal"]
                bate = esperado == obtido
            elif coluna == "pct_vetado":
                esperado = float(ref["pct_vetado"]) if ref["pct_vetado"] is not None else None
                obtido = calc["fracao_vetada"]
                if esperado is None and obtido is None:
                    bate = True
                elif esperado is None or obtido is None:
                    bate = False
                else:
                    bate = abs(esperado - obtido) <= 0.5
            else:  # fatores f_* (smallint 0-100 no cbre)
                esperado = ref[coluna]
                obtido = calc["fatores_media"].get(coluna)
                if esperado is None and obtido is None:
                    bate = True
                elif esperado is None or obtido is None:
                    bate = False
                else:
                    bate = abs(float(esperado) - float(obtido)) <= 0.5
            ok += bate
            if not bate and len(exemplos) < 5:
                exemplos.append({"car_cod": cid, "esperado": esperado, "obtido": obtido})
        taxa = ok / total if total else 1.0
        resumo[coluna] = {"total": total, "ok": ok, "taxa": round(taxa, 5)}
        if exemplos:
            falhas_detalhe[coluna] = exemplos

    carga_1min = os.getloadavg()[0]
    with open("/proc/meminfo", encoding="ascii") as fh:
        linha_mem = next(linha for linha in fh if linha.startswith("MemAvailable:"))
        ram_livre_gb = round(int(linha_mem.split()[1]) / (1024 * 1024), 2)
    medido_em = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    contexto = f"carga_1min={carga_1min:.2f}, ram_livre_gb={ram_livre_gb:.2f}, medido_em={medido_em}"

    gravar = medida(MEDIDAS_ITEM)
    gravar("tempo_agregacao_4346_feicoes_73115_celulas_ms", tempo_ms_sql, "ms",
           f"app.amc.agregacao.agregar() sobre cbre.imoveis_candidatos x cbre.hex_fav (10 fatores "
           f"comparáveis, 73.115 células); {contexto}")
    gravar("tempo_agregacao_python_total_ms", tempo_python_ms, "ms",
           f"tempo de parede do fixture 'agregado' (inclui fetch de 4.346 linhas); {contexto}")
    for coluna, r_coluna in resumo.items():
        gravar(f"reproducao_{coluna}_taxa", r_coluna["taxa"], "fração de feições com |Δ| <= 0,5",
               f"comparação por feição de agregacao.agregar()[...].fatores_media/{coluna} "
               f"contra cbre.imoveis_fav.{coluna}, n={r_coluna['total']}")
    gravar("excecoes_mine_veredito_veto_mineracao", len(excecoes_mineracao), "feições",
           "cbre.imoveis_fav onde mine_veredito='veto_mineracao' — pct_vetado/veto_principal sobrescritos "
           "por regra de negócio alheia à geometria, excluídos da comparação de pct_vetado/veto_principal")

    piores = {c: v["taxa"] for c, v in resumo.items() if v["taxa"] < 0.995}
    assert not piores, (
        f"colunas abaixo de 99,5% de reprodução (|Δ|<=0,5): {json.dumps(piores, indent=1)}\n"
        f"exemplos de falha: {json.dumps(falhas_detalhe, indent=1, default=str)[:4000]}"
    )
