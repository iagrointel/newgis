"""Exportação para pandapower/MATPOWER e importação de caso MATPOWER (item L4-05-c).

Cláusulas do portão provadas aqui:

* `GET .../subrede/{nome}/exportar?formato=pandapower` devolve `rede.json`, `resumo.json` e `NAO_FAZ.md`
  num zip, e o número de `bus`/`line`/`trafo` bate com nós, trechos e transformadores contados por
  consulta INDEPENDENTE ao banco — `test_exportar_pandapower_conta_bus_line_trafo`;
* `formato=matpower` devolve o `.m` do caseformat 2 do mesmo alimentador —
  `test_exportar_matpower_devolve_o_caso`;
* importar o caso público `case9`/`case30` cria uma rede de TRANSMISSÃO e o traçado funciona sobre ela —
  `test_importar_caso_publico_e_tracar`;
* paridade escrita como CONECTOR: `docs/PARIDADE.md` diz que estes formatos são troca com outro motor,
  não capacidade equivalente de um produto concorrente — `test_paridade_fala_em_conector`.

Refutação (papel adversário), provada aqui:
* `test_barra_importada_fica_sem_geometria`: a barra do caso MATPOWER, que não tem coordenada nenhuma,
  vira objeto NÃO ESPACIAL (`geom` nulo) e nunca um ponto em (0, 0);
* `test_importar_sem_o_pacote_de_transmissao_e_recusado` e `test_caso_invalido_e_recusado_com_a_linha`;
* `test_formato_desconhecido_e_recusado`.
"""

import io
import json
import zipfile
from pathlib import Path

import psycopg2
import pytest

from app import db as banco
from app.rede_utilidades import instalados
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rede_opendss import (
    CTMT,
    _alimentador,
    _atualizar_tudo,
    _conferencia_independente,
    _criar_rede,
)
from tests.api.test_rls import ids_por_slug

ITEM = "L4-05-c-pandapower-e-matpower"
MEDIDAS = Path(__file__).resolve().parents[1] / "medidas" / f"{ITEM}.json"
DADOS = Path(__file__).resolve().parents[1] / "dados"


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _pasta(resposta) -> dict:
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resposta.content)) as z:
        return {n.split("/", 1)[1]: z.read(n).decode("utf-8") for n in z.namelist()}


def _contexto(env, sessao):
    eu = sessao.get("/api/eu").json()
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    tenant_id = ids_por_slug(con)[eu["inquilino"]["slug"]]
    con.close()
    return tenant_id, banco.Contexto(tenant_id, int(eu["id"]), "teste-l405c")


def _rede_de_transmissao(sessao, sufixo, limpar):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-mpc-{sufixo}",
                                       "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append(rid)
    r = sessao.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("transmissao-matpower"),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    return rid


def _importar(sessao, rid, nome_do_caso, prefixo="", corpo=None):
    """O `Content-Type: application/json` é exigência da defesa contra CSRF da casa
    (`auth.sessao.checar_escrita_sob_cookie`): sob cookie, todo corpo de escrita tem de se declarar
    JSON. É a mesma chamada de `POST .../pacote`, que também recebe bytes crus."""
    if corpo is None:
        corpo = (DADOS / f"matpower_{nome_do_caso}.m").read_bytes()
    return sessao.post(f"/api/rede/{rid}/matpower?prefixo={prefixo}", content=corpo,
                       headers={"Content-Type": "application/json"})


# --- cláusula: exportação para pandapower, com as contagens conferidas -------------------------------

