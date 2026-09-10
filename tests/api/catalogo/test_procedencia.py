"""Procedência do item de dado pela API (item L0-09-a-procedencia).

Cláusulas do portão provadas aqui: a ficha e a lista mostram o bloco e a pontuação; a busca filtra por
licença e por pontuação; a exportação leva a procedência. A refutação do adversário sobre licença vazia
(vira NULL, nunca string vazia) está em `test_licenca_vazia_vira_nulo_*`; a parte de sha256 (mesmo arquivo
duas vezes, 1 byte diferente) fica em `tests/api/ingestao/test_procedencia_ingestao.py`, onde há arquivo de
verdade sendo importado.
"""

import json

import pytest

from app.catalogo import procedencia
from tests.api.catalogo.conftest import titulo_zt
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L0-09-a-procedencia"


def _contexto_admin(con, slug: str = "demo") -> None:
    """`contexto()` com o usuario_id REAL do admin: plat.item.p_item_ler exige `plat.pode_ler(id)`, que é
    falso para usuario_id=0 em item privado."""
    ids = ids_por_slug(con)
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        adm = cur.fetchone()["usuario_id"]
    contexto(con, ids[slug], usuario_id=adm, login="admin")

BLOCO_CHEIO = {
    "fonte": "Malha municipal IBGE",
    "url": "https://geoftp.ibge.gov.br/exemplo",
    "licenca": "CC BY 4.0",
    "data_do_dado": "2024-07-01",
    "data_de_acesso": "2026-09-06",
    "gerador": "plat teste v1",
    "sha256": "a" * 64,
    "comando_reexecucao": "sha256sum malha.gpkg",
    "metodo": "ogr2ogr + ST_MakeValid",
    "confianca": "alta: arquivo oficial, hash conferido",
    "limites": ["não serve para medir área abaixo de 1 ha"],
    "frescor": "anual",
    "proxima_verificacao": "2027-01-31",
    "responsavel": "equipe de dados",
    "origem": {"licenca": "declarado", "sha256": "medido", "metodo": "medido"},
}


def _camada(itens_a, **procedencia_bloco):
    dados = {
        "schema": "plat_trabalho",
        "tabela": "zt_inexistente",
        "geometria": "Point",
        "srid": 4326,
        "campos": [{"nome": "a", "tipo": "text"}],
        "fonte": "hospedada",
    }
    if procedencia_bloco:
        dados["procedencia"] = procedencia_bloco["bloco"]
    return itens_a.criar("camada_vetorial", dados=dados)


# ---------------------------------------------------------------- ficha e pontuação
def test_ficha_do_item_traz_bloco_e_pontuacao(itens_a, sessao_a, medida):
    it = _camada(itens_a, bloco=dict(BLOCO_CHEIO))
    r = sessao_a.get(f"/api/itens/{it['id']}")
    assert r.status_code == 200, r.text
    j = r.json()
    bloco = j["dados"]["procedencia"]
    assert bloco["licenca"] == "CC BY 4.0"
    assert bloco["origem"] == {"licenca": "declarado", "sha256": "medido", "metodo": "medido"}
    assert j["procedencia"]["pontuacao"] == 10.0
    assert j["procedencia"]["campos"] == 10
    assert j["procedencia"]["campos_possiveis"] == 10
    assert j["procedencia"]["completude_texto"] == "10,0/10"
    assert j["procedencia"]["licenca"] == "CC BY 4.0"
    medida(ITEM)(
        "pontuacao_bloco_cheio", j["procedencia"]["pontuacao"], "0-10",
        "pytest tests/api/catalogo/test_procedencia.py::test_ficha_do_item_traz_bloco_e_pontuacao",
    )


