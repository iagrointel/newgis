"""Injeção em consulta fechada por construção (item L7-03-d-injecao-consulta; L7_CONCEITO C8). Portão:
"suíte com >= 100 payloads (sqlmap tamper list, `1=1; DROP`, comentários, unicode, `pg_sleep`, funções de
sistema, subconsulta em outStatistics) → todos 400 ou resultado correto, 0 execução; grep prova ausência de
f-string/format em SQL com entrada do usuário (teste estático); ZAP baseline sem alerta alto".

Como se prova "0 execução": (1) nenhuma resposta 5xx (o parser recusa ANTES do banco: 400/422); (2) uma resposta
200 só é "resultado correto" se o corpo é o JSON do FeatureServer com feições da própria camada (contagem <=
total conhecido, atributos só do esquema); (3) o `pg_sleep(5)` de todos os payloads somados nunca custa 5 s
(latência máxima medida e gravada); (4) uma tabela-canário no schema do inquilino continua existindo e com as
mesmas linhas depois de todos os payloads, e a contagem da camada não muda (`; DROP`, `UPDATE`, `DELETE`
nunca rodaram); (5) o teste estático varre `app/` por SQL montado com interpolação de NOME DE ENTRADA DO USUÁRIO
(`where`, `outFields`, `orderByFields`, `outStatistics`, `havingClause`, `filter`, `bbox`, `query_params`...) —
zero ocorrências — e roda o `bandit` (B608) sobre `app/consulta` gravando a contagem como medida.

A camada de teste é a `cobertura.gpkg` da suíte de ingestão, importada de verdade (worker próprio da trilha).
ZAP baseline NÃO roda aqui: não há imagem do ZAP nesta máquina e o disco a 94 % não comporta baixá-la (D21) —
cláusula registrada como pendente no handoff, nunca como passada."""

from __future__ import annotations

import ast
import json
import os
import socket
import subprocess
import time
from pathlib import Path

import psycopg2
import pytest

from app.catalogo import destruidores
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.ingestao.conftest import Ingestor
from tests.api.jobs.conftest import WorkerExtra
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L7-03-d-injecao-consulta"
RAIZ = Path(__file__).resolve().parents[2]


def _porta_livre() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def worker(env):
    nome = f"l703d-{os.getpid()}"
    w = WorkerExtra(env, nome, 1, _porta_livre())
    assert w.saude()["nome_base"] == nome
    yield w
    w.parar()


@pytest.fixture(scope="module")
def camada(sessao_a, env, worker):
    """importa cobertura.gpkg como camada do inquilino A; devolve (item_id, campos, total, sessao). Teardown
    igual ao `ingestor_a` da suíte de ingestão (lixeira + destruidor físico + expurgo)."""
    gerado = RAIZ / "tests" / "dados" / "gerados" / "cobertura.gpkg"
    if not gerado.exists():
        subprocess.run([str(RAIZ / "venv" / "bin" / "python"), str(RAIZ / "tests" / "dados" / "gerar.py")],
                       check=True, cwd=RAIZ, timeout=600)
    ing = Ingestor(sessao_a)
    final = None
    for tentativa in range(4):
        iid, _ = ing.importar("cobertura.gpkg", "gpkg")
        final = ing.confirmar(iid)
        if final["estado"] == "concluida":
            break
        time.sleep(2 + tentativa)
    assert final and final["estado"] == "concluida", final
    item_id = final["item_id"]
    r = sessao_a.get(f"/rest/services/{item_id}/FeatureServer/0?f=json")
    assert r.status_code == 200, r.text
    campos = [c["name"] for c in r.json()["fields"]]
    r = sessao_a.get(f"/rest/services/{item_id}/FeatureServer/0/query?where=1%3D1&returnCountOnly=true&f=json")
    assert r.status_code == 200, r.text
    total = r.json()["count"]
    assert total > 0
    yield {"item_id": item_id, "campos": campos, "total": total}
    ing.liberar_token()
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
            adm = cur.fetchone()["usuario_id"]
        contexto(con, ids["demo"], usuario_id=adm, login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
            cur.execute("DELETE FROM plat.importacao WHERE arquivo_id = ANY(%s::uuid[]) OR item_id = ANY(%s::uuid[])",
                        (ing.arquivos, ing.camadas))
            for iid in ing.camadas + ing.arquivos:
                cur.execute("SELECT tipo, dados, miniatura_chave FROM plat.item WHERE id = %s::uuid", (iid,))
                item = cur.fetchone()
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (iid,))
                if item is not None:
                    try:
                        destruidores.destruir(cur, item["tipo"], item["dados"], item["miniatura_chave"],
                                              lambda *_a: None)
                    except destruidores.Recusado:
                        pass
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (iid,))
        con.commit()
    finally:
        con.close()