def test_exportar_pandapower_conta_bus_line_trafo(sessao_a, env, limpar_redes):
    rid = _criar_rede(sessao_a, "pp", limpar_redes)
    _alimentador(sessao_a, rid)
    _atualizar_tudo(sessao_a, env, rid)

    arquivos = _pasta(sessao_a.get(
        f"/api/rede/{rid}/subrede/{CTMT}/exportar?formato=pandapower&jusante=true"))
    assert set(arquivos) == {"rede.json", "NAO_FAZ.md", "resumo.json"}
    resumo = json.loads(arquivos["resumo.json"])
    net = json.loads(arquivos["rede.json"])
    assert net["_class"] == "pandapowerNet"

    esperado = _conferencia_independente(env, sessao_a, rid, com_jusante=True)
    c = resumo["pandapower"]
    conferencia = resumo["conferencia"]
    assert conferencia["nos_da_subrede"] == esperado["nos"], (conferencia, esperado)
    assert conferencia["trechos_da_subrede"] == esperado["trechos"], (conferencia, esperado)
    # bus = nós menos as fusões por chave fechada; line = trechos; trafo = transformadores
    assert c["bus"] == esperado["nos"] - conferencia["fusoes_por_chave_fechada"], c
    assert c["bus"] == c["barras_esperadas"], c
    assert c["line"] == c["linhas_esperadas"] == esperado["trechos"], (c, esperado)
    assert c["trafo"] == c["transformadores_esperados"] == 1, c
    assert c["load"] >= 1 and c["sgen"] >= 1 and c["ext_grid"] == 1, c
    # a tabela de barras do arquivo tem exatamente essa quantidade de linhas
    assert len(json.loads(net["_object"]["bus"]["_object"])["data"]) == c["bus"]
    assert "não faz" in arquivos["NAO_FAZ.md"]
    assert "equilibrado" in arquivos["NAO_FAZ.md"] or "EQUILIBRADO" in arquivos["NAO_FAZ.md"]

    MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
    registro = json.loads(MEDIDAS.read_text(encoding="utf-8")) if MEDIDAS.exists() else {}
    registro["exportacao_pandapower"] = {"conferencia_independente": esperado, "pandapower": c}
    MEDIDAS.write_text(json.dumps(registro, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def test_exportar_matpower_devolve_o_caso(sessao_a, env, limpar_redes):
    from app.rede_utilidades import matpower

    rid = _criar_rede(sessao_a, "mp", limpar_redes)
    _alimentador(sessao_a, rid)
    _atualizar_tudo(sessao_a, env, rid)

    arquivos = _pasta(sessao_a.get(
        f"/api/rede/{rid}/subrede/{CTMT}/exportar?formato=matpower&jusante=true"))
    nome_m = [n for n in arquivos if n.endswith(".m")]
    assert len(nome_m) == 1, arquivos.keys()
    caso = matpower.ler_caso(arquivos[nome_m[0]])
    resumo = json.loads(arquivos["resumo.json"])
    assert caso["versao"] == "2" and caso["baseMVA"] == 100.0
    assert len(caso["bus"]) == resumo["matpower"]["bus"] == resumo["matpower"]["barras_esperadas"]
    assert len(caso["branch"]) == resumo["matpower"]["ramos_esperados"]
    assert len(caso["gen"]) == 1
    tipos = [matpower.coluna(b, matpower.COLUNAS_BUS, "type") for b in caso["bus"]]
    assert tipos.count(3.0) == 1, "exatamente uma barra de referência"


def test_formato_desconhecido_e_recusado(sessao_a, env, limpar_redes):
    rid = _criar_rede(sessao_a, "fmt", limpar_redes)
    _alimentador(sessao_a, rid)
    _atualizar_tudo(sessao_a, env, rid)
    r = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/exportar?formato=pypsa")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "formato_desconhecido"


# --- cláusula: importar caso público e traçar --------------------------------------------------------

@pytest.mark.parametrize("caso,barras,ramos", [("case9", 9, 9), ("case30", 30, 41)])
def test_importar_caso_publico_e_tracar(sessao_a, env, limpar_redes, caso, barras, ramos):
    rid = _rede_de_transmissao(sessao_a, caso, limpar_redes)
    r = _importar(sessao_a, rid, caso)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["versao_do_caseformat"] == "2"
    c = corpo["contagens"]
    assert c["barras_no_caso"] == c["barras_gravadas"] == barras, c
    assert c["ramos_no_caso"] == c["ramos_gravados"] == ramos, c
    assert c["barras_sem_geometria"] == barras, c
    assert c["comprimento_declarado"] is False
    assert c["barras_com_geracao"] >= 1

    tenant_id, contexto = _contexto(env, sessao_a)
    with banco.db(contexto) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.rede_no WHERE rede_id = %s::uuid", (rid,))
        assert cur.fetchone()["n"] == barras
        cur.execute("SELECT count(*) AS n FROM plat.rede_no WHERE rede_id = %s::uuid "
                    "AND papel = 'fonte'", (rid,))
        assert cur.fetchone()["n"] >= 1
        # traçado: menor caminho entre a barra de referência e a barra mais distante do caso
        cur.execute("SELECT id, codigo_externo FROM plat.rede_no WHERE rede_id = %s::uuid "
                    "ORDER BY codigo_externo", (rid,))
        nos = {r["codigo_externo"]: str(r["id"]) for r in cur.fetchall()}
        de, para = nos["bus1"], nos[f"bus{barras}"]
        cur.execute("SELECT plat.rede_menor_caminho(%s::uuid, %s::uuid, %s::uuid) AS r",
                    (rid, de, para))
        caminho = cur.fetchone()["r"]
    assert caminho["encontrado"] is True, caminho
    assert len(caminho["arestas"]) >= 1, caminho
    # o caseformat não traz comprimento: o traçado custa zero e CONTA quantos ramos entraram assim
    assert caminho["custo_m"] == 0 and caminho["ramais_sem_custo"] == len(caminho["arestas"]), caminho

    MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
    registro = json.loads(MEDIDAS.read_text(encoding="utf-8")) if MEDIDAS.exists() else {}
    registro.setdefault("importacao_matpower", {})[caso] = {
        "contagens": c, "arestas_no_caminho": len(caminho["arestas"]),
        "ramos_sem_comprimento_no_caminho": caminho["ramais_sem_custo"]}
    MEDIDAS.write_text(json.dumps(registro, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def test_barra_importada_fica_sem_geometria(sessao_a, env, limpar_redes):
    """A refutação do item: barra sem coordenada tem de virar objeto NÃO ESPACIAL, não ponto (0, 0)."""
    rid = _rede_de_transmissao(sessao_a, "geo", limpar_redes)
    assert _importar(sessao_a, rid, "case9").status_code == 201
    tenant_id, contexto = _contexto(env, sessao_a)
    with banco.db(contexto) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.rede_no WHERE rede_id = %s::uuid "
                    "AND geom IS NOT NULL", (rid,))
        assert cur.fetchone()["n"] == 0
        cur.execute("SELECT count(*) AS n FROM plat.rede_aresta WHERE rede_id = %s::uuid "
                    "AND (geom IS NOT NULL OR comprimento_m IS NOT NULL)", (rid,))
        assert cur.fetchone()["n"] == 0
        # e nenhuma barra virou feição de ponto (a tabela de feição exige geometria)
        cur.execute("SELECT count(*) AS n FROM plat.rede_feicao_ponto WHERE rede_id = %s::uuid", (rid,))
        assert cur.fetchone()["n"] == 0
        # o grupo do pacote diz a mesma coisa que a tabela
        cur.execute("SELECT codigo, geometria FROM plat.rede_grupo WHERE rede_id = %s::uuid "
                    "ORDER BY codigo", (rid,))
        grupos = {r["codigo"]: r["geometria"] for r in cur.fetchall()}
    assert grupos == {"barra": "sem_geometria", "ramo": "sem_geometria"}


def test_dois_casos_na_mesma_rede_por_prefixo(sessao_a, limpar_redes):
    rid = _rede_de_transmissao(sessao_a, "prefixo", limpar_redes)
    assert _importar(sessao_a, rid, "case9", "a-").status_code == 201
    r = _importar(sessao_a, rid, "case9", "b-")
    assert r.status_code == 201, r.text
    assert r.json()["contagens"]["barras_gravadas"] == 9
    # reimportar o mesmo caso com o mesmo prefixo não duplica
    r = _importar(sessao_a, rid, "case9", "a-")
    assert r.status_code == 201 and r.json()["contagens"]["barras_gravadas"] == 9


# --- refutação --------------------------------------------------------------------------------------

def test_importar_sem_o_pacote_de_transmissao_e_recusado(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "sempacote", limpar_redes)      # rede com o pacote de distribuição
    r = _importar(sessao_a, rid, "case9")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "pacote_de_transmissao_ausente"


def test_caso_invalido_e_recusado_com_a_linha(sessao_a, limpar_redes):
    rid = _rede_de_transmissao(sessao_a, "invalido", limpar_redes)
    r = _importar(sessao_a, rid, None, corpo=b"mpc.baseMVA = 100;\nmpc.bus = [\n1 3 tres;\n];\n")
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "valor_nao_numerico", corpo
    assert corpo["detalhe"][0]["linha"] == 3, corpo


def test_corpo_vazio_e_recusado(sessao_a, limpar_redes):
    rid = _rede_de_transmissao(sessao_a, "vazio", limpar_redes)
    r = sessao_a.post(f"/api/rede/{rid}/matpower", content=b" ",
                      headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["erro"] == "caso_vazio", r.text


def test_rede_inexistente_da_404_antes_de_ler_o_corpo(sessao_a):
    r = sessao_a.post("/api/rede/00000000-0000-0000-0000-000000000000/matpower",
                      content=b"lixo que nao e caseformat",
                      headers={"Content-Type": "application/json"})
    assert r.status_code == 404, r.text


# --- cláusula: paridade escrita como conector --------------------------------------------------------

def test_paridade_fala_em_conector():
    texto = (Path(__file__).resolve().parents[2] / "docs" / "PARIDADE.md").read_text(encoding="utf-8")
    assert "pandapower" in texto and "MATPOWER" in texto
    trecho = texto[texto.index("pandapower") - 2000:texto.index("pandapower") + 2000]
    assert "conector" in trecho.lower(), "a paridade tem de dizer CONECTOR, não capacidade equivalente"