def test_item_sem_bloco_tem_pontuacao_nula_na_ficha_e_na_lista(itens_a, sessao_a):
    it = _camada(itens_a)
    j = sessao_a.get(f"/api/itens/{it['id']}").json()
    assert j["procedencia"]["pontuacao"] is None
    assert j["procedencia"]["completude_texto"] is None
    lista = sessao_a.get("/api/itens", params={"q": f'titulo:"{it["titulo"]}"'}).json()
    assert lista["itens"], lista
    assert lista["itens"][0]["procedencia"]["pontuacao"] is None


def test_lista_traz_a_pontuacao_sem_pedido_por_item(itens_a, sessao_a):
    it = _camada(itens_a, bloco={"licenca": "ODbL", "sha256": "b" * 64, "metodo": "ogr2ogr"})
    lista = sessao_a.get("/api/itens", params={"q": f'titulo:"{it["titulo"]}"'}).json()
    achado = [x for x in lista["itens"] if x["id"] == it["id"]]
    assert achado, lista
    assert achado[0]["procedencia"]["pontuacao"] == 3.0
    assert achado[0]["procedencia"]["licenca"] == "ODbL"


# ---------------------------------------------------------------- refutação: vazio vira NULL
def test_licenca_vazia_vira_nulo_na_criacao(itens_a, sessao_a):
    """Refutação do adversário: 'licença' com texto vazio vira NULL, não string vazia."""
    it = _camada(itens_a, bloco={"licenca": "", "fonte": "   ", "sha256": "c" * 64})
    j = sessao_a.get(f"/api/itens/{it['id']}").json()
    bloco = j["dados"]["procedencia"]
    assert bloco["licenca"] is None and bloco["licenca"] != ""
    assert bloco["fonte"] is None
    assert j["procedencia"]["pontuacao"] == 1.0  # só o sha256
    assert j["procedencia"]["licenca"] is None


def test_licenca_vazia_vira_nulo_na_edicao(itens_a, sessao_a):
    it = _camada(itens_a, bloco=dict(BLOCO_CHEIO))
    dados = sessao_a.get(f"/api/itens/{it['id']}").json()["dados"]
    dados["procedencia"]["licenca"] = "   "
    r = sessao_a.put(f"/api/itens/{it['id']}", json={"dados": dados})
    assert r.status_code == 200, r.text
    j = sessao_a.get(f"/api/itens/{it['id']}").json()
    assert j["dados"]["procedencia"]["licenca"] is None
    assert j["procedencia"]["pontuacao"] == 9.0


def test_licenca_vazia_nao_aparece_como_licenca_no_filtro(itens_a, sessao_a):
    it = _camada(itens_a, bloco={"licenca": "", "sha256": "d" * 64})
    r = sessao_a.get("/api/itens", params={"q": f'titulo:"{it["titulo"]}"', "licenca": "nenhuma"})
    assert it["id"] in [x["id"] for x in r.json()["itens"]]


def test_origem_invalida_e_422(itens_a, sessao_a):
    dados = {
        "schema": "plat_trabalho", "tabela": "zt_inexistente", "geometria": "Point", "srid": 4326,
        "campos": [{"nome": "a", "tipo": "text"}], "fonte": "hospedada",
        "procedencia": {"licenca": "CC BY", "origem": {"licenca": "achismo"}},
    }
    r = sessao_a.post("/api/itens", json={"tipo": "camada_vetorial", "titulo": titulo_zt("camada"), "dados": dados})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "procedencia_invalida"