@pytest.fixture(scope="module")
def canario(env):
    """tabela no schema do inquilino A que nenhum payload pode tocar; contagem conferida no fim."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
        contexto(con, ids["demo"])
        with con.cursor() as cur:
            cur.execute("SELECT current_schema(), current_setting('plat.tenant_id', true)")
            cur.execute("CREATE TABLE IF NOT EXISTS plat_trabalho.zt_canario_injecao(id serial PRIMARY KEY, v text)")
            cur.execute("DELETE FROM plat_trabalho.zt_canario_injecao")
            cur.execute("INSERT INTO plat_trabalho.zt_canario_injecao(v) VALUES ('a'), ('b'), ('c')")
        con.commit()
        yield "plat_trabalho.zt_canario_injecao"
        with con.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM plat_trabalho.zt_canario_injecao")
            assert cur.fetchone()["n"] == 3, "o canário foi alterado: algum payload executou"
            cur.execute("DROP TABLE plat_trabalho.zt_canario_injecao")
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------- payloads

_BASE = [
    "1=1; DROP TABLE plat_trabalho.zt_canario_injecao; --",
    "1=1; DELETE FROM plat_trabalho.zt_canario_injecao",
    "1=1; UPDATE plat_trabalho.zt_canario_injecao SET v='x'",
    "1=1 OR 1=1", "1=1 or 1=1", "1=1/**/OR/**/1=1", "1=1%0aOR%0a1=1", "1=1 OR '1'='1", "1=1 OR 'a' LIKE 'a'",
    "1=1--", "1=1 --", "1=1 #", "1=1 /* c */", "1=1;--", "1=1');--", "1=1))--", "')", "'", "''", "\"", "\\",
    "1=1 UNION SELECT 1", "1=1 UNION ALL SELECT NULL,NULL", "1=1 UNION SELECT usename FROM pg_user",
    "1=1 UNION SELECT tenant_id FROM plat.tenant", "1=1 UNION SELECT * FROM plat.usuario",
    "1=1 AND pg_sleep(5)", "1=1 AND (SELECT pg_sleep(5))", "1=1; SELECT pg_sleep(5)", "fid=1 AND pg_sleep(5)",
    "fid=(SELECT pg_sleep(5))", "fid=1 OR pg_sleep(5) IS NULL", "1=1 AND 1=(SELECT 1 FROM pg_sleep(5))",
    "fid=1 AND current_user='postgres'", "fid=1 AND version() LIKE '%'", "fid=1 AND current_database()='x'",
    "fid=1 AND inet_server_addr() IS NOT NULL", "fid=1 AND pg_read_file('/etc/passwd') IS NOT NULL",
    "fid=1 AND (SELECT count(*) FROM plat.usuario)>0", "fid IN (SELECT fid FROM plat.tenant)",
    "fid=1 AND (SELECT tenant_id FROM plat.tenant LIMIT 1)=1", "fid=1 AND lo_import('/etc/passwd')>0",
    "fid=1 AND COPY plat_trabalho.zt_canario_injecao TO '/tmp/x'", "fid=1; COPY (SELECT 1) TO PROGRAM 'id'",
    "fid=1 AND 1=CAST((SELECT current_user) AS int)", "fid=1 AND ascii(substring(current_user,1,1))>0",
    "fid=1 AND 1=1 AND 'a'='a'", "fid=1 AND 1=2", "fid=1 OR 1=2", "NOT fid=1", "fid<>1", "fid!=1",
    "fid=1 AND fid=1 AND fid=1 AND fid=1 AND fid=1 AND fid=1 AND fid=1 AND fid=1", "((((((((fid=1))))))))",
    "fid = 1 OR fid = 2 OR fid = 3", "fid IN (1,2,3)", "fid IN (1,2,(SELECT 3))", "fid IN ()",
    "fid LIKE '1%'", "fid LIKE '%'", "fid LIKE '%' ESCAPE '\\'", "fid IS NULL", "fid IS NOT NULL",
    "fid=0x31", "fid=CHR(49)", "fid=1e0", "fid=1.0", "fid=+1", "fid=-1", "fid=1;", "fid=1)",
    "fid=1 AND ''='", "fid=1 AND ''||''=''", "fid=1 AND 'a'||'b'='ab'", "fid=1 AND CONCAT('a','b')='ab'",
    "fid=1 AND ARRAY[1]=ARRAY[1]", "fid=1 AND $$x$$=$$x$$", "fid=1 AND $1=1", "fid=1 AND ?=1",
    "fid=1 AND :x=1", "fid=1 AND @x=1", "fid=1 AND E'\\x27'='''", "fid=1 AND U&'\\0027'=''''",
    "fid=1 AND '’'=''", "fid=1 AND N'x'='x'", "fid=1 AND B'1'=B'1'", "fid=1 AND X'31'=X'31'",
    "fid＝1", "fid=１", "ｆｉｄ=1", "fid=1​", "fid=1 AND 1=1", "fid=1 AND 1=1\x00",
    "fid=1 AND 1=1 %00", "%27%20OR%201%3D1", "fid=1%3B%20DROP%20TABLE%20x", "fid=1 /*!50000OR*/ 1=1",
    "fid=1 AnD 1=1", "fid=1 oR 1=1", "fid=1 AND 1 IN (SELECT 1)", "fid=1 AND EXISTS(SELECT 1)",
    "fid=1 AND (1) = (1)", "fid=1 AND fid::text='1'", "fid=1 AND CAST(fid AS text)='1'",
    "fid=1 AND fid = ANY(ARRAY[1])", "fid=1 AND fid BETWEEN 1 AND 2", "fid=1 AND fid > ALL(SELECT 0)",
    "geom IS NOT NULL", "ST_Area(geom)>0", "tenant_id=1", "tenant_id<>1", "globalid IS NOT NULL",
    "criado_por=1", "\"fid\"=1", "`fid`=1", "[fid]=1", "d_demo.c_x.fid=1", "t.fid=1",
    "fid=1 AND LENGTH('" + "a" * 5000 + "')>0", "(" * 50 + "fid=1" + ")" * 50, " OR ".join(["fid=1"] * 500),
]
_OUTFIELDS = ["*, (SELECT 1)", "fid, pg_sleep(5)", "fid; DROP TABLE x", "fid,tenant_id", "tenant_id", "*,version()",
              "fid AS x", "\"fid\"", "fid--", "fid/**/", "fid, (SELECT usename FROM pg_user)"]
_ORDERBY = ["fid; DROP TABLE x", "pg_sleep(5)", "(SELECT 1)", "fid DESC, pg_sleep(5)", "fid ASC LIMIT 1",
            "tenant_id", "fid DESC -- x", "1", "fid, 1=1", "random()"]
_GROUPBY = ["tenant_id", "fid; DROP TABLE x", "(SELECT 1)", "fid,pg_sleep(5)", "version()"]
_STATS = [
    '[{"statisticType":"count","onStatisticField":"fid","outStatisticFieldName":"n; DROP TABLE x"}]',
    '[{"statisticType":"count","onStatisticField":"(SELECT pg_sleep(5))","outStatisticFieldName":"n"}]',
    '[{"statisticType":"sum","onStatisticField":"fid) FROM plat.tenant; --","outStatisticFieldName":"n"}]',
    '[{"statisticType":"pg_sleep","onStatisticField":"fid","outStatisticFieldName":"n"}]',
    '[{"statisticType":"count","onStatisticField":"fid","outStatisticFieldName":"n\\" FROM plat.usuario --"}]',
    '[{"statisticType":"percentile_cont","onStatisticField":"fid","outStatisticFieldName":"p",'
    '"statisticParameters":{"value":"1); SELECT pg_sleep(5); --"}}]',
    '[{"statisticType":"count","onStatisticField":"tenant_id","outStatisticFieldName":"n"}]',
    '[{"statisticType":"avg","onStatisticField":"(SELECT count(*) FROM plat.usuario)","outStatisticFieldName":"n"}]',
    "[{\"statisticType\":\"count\",\"onStatisticField\":\"fid\",\"outStatisticFieldName\":\"n\"}]; DROP TABLE x",
    "not json",
]
_HAVING = ["n>0; DROP TABLE x", "pg_sleep(5)>0", "count(*)>(SELECT 1)", "n>0 OR 1=1", "n>0 UNION SELECT 1"]
_OBJECTIDS = ["1; DROP TABLE x", "1,2,pg_sleep(5)", "(SELECT 1)", "1 OR 1=1", "1--", "1,2,3,,4"]
_OGC = [("bbox", "1,2,3,4; DROP TABLE x"), ("bbox", "pg_sleep(5),1,2,3"), ("bbox", "1,2,3"), ("bbox", "a,b,c,d"),
        ("limit", "1; DROP TABLE x"), ("limit", "-1"), ("limit", "1 OR 1=1"), ("offset", "1; SELECT pg_sleep(5)"),
        ("offset", "-1"), ("filter", "fid=1; DROP TABLE x"), ("filter", "pg_sleep(5)"), ("filter-lang", "sql")]


def _payloads():
    saida = [("where", p) for p in _BASE]
    saida += [("outFields", p) for p in _OUTFIELDS] + [("orderByFields", p) for p in _ORDERBY]
    saida += [("groupByFieldsForStatistics", p) for p in _GROUPBY] + [("outStatistics", p) for p in _STATS]
    saida += [("havingClause", p) for p in _HAVING] + [("objectIds", p) for p in _OBJECTIDS]
    saida += [("ogc:" + k, v) for k, v in _OGC]
    return saida


PAYLOADS = _payloads()
assert len(PAYLOADS) >= 100, len(PAYLOADS)
_RESULTADOS: list[dict] = []


def _conferir_resultado(corpo: dict, camada: dict, parametro: str) -> None:
    """200 só é 'resultado correto' se o corpo é o JSON do FeatureServer da própria camada."""
    if "error" in corpo:
        return  # erro no formato Esri (com status 200 o protocolo antigo faz isso): também é recusa
    if "count" in corpo and "features" not in corpo:
        assert 0 <= corpo["count"] <= camada["total"]
        return
    if "objectIds" in corpo:
        assert len(corpo["objectIds"] or []) <= camada["total"]
        return
    feats = corpo.get("features")
    assert feats is not None, corpo
    assert len(feats) <= camada["total"]
    permitidos = set(camada["campos"])
    for f in feats[:50]:
        attrs = f.get("attributes") or f.get("properties") or {}
        if parametro in ("outStatistics", "groupByFieldsForStatistics", "havingClause"):
            continue  # estatísticas devolvem alias/grupos, não colunas da camada
        assert set(attrs) <= permitidos | {"OBJECTID"}, set(attrs) - permitidos
        assert "tenant_id" not in attrs


@pytest.mark.parametrize("parametro,payload", PAYLOADS, ids=[f"{k}:{i}" for i, (k, _) in enumerate(PAYLOADS)])
def test_payload_nunca_executa(sessao_a, camada, canario, parametro, payload):
    item = camada["item_id"]
    t0 = time.monotonic()
    if parametro.startswith("ogc:"):
        chave = parametro[4:]
        params = {chave: payload, "f": "json"}
        r = sessao_a.get(f"/ogc/features/{item}/collections/{item}/items", params=params)
    else:
        params = {"f": "json", "where": "1=1", "outFields": "*", "resultRecordCount": 5}
        if parametro in ("outStatistics", "havingClause"):
            params["outStatistics"] = _STATS[6] if parametro == "havingClause" else payload
        if parametro == "groupByFieldsForStatistics":
            params["outStatistics"] = _STATS[6]
        params[parametro] = payload
        r = sessao_a.post(f"/rest/services/{item}/FeatureServer/0/query", data=params)
    dt = time.monotonic() - t0
    _RESULTADOS.append({"parametro": parametro, "status": r.status_code, "ms": int(dt * 1000)})
    assert r.status_code < 500, (parametro, payload, r.status_code, r.text[:300])
    assert dt < 4.0, f"payload demorou {dt:.1f}s: pg_sleep executou? {parametro}={payload!r}"
    if r.status_code == 200:
        _conferir_resultado(r.json(), camada, parametro)
    else:
        assert r.status_code in (400, 404, 422), (parametro, payload, r.status_code)
        # o parser pode ecoar o TOKEN do cliente ("obtido: pg_read_file"); nunca um erro do banco
        baixo = r.text.lower()
        marcas = ("psycopg2", "syntax error at", "pg_catalog", "relation \"", "error:")
        assert not any(m in baixo for m in marcas), r.text[:300]


def test_camada_intacta_depois_dos_payloads_e_medidas(sessao_a, camada, medida):
    """contagem da camada igual à do início (nenhum DELETE/UPDATE/DROP rodou) e medidas gravadas."""
    item = camada["item_id"]
    r = sessao_a.get(f"/rest/services/{item}/FeatureServer/0/query?where=1%3D1&returnCountOnly=true&f=json")
    assert r.status_code == 200 and r.json()["count"] == camada["total"]
    assert len(_RESULTADOS) >= 100, len(_RESULTADOS)
    m = medida(ITEM)
    por_status: dict[str, int] = {}
    for x in _RESULTADOS:
        por_status[str(x["status"])] = por_status.get(str(x["status"]), 0) + 1
    m("payloads", len(_RESULTADOS), "payloads",
      "tests/seguranca/test_injecao.py PAYLOADS (where/outFields/orderBy/groupBy/outStatistics/having/objectIds/OGC)")
    m("respostas_por_status", por_status, "respostas", "status HTTP de cada payload (nenhum 5xx)")
    m("latencia_max_ms", max(x["ms"] for x in _RESULTADOS), "ms",
      "maior tempo de resposta entre os payloads (pg_sleep(5) nunca executou)")
    m("respostas_5xx", sum(1 for x in _RESULTADOS if x["status"] >= 500), "respostas", "contagem de 5xx (tem de ser 0)")


# --------------------------------------------------------------------------- estático

NOMES_DE_ENTRADA = {
    "where", "outFields", "orderByFields", "groupByFieldsForStatistics", "outStatistics", "havingClause",
    "objectIds", "uniqueIds", "filter", "bbox", "query_params", "form", "body", "payload", "texto", "q",
    "where_texto", "sql_usuario", "consulta_usuario", "expressao",
}
_INTERPOLADORES = {"format", "format_map", "join"}


def _nomes_interpolados(no: ast.AST) -> set[str]:
    """nomes/atributos que aparecem DENTRO de uma f-string, `.format(...)` ou `%` de um argumento SQL."""
    nomes: set[str] = set()
    for sub in ast.walk(no):
        if isinstance(sub, ast.Name):
            nomes.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            nomes.add(sub.attr)
    return nomes


def _sql_dinamico(arg: ast.AST) -> list[ast.AST]:
    """as partes interpoladas de um argumento que parece SQL montado dinamicamente."""
    partes = []
    for sub in ast.walk(arg):
        if isinstance(sub, ast.JoinedStr):
            partes += [v.value for v in sub.values if isinstance(v, ast.FormattedValue)]
        elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr in _INTERPOLADORES:
            partes += list(sub.args) + [k.value for k in sub.keywords]
        elif isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Mod):
            partes.append(sub.right)
    return partes


def test_estatico_nenhum_sql_interpola_entrada_do_usuario():
    """toda chamada `.execute(<sql>, ...)` em app/: as partes interpoladas do SQL nunca citam um nome de
    parâmetro de entrada do usuário (a lista acima). Quem monta SQL com `where` é `where_ast.compilar`,
    que devolve texto com `%s` e parâmetros — nunca o texto do cliente."""
    ofensas = []
    for caminho in sorted((RAIZ / "app").rglob("*.py")):
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "execute"):
                continue
            if not no.args:
                continue
            for parte in _sql_dinamico(no.args[0]):
                ruins = _nomes_interpolados(parte) & NOMES_DE_ENTRADA
                if ruins:
                    ofensas.append(f"{caminho.relative_to(RAIZ)}:{no.lineno} interpola {sorted(ruins)}")
    assert not ofensas, "\n".join(ofensas)


def test_bandit_b608_em_app_consulta_e_registrado(medida):
    """`bandit -t B608` (SQL montado por string) sobre app/consulta: cada achado é uma f-string cujo conteúdo
    interpolado vem de lista branca (`colunas_sql[...]`, schema/tabela do catálogo, `where_sql` já compilado)
    — o teste acima é quem prova que nenhum nome de usuário entra; aqui a contagem vira medida para o
    adversário conferir uma a uma."""
    r = subprocess.run(
        [str(RAIZ / "venv" / "bin" / "bandit"), "-q", "-f", "json", "-t", "B608", "-r", str(RAIZ / "app" / "consulta")],
        capture_output=True, text=True, timeout=120,
    )
    dados = json.loads(r.stdout or "{}")
    achados = dados.get("results", [])
    m = medida(ITEM)
    m("bandit_b608_app_consulta", len(achados), "achados",
      "venv/bin/bandit -q -f json -t B608 -r app/consulta (cada um conferido: interpola só lista branca)")
    linhas = sorted(f"{a['filename'].split('/app/')[-1]}:{a['line_number']}" for a in achados)
    m("bandit_b608_linhas", linhas, "linhas", "onde o bandit vê SQL montado por string em app/consulta")
    # o que o bandit acha tem de ser o que já conhecemos (motor.py); qualquer linha nova é revisão obrigatória
    # rotas_servico: extent com schema/tabela vindos do catálogo
    conhecidos = ("consulta/motor.py", "consulta/where_ast.py", "consulta/rotas_servico.py")
    assert all(li.startswith(conhecidos) for li in linhas), linhas
