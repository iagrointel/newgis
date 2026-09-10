"""Unidade do item L2-15-b-consultas-duckdb-em-escala: o portão do SQL livre, o cofre do motor e os
construtores de SQL das seis ferramentas grandes.

Nada aqui toca o banco: o que se testa é a decisão de aceitar ou recusar, e o resultado numérico da mesma
pergunta rodada no DuckDB sobre Parquet gerado na hora (pequeno, escrito no tmp_path do pytest).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app import limites
from app.consulta_grande import dialeto as dial
from app.consulta_grande import duckdb_cli, execucao, seguranca
from app.consulta_grande import consulta_livre as _consulta_livre  # noqa: F401 — registra consulta_sql
from app.consulta_grande import ferramentas_grandes as fg
from app.ferramentas import registro

RAIZ = Path(__file__).resolve().parents[2]
CAMPOS_PONTOS = ["id", "navio", "quando", "carga"]
CAMPOS_POLIGONOS = ["cod", "nome"]


# ---------------------------------------------------------------- portão do SQL livre
ACEITOS = [
    "SELECT count(*) FROM fonte_a",
    "SELECT navio, count(*) AS n FROM fonte_a GROUP BY navio ORDER BY n DESC",
    "WITH pares AS (SELECT navio, quando FROM fonte_a) SELECT count(*) FROM pares",
    "SELECT a.navio FROM fonte_a a JOIN fonte_b b ON a.navio = b.cod",
    "SELECT i FROM range(10) t(i)",
]

# As dez tentativas que o portão de pronto do item nomeia: caminho externo, http, ATTACH e INSTALL.
RECUSADOS = [
    ("SELECT * FROM read_parquet('/etc/segredo.parquet')", "funcao_proibida"),
    ("SELECT * FROM read_parquet('/home/dev/outro_inquilino/dados.parquet')", "funcao_proibida"),
    ("SELECT * FROM read_csv('/etc/passwd')", "funcao_proibida"),
    ("SELECT * FROM read_csv_auto('/etc/passwd')", "funcao_proibida"),
    ("SELECT * FROM read_parquet('https://exemplo.invalido/a.parquet')", "funcao_proibida"),
    ("SELECT * FROM read_json('http://exemplo.invalido/a.json')", "funcao_proibida"),
    ("ATTACH '/tmp/outro.db' AS outro", "nao_e_select"),
    ("INSTALL httpfs", "nao_e_select"),
    ("LOAD httpfs", "nao_e_select"),
    ("SELECT * FROM glob('/etc/*')", "funcao_proibida"),
]

OUTRAS_RECUSAS = [
    ("COPY (SELECT 1) TO '/tmp/x.csv'", "nao_e_select"),
    ("CREATE TABLE t AS SELECT 1", "nao_e_select"),
    ("DELETE FROM fonte_a", "nao_e_select"),
    ("PRAGMA database_list", "nao_e_select"),
    ("SET enable_external_access=true", "nao_e_select"),
    ("SELECT * FROM fonte_a; SELECT 1", "varias_instrucoes"),
    ("SELECT * FROM d_outro_inquilino.camada", "relacao_qualificada"),
    ("SELECT * FROM fonte_do_vizinho", "relacao_desconhecida"),
    ("SELECT * FROM postgres_scan('dbname=x', 'public', 'usuario')", "funcao_proibida"),
    ("SELECT * FROM ST_Read('/etc/mapa.shp')", "funcao_proibida"),
]


@pytest.mark.parametrize("sql", ACEITOS)
def test_portao_aceita_select_sobre_as_views_do_inquilino(sql):
    analise = seguranca.analisar(sql, ["fonte_a", "fonte_b"], tamanho_max=limites.CONSULTA_GRANDE_SQL_MAX)
    assert analise.relacoes <= {"fonte_a", "fonte_b", "pares", "a", "b"}


@pytest.mark.parametrize(("sql", "motivo"), RECUSADOS + OUTRAS_RECUSAS)
def test_portao_recusa_leitura_de_arquivo_rede_e_catalogo(sql, motivo):
    with pytest.raises(seguranca.ErroSqlInseguro) as e:
        seguranca.analisar(sql, ["fonte_a", "fonte_b"], tamanho_max=limites.CONSULTA_GRANDE_SQL_MAX)
    assert e.value.motivo == motivo, e.value.mensagem
    assert e.value.mensagem


def test_portao_recusa_as_dez_tentativas_do_item():
    """A cláusula do portão fala em dez tentativas; esta é a contagem, para ninguém encolher a lista depois."""
    assert len(RECUSADOS) == 10
    for sql, _ in RECUSADOS:
        with pytest.raises(seguranca.ErroSqlInseguro):
            seguranca.analisar(sql, ["fonte_a"], tamanho_max=limites.CONSULTA_GRANDE_SQL_MAX)


def test_portao_recusa_sql_vazio_e_longo_demais():
    with pytest.raises(seguranca.ErroSqlInseguro) as e:
        seguranca.analisar("   ", ["fonte_a"], tamanho_max=100)
    assert e.value.motivo == "sql_vazio"
    with pytest.raises(seguranca.ErroSqlInseguro) as e:
        seguranca.analisar("SELECT " + "1," * 200 + "1 FROM fonte_a", ["fonte_a"], tamanho_max=50)
    assert e.value.motivo == "sql_longo"


def test_analise_do_plano_recusa_operador_de_leitura_estranho():
    plano_bom = json.dumps([{"name": "PROJECTION", "children": [
        {"name": "READ_PARQUET", "children": [], "extra_info": {"Function": "READ_PARQUET"}}]}])
    assert seguranca.conferir_plano(plano_bom) == ["READ_PARQUET"]
    plano_ruim = json.dumps([{"name": "POSTGRES_SCAN", "children": [], "extra_info": {}}])
    with pytest.raises(seguranca.ErroSqlInseguro) as e:
        seguranca.conferir_plano(plano_ruim)
    assert e.value.motivo == "plano_com_leitura_estranha"


# ---------------------------------------------------------------- dados de apoio
def _gerar_parquet(tmp_path: Path, linhas: int = 20_000) -> dict:
    """Pontos e polígonos determinísticos em Parquet, escritos por um processo separado (o DuckDB nunca é
    importado no processo do pytest, pela mesma razão do `duckdb_cli`)."""
    dados = tmp_path / "dados"
    dados.mkdir(parents=True, exist_ok=True)
    programa = (
        "import duckdb, sys\n"
        "c = duckdb.connect(); c.execute('LOAD spatial')\n"
        f"c.execute(\"COPY (SELECT i AS id, (i%50) AS navio, TIMESTAMP '2024-01-01' + INTERVAL (i%400) HOUR "
        f"AS quando, (i%37)*0.5 AS carga, ST_Point(-50 + (i%97)*0.05, -20 + (i%53)*0.05) AS geom "
        f"FROM range({linhas}) t(i)) TO '{dados / 'pontos.parquet'}' (FORMAT PARQUET)\")\n"
        f"c.execute(\"COPY (SELECT i AS cod, 'area-'||i AS nome, "
        f"ST_MakeEnvelope(-50 + i*1.0, -20, -50 + (i+1)*1.0, -17) AS geom FROM range(5) t(i)) "
        f"TO '{dados / 'poligonos.parquet'}' (FORMAT PARQUET)\")\n"
    )
    r = subprocess.run([sys.executable, "-c", programa], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    return {"dir": dados, "pontos": str(dados / "pontos.parquet"),
            "poligonos": str(dados / "poligonos.parquet"), "linhas": linhas}


def _rodar(dados: dict, tmp_path: Path, sql: str, views: dict, **extra) -> dict:
    saida = tmp_path / "saida"
    saida.mkdir(parents=True, exist_ok=True)
    plano = {"sql": sql, "views": views, "diretorios": [str(dados["dir"]), str(saida)],
             "memoria_mb": 512, "threads": 2, "tempo_s": 120,
             "linhas_max": limites.CONSULTA_GRANDE_LINHAS_SAIDA_MAX,
             "sql_max": limites.CONSULTA_GRANDE_SQL_MAX,
             "saida_parquet": str(saida / "r.parquet"), "saida_csv": str(saida / "r.csv"), **extra}
    caminho = tmp_path / "plano.json"
    caminho.write_text(json.dumps(plano), encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "app.consulta_grande.duckdb_cli", "executar", str(caminho)],
                       cwd=str(RAIZ), capture_output=True, text=True, check=False)
    return {"rc": r.returncode, "err": r.stderr,
            "saida": json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else None}


def _fontes(dados: dict) -> dict:
    return {
        "camada": {"nome": "camada", "view": "v_pontos", "srid": 4326, "campos": CAMPOS_PONTOS,
                   "formato": "parquet", "linhas": dados["linhas"]},
        "pontos": {"nome": "pontos", "view": "v_pontos", "srid": 4326, "campos": CAMPOS_PONTOS,
                   "formato": "parquet", "linhas": dados["linhas"]},
        "poligonos": {"nome": "poligonos", "view": "v_poligonos", "srid": 4326, "campos": CAMPOS_POLIGONOS,
                      "formato": "parquet", "linhas": 5},
    }


# ---------------------------------------------------------------- o cofre do motor
@pytest.mark.parametrize(("sql", "trecho"), [
    ("SELECT count(*) FROM read_parquet('/etc/hostname')", "Permission"),
    ("SELECT count(*) FROM read_csv('/etc/passwd')", "Permission"),
])
def test_cofre_do_motor_recusa_mesmo_sem_o_portao(tmp_path, sql, trecho):
    """O motor tem de recusar por conta própria: a prova roda o SQL proibido DIRETO na conexão trancada,
    sem passar pelo portão de sintaxe, e confere que o DuckDB nega o acesso ao arquivo."""
    dados = _gerar_parquet(tmp_path, 100)
    programa = (
        "import duckdb, json\n"
        "c = duckdb.connect(); c.execute('LOAD spatial')\n"
        f"c.execute(\"CREATE VIEW v AS SELECT * FROM read_parquet('{dados['pontos']}')\")\n"
        f"c.execute(\"SET allowed_directories=['{dados['dir']}']\")\n"
        "c.execute('SET autoinstall_known_extensions=false')\n"
        "c.execute('SET autoload_known_extensions=false')\n"
        "c.execute('SET enable_external_access=false')\n"
        "c.execute('SET lock_configuration=true')\n"
        "assert c.execute('SELECT count(*) FROM v').fetchone()[0] == 100\n"
        "try:\n"
        f"    c.execute({sql!r}); print('PASSOU')\n"
        "except Exception as e:\n"
        "    print(type(e).__name__, str(e)[:60])\n"
    )
    r = subprocess.run([sys.executable, "-c", programa], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    assert "PASSOU" not in r.stdout, r.stdout
    assert trecho in r.stdout, r.stdout


def test_cofre_do_motor_recusa_destravar_a_configuracao(tmp_path):
    dados = _gerar_parquet(tmp_path, 50)
    programa = (
        "import duckdb\n"
        "c = duckdb.connect(); c.execute('LOAD spatial')\n"
        f"c.execute(\"SET allowed_directories=['{dados['dir']}']\")\n"
        "c.execute('SET enable_external_access=false')\n"
        "c.execute('SET lock_configuration=true')\n"
        "for sql in (\"SET enable_external_access=true\", \"SET allowed_directories=['/']\"):\n"
        "    try:\n"
        "        c.execute(sql); print('PASSOU', sql)\n"
        "    except Exception as e:\n"
        "        print('recusado', type(e).__name__)\n"
    )
    r = subprocess.run([sys.executable, "-c", programa], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    assert "PASSOU" not in r.stdout
    assert r.stdout.count("recusado") == 2, r.stdout


# ---------------------------------------------------------------- tetos
def test_consulta_acima_do_teto_de_tempo_e_cancelada_com_mensagem(tmp_path):
    dados = _gerar_parquet(tmp_path, 100)
    r = _rodar(dados, tmp_path,
               "SELECT count(*) FROM range(100000000000) t(i) WHERE i % 7 = 3",
               {"v_pontos": [dados["pontos"]]}, tempo_s=2)
    assert r["rc"] == duckdb_cli.CODIGO_TEMPO, r
    assert "passou do teto de 2 segundos e foi cancelada" in r["err"], r["err"]


def test_resultado_acima_do_teto_de_linhas_e_recusado_e_nao_truncado(tmp_path):
    dados = _gerar_parquet(tmp_path, 5_000)
    r = _rodar(dados, tmp_path, "SELECT * FROM v_pontos", {"v_pontos": [dados["pontos"]]}, linhas_max=100)
    assert r["rc"] == 1
    assert "mais de 100 linhas" in r["err"], r["err"]


# ---------------------------------------------------------------- as seis ferramentas grandes
CASOS = [
    ("agregar_em_grade", ("camada",),
     {"tamanho_celula": {"metros": 50_000.0}, "campo_periodo": "quando", "grao_periodo": "mes",
      "campo_valor": "carga", "projecao_metrica": 5880}),
    ("juncao_espacial", ("pontos", "poligonos"), {"campo_chave": "nome"}),
    ("resumir_dentro", ("poligonos", "pontos"),
     {"campo_chave": "nome", "campo_valor": "carga", "estatisticas": ["contagem", "soma", "media"]}),
    ("contagem_por_periodo", ("camada",), {"campo_periodo": "quando", "grao_periodo": "dia"}),
    ("detectar_duplicatas", ("camada",), {"campos": ["navio"], "mesma_posicao": False}),
    ("padroes_deslocamento", ("camada",),
     {"campo_id": "navio", "campo_periodo": "quando", "velocidade_maxima": 120.0}),
]


@pytest.mark.parametrize(("nome", "usadas", "parametros"), CASOS)
def test_ferramenta_grande_roda_no_duckdb_e_declara_os_campos(tmp_path, nome, usadas, parametros):
    dados = _gerar_parquet(tmp_path, 20_000)
    todas = _fontes(dados)
    fontes = {u: todas[u] for u in usadas}
    sql, srid = fg.CONSTRUTORES[nome](dial.DUCKDB, fontes, parametros)
    assert srid == 4326
    r = _rodar(dados, tmp_path, sql,
               {"v_pontos": [dados["pontos"]], "v_poligonos": [dados["poligonos"]]})
    assert r["rc"] == 0, r["err"]
    assert r["saida"]["linhas"] > 0
    assert r["saida"]["operadores_do_plano"], "o plano tem de nomear por onde leu"
    assert all(c["tipo"] for c in r["saida"]["campos"])


def test_juncao_espacial_nao_perde_ponto(tmp_path):
    """A cláusula do portão é de CONTAGEM: a junção à esquerda devolve ao menos uma linha por ponto."""
    dados = _gerar_parquet(tmp_path, 20_000)
    todas = _fontes(dados)
    sql, _ = fg.CONSTRUTORES["juncao_espacial"](
        dial.DUCKDB, {"pontos": todas["pontos"], "poligonos": todas["poligonos"]}, {"campo_chave": "nome"})
    r = _rodar(dados, tmp_path, sql, {"v_pontos": [dados["pontos"]], "v_poligonos": [dados["poligonos"]]})
    assert r["rc"] == 0, r["err"]
    assert r["saida"]["linhas"] >= 20_000


def test_campo_inexistente_da_erro_que_nomeia_o_campo(tmp_path):
    dados = _gerar_parquet(tmp_path, 10)
    with pytest.raises(execucao.ErroFerramentaGrande) as e:
        fg.CONSTRUTORES["contagem_por_periodo"](dial.DUCKDB, {"camada": _fontes(dados)["camada"]},
                                                {"campo_periodo": "nao_existe"})
    assert "nao_existe" in str(e.value)
    with pytest.raises(execucao.ErroFerramentaGrande):
        fg.CONSTRUTORES["contagem_por_periodo"](dial.DUCKDB, {"camada": _fontes(dados)["camada"]},
                                                {"campo_periodo": "quando; DROP TABLE x"})


# ---------------------------------------------------------------- escolha do motor
def _fonte(formato: str, linhas: int) -> dict:
    return {"nome": "camada", "formato": formato, "linhas": linhas, "srid": 4326, "campos": [],
            "item_id": "x", "titulo": "t", "versao": 1, "sha256": "s", "view": "v", "arquivos": []}


def test_escolha_do_motor():
    assert execucao.escolher_motor({"a": _fonte("parquet", 10**9)}) == "duckdb"
    assert execucao.escolher_motor({"a": _fonte("postgis", 1000)}) == "postgis"
    with pytest.raises(execucao.ErroFerramentaGrande) as e:
        execucao.escolher_motor({"a": _fonte("postgis", limites.CONSULTA_GRANDE_LIMIAR_LINHAS_DUCKDB + 1)})
    assert "geoparquet.gerar" in str(e.value)
    with pytest.raises(execucao.ErroFerramentaGrande) as e:
        execucao.escolher_motor({"a": _fonte("parquet", 10), "b": _fonte("postgis", 10)})
    assert "mistura" in str(e.value)


# ---------------------------------------------------------------- manifesto no catálogo
def test_as_sete_ferramentas_grandes_estao_no_mesmo_catalogo_das_pequenas():
    for nome in (*fg.FERRAMENTAS, "consulta_sql"):
        f = registro.obter(nome)
        assert f is not None, nome
        assert f.limites.get("aceita_parquet") is True, nome
        assert f.saidas, nome
        esquema = registro.esquema_json(f)
        assert esquema["additionalProperties"] is False
        descritor = registro.descrever_gp(f)
        assert descritor["executionType"] == "esriExecutionTypeAsynchronous"
        # o custo de toda ferramenta grande fica acima do teto do caminho em processo: a fila é obrigatória,
        # e é a fila que serializa "1 pesado por vez"
        entradas = {p.nome: {"feicoes": 1} for p in f.entradas if p.tipo == "GPFeatureRecordSetLayer"}
        assert f.custo(entradas, {}) > limites.FERRAMENTA_SINCRONO_CUSTO_MAX, nome


def test_tipo_do_postgres_a_partir_do_tipo_do_duckdb():
    assert duckdb_cli._tipo_pg("BIGINT") == "bigint"
    assert duckdb_cli._tipo_pg("DECIMAL(38,1)") == "numeric"
    assert duckdb_cli._tipo_pg("VARCHAR(20)") == "text"
    assert duckdb_cli._tipo_pg("MAP(VARCHAR, INTEGER)") == "text"
    assert duckdb_cli._e_geometria("GEOMETRY('OGC:CRS84')")
    assert duckdb_cli._e_geometria("GEOMETRY")
    assert not duckdb_cli._e_geometria("VARCHAR")


# ---------------------------------------------------------------- extent degenerado (defeito achado por este item)
def test_extent_de_ponto_linha_e_poligono():
    """`ST_Extent` devolve POINT com uma feição só e LINESTRING com feições colineares; a leitura do retângulo
    tem de aguentar os três casos (defeito achado ao rodar `detectar_duplicatas`, ver executor._extent_de)."""
    from app.ferramentas import executor as exe

    assert exe._extent_de(None) is None
    assert exe._extent_de('{"type":"Point","coordinates":[-50,-20]}') == [-50.0, -20.0, -50.0, -20.0]
    assert exe._extent_de('{"type":"LineString","coordinates":[[-50,-20],[-45,-20]]}') == [
        -50.0, -20.0, -45.0, -20.0]
    assert exe._extent_de(
        '{"type":"Polygon","coordinates":[[[-50,-20],[-45,-20],[-45,-15],[-50,-15],[-50,-20]]]}') == [
        -50.0, -20.0, -45.0, -15.0]
    # fora da faixa de graus (camada em projeção métrica que não foi transformada): sem extent, nunca um valor
    # impossível gravado no catálogo
    assert exe._extent_de('{"type":"Point","coordinates":[7000000,300000]}') is None