# ---------------------------------------------------------------- busca e filtro
def test_busca_por_licenca_e_por_pontuacao(itens_a, sessao_a):
    alto = _camada(itens_a, bloco=dict(BLOCO_CHEIO))
    baixo = _camada(itens_a, bloco={"licenca": "uso interno", "sha256": "e" * 64})
    ids_alto = lambda r: [x["id"] for x in r.json()["itens"]]  # noqa: E731

    r = sessao_a.get("/api/itens", params={"q": "licenca:CC"})
    assert alto["id"] in ids_alto(r) and baixo["id"] not in ids_alto(r)

    r = sessao_a.get("/api/itens", params={"q": "procedencia:[9 TO 10]"})
    assert alto["id"] in ids_alto(r) and baixo["id"] not in ids_alto(r)

    r = sessao_a.get("/api/itens", params={"q": "procedencia:[0 TO 3]"})
    assert baixo["id"] in ids_alto(r) and alto["id"] not in ids_alto(r)

    r = sessao_a.get("/api/itens", params={"procedencia_min": 9})
    assert alto["id"] in ids_alto(r) and baixo["id"] not in ids_alto(r)

    r = sessao_a.get("/api/itens", params={"licenca": "CC BY 4.0"})
    assert alto["id"] in ids_alto(r) and baixo["id"] not in ids_alto(r)


def test_pontuacao_fora_de_faixa_e_422(sessao_a):
    r = sessao_a.get("/api/itens", params={"q": "procedencia:[0 TO 42]"})
    assert r.status_code == 422 and r.json()["erro"] == "campo_invalido"
    r = sessao_a.get("/api/itens", params={"procedencia_min": 11})
    assert r.status_code == 422 and r.json()["erro"] == "campo_invalido"


def test_faceta_de_licenca_conta_o_que_nao_tem_licenca(itens_a, sessao_a):
    it = _camada(itens_a, bloco={"licenca": "CC BY-SA 4.0", "sha256": "f" * 64})
    r = sessao_a.get("/api/itens/facetas", params={"q": f'titulo:"{it["titulo"]}"'})
    assert r.status_code == 200, r.text
    valores = {x["valor"]: x["n"] for x in r.json()["licenca"]}
    assert valores.get("CC BY-SA 4.0") == 1


# ---------------------------------------------------------------- paridade Python x SQL
def test_pontuacao_do_python_e_do_sql_sao_a_mesma(conexao_plat_app, env, medida):
    """A conta existe em dois lugares (app/catalogo/procedencia.py e plat.procedencia_pontuacao); se as duas
    divergirem, a tela mostra um número e a busca filtra por outro."""
    casos = [
        dict(BLOCO_CHEIO),
        {"licenca": "", "sha256": "a"},
        {"limites": []},
        {"limites": ["um aviso"]},
        {"data_dado": "2024", "script_gerador": "carga.py", "fonte_url": "https://x.gov.br"},
        {c: "x" for c in procedencia.CAMPOS_PONTUADOS[:7]},
        {},
    ]
    _contexto_admin(conexao_plat_app, "demo")
    divergentes = []
    with conexao_plat_app.cursor() as cur:
        for bloco in casos:
            normalizado = procedencia.normalizar(bloco)
            dados = json.dumps({"procedencia": normalizado}, ensure_ascii=False)
            cur.execute(
                "SELECT plat.procedencia_pontuacao(%s::jsonb) AS p, plat.procedencia_campos(%s::jsonb) AS c",
                (dados, dados),
            )
            r = cur.fetchone()
            py_p = procedencia.pontuacao(normalizado)
            py_c = procedencia.campos_preenchidos(normalizado) if normalizado else 0
            sql_p = None if r["p"] is None else float(r["p"])
            if (sql_p, r["c"]) != (py_p, py_c):
                divergentes.append((bloco, (sql_p, r["c"]), (py_p, py_c)))
    assert not divergentes, divergentes
    medida(ITEM)(
        "casos_paridade_python_sql", len(casos), "blocos",
        "pytest tests/api/catalogo/test_procedencia.py::test_pontuacao_do_python_e_do_sql_sao_a_mesma",
    )


@pytest.fixture(scope="module")
def corpus(env):
    """O mesmo corpus de 10 mil itens do L0-03 (tests/api/semear_catalogo.py); a semeadura é idempotente."""
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.semear_catalogo import semear

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        semear(con, "demo", 10_000)
    finally:
        con.close()
    return True


def test_selo_na_lista_nao_estoura_o_portao_de_100_ms(sessao_a, corpus, medida):
    """O selo de procedência de cada linha é calculado no banco (plat.procedencia_resumo) e entra na MESMA
    consulta da lista. Medido no corpus de 10 mil itens: a primeira versão, encadeando uma função por campo,
    levava a lista de 50 itens a 288 ms (o portão do L0-03 é 100 ms); a versão de uma expressão só, não.
    """
    import statistics
    import time

    tempos = []
    for _ in range(20):
        t0 = time.monotonic()
        r = sessao_a.get("/api/itens", params={"tipo": "mapa", "limite": 50})
        tempos.append((time.monotonic() - t0) * 1000)
        assert r.status_code == 200, r.text
    assert r.json()["itens"][0]["procedencia"]["campos_possiveis"] == 10
    tempos.sort()
    p95 = round(tempos[int(len(tempos) * 0.95) - 1], 1)
    medida(ITEM)(
        "lista_50_itens_com_selo_p95_ms", p95, "ms",
        "GET /api/itens?tipo=mapa&limite=50, 20 execuções, corpus 10 mil "
        f"(mediana {round(statistics.median(tempos), 1)})",
    )
    assert p95 < 100, p95


# ---------------------------------------------------------------- exportação
def test_exportacao_leva_a_procedencia(itens_a, conexao_plat_app, medida):
    """Cláusula 'exportação leva a procedência', provada na exportação que existe hoje (job
    catalogo.exportar_lista, csv e json). A exportação do inquilino inteiro em GeoPackage é o item
    L0-06-d-exportar-inquilino, ainda PENDENTE — está escrito assim em docs/PROCEDENCIA.md."""
    from app.catalogo import tarefas

    it = _camada(itens_a, bloco=dict(BLOCO_CHEIO))
    _contexto_admin(conexao_plat_app, "demo")
    with conexao_plat_app.cursor() as cur:
        linhas = tarefas.linhas_exportacao(cur, [it["id"]])
    assert len(linhas) == 1, linhas
    linha = linhas[0]
    assert linha["licenca"] == "CC BY 4.0"
    assert float(linha["procedencia_pontuacao"]) == 10.0
    assert linha["procedencia_campos"] == 10
    assert linha["procedencia_sha256"] == "a" * 64
    assert linha["procedencia_gerador"] == "plat teste v1"

    csv_bytes, ct = tarefas.serializar_exportacao(linhas, "csv")
    cabecalho = csv_bytes.decode("utf-8").splitlines()[0]
    for coluna in ("licenca", "procedencia_pontuacao", "procedencia_sha256", "procedencia_gerador"):
        assert coluna in cabecalho
    assert ct == "text/csv"

    json_bytes, ct = tarefas.serializar_exportacao(linhas, "json")
    saida = json.loads(json_bytes.decode("utf-8"))
    assert saida[0]["procedencia"]["comando_reexecucao"] == "sha256sum malha.gpkg"
    assert ct == "application/json"
    medida(ITEM)(
        "colunas_procedencia_na_exportacao", 5, "colunas",
        "pytest tests/api/catalogo/test_procedencia.py::test_exportacao_leva_a_procedencia",
    )


# ---------------------------------------------------------------- todo item de dado aceita o bloco
@pytest.mark.parametrize("tipo", ["camada_vetorial", "arquivo", "cena"])
def test_tipos_de_dado_aceitam_o_bloco(itens_a, sessao_a, tipo):
    from tests.api.catalogo.conftest import DADOS_POR_TIPO

    dados = dict(DADOS_POR_TIPO[tipo])
    dados["procedencia"] = {"licenca": "CC BY 4.0", "sha256": "0" * 64, "metodo": "carga manual"}
    it = itens_a.criar(tipo, dados=dados)
    j = sessao_a.get(f"/api/itens/{it['id']}").json()
    assert j["procedencia"]["pontuacao"] == 3.0
