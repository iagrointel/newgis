"""Item L2-07-b: importar XLSForm cria o item `formulario` e as camadas; responder grava a feição pela porta única
de escrita; restrição violada não grava nada; repetição grava N linhas na camada filha com `pai_globalid`; campo
não relevante vai NULL; cascata de 3 níveis e cálculos vêm do servidor; cálculo circular é 422; isolamento A->B."""

import base64
from pathlib import Path

import pytest

from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug

XLSFORMS = Path(__file__).resolve().parents[1] / "coleta" / "xlsforms"


def _b64(nome: str) -> str:
    return base64.b64encode((XLSFORMS / nome).read_bytes()).decode("ascii")


def _importar(sessao, nome: str, **extra):
    r = sessao.post("/api/formularios/xlsform", json={"nome": nome, "conteudo": _b64(nome),
                                                      "titulo": f"{PREFIXO_TESTE} {nome}"} | extra)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def limpeza(conexao_plat_app):
    """Apaga as camadas e formulários `zt` criados pelo teste (tabelas físicas + itens)."""
    yield
    ids = ids_por_slug(conexao_plat_app)
    admin = _admin_id(conexao_plat_app, "demo")
    contexto(conexao_plat_app, ids["demo"], usuario_id=admin, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT id, tipo, dados FROM plat.item WHERE titulo LIKE %s AND tipo IN ('formulario', "
                    "'camada_vetorial')", (f"{PREFIXO_TESTE} %",))
        for r in cur.fetchall():
            d = r["dados"] or {}
            if r["tipo"] == "camada_vetorial" and d.get("schema") and d.get("tabela"):
                cur.execute(f'DROP TABLE IF EXISTS "{d["schema"]}"."{d["tabela"]}" CASCADE')
            cur.execute("DELETE FROM plat.item WHERE id = %s", (r["id"],))
    conexao_plat_app.commit()


def _admin_id(con, slug):
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        return cur.fetchone()["usuario_id"]


def _linhas(con, camada_dados: dict) -> list[dict]:
    contexto(con, ids_por_slug(con)["demo"], usuario_id=_admin_id(con, "demo"), login="admin")
    with con.cursor() as cur:
        cur.execute(f'SELECT * FROM "{camada_dados["schema"]}"."{camada_dados["tabela"]}" ORDER BY fid')
        return cur.fetchall()


def _camada(sessao, item_id: str) -> dict:
    r = sessao.get(f"/api/itens/{item_id}")
    assert r.status_code == 200, r.text
    return r.json()["dados"]


def test_importa_os_cinco_xlsforms_de_teste(sessao_a, limpeza):
    for nome in ("basico.xlsx", "regras.xlsx", "calculos.xlsx", "cascata.xlsx", "repeticao.xlsx"):
        f = _importar(sessao_a, nome)
        doc = f["documento"]
        assert doc["camada_destino"] and doc["campos"]
        g = sessao_a.get(f"/api/formularios/{f['id']}")
        assert g.status_code == 200 and g.json()["documento"]["nome"] == doc["nome"]


def test_calculo_circular_e_recusado(sessao_a):
    r = sessao_a.post("/api/formularios/xlsform", json={"nome": "circular.xlsx", "conteudo": _b64("circular.xlsx")})
    assert r.status_code == 422 and r.json()["erro"] == "dependencia_circular"
    assert set(r.json()["detalhe"]["campos"]) == {"a", "b", "c"}


def test_resposta_vira_feicao_com_calculo_e_metadados(sessao_a, conexao_plat_app, limpeza):
    f = _importar(sessao_a, "calculos.xlsx")
    r = sessao_a.post(f"/api/formularios/{f['id']}/respostas", json={
        "valores": {"largura": 2.5, "comprimento": 3.3, "preco_m2": 100}, "inicio": "2026-09-07T10:00:00Z",
        "dispositivo": "teste"})
    assert r.status_code == 201, r.text
    linhas = _linhas(conexao_plat_app, _camada(sessao_a, f["documento"]["camada_destino"]))
    assert len(linhas) == 1
    li = linhas[0]
    assert li["area"] == "8.25" and li["area_ha"] == "0.000825" and li["valor"] == "825"
    assert li["faixa_calc"] == "pequena"
    assert li["coleta_usuario"] == "admin" and li["coleta_dispositivo"] == "teste" and li["coleta_fim"] is not None
    assert li["coleta_versao"] == "2026090701"


def test_restricao_violada_nao_grava_nada(sessao_a, conexao_plat_app, limpeza):
    f = _importar(sessao_a, "regras.xlsx")
    camada = _camada(sessao_a, f["documento"]["camada_destino"])
    r = sessao_a.post(f"/api/formularios/{f['id']}/respostas", json={
        "valores": {"idade": 200, "tem_filhos": "sim", "n_filhos": 0}})
    assert r.status_code == 422 and r.json()["erro"] == "resposta_invalida"
    erros = {e["campo"]: e for e in r.json()["detalhe"]}
    assert erros["idade"]["erro"] == "restricao_violada" and erros["idade"]["mensagem"] == "Idade entre 0 e 149"
    assert erros["n_filhos"]["erro"] == "restricao_violada"
    assert _linhas(conexao_plat_app, camada) == []
    # obrigatório ausente também barra
    r = sessao_a.post(f"/api/formularios/{f['id']}/respostas", json={"valores": {"tem_filhos": "nao"}})
    assert r.status_code == 422 and any(e["erro"] == "campo_obrigatorio" for e in r.json()["detalhe"])
    assert _linhas(conexao_plat_app, camada) == []


def test_campo_nao_relevante_vai_nulo_e_regex_fica_registrado(sessao_a, conexao_plat_app, limpeza):
    f = _importar(sessao_a, "regras.xlsx")
    assert any(a["funcao"] == "regex" and a["estado"] == "fora" for a in f["documento"]["avisos"])
    r = sessao_a.post(f"/api/formularios/{f['id']}/respostas", json={
        "valores": {"idade": 15, "tem_filhos": "nao", "n_filhos": 5, "email": "sem-arroba", "documento": "x"}})
    assert r.status_code == 201, r.text  # n_filhos e email não são relevantes: nem validados, nem gravados
    li = _linhas(conexao_plat_app, _camada(sessao_a, f["documento"]["camada_destino"]))[0]
    assert li["n_filhos"] is None and li["email"] is None and li["idade"] == 15 and li["documento"] == "x"


def test_cascata_de_tres_niveis_valida_fora_da_lista(sessao_a, limpeza):
    f = _importar(sessao_a, "cascata.xlsx")
    doc = f["documento"]
    filtros = {c["nome"]: (c.get("filtro_lista") or {}).get("texto") for c in doc["campos"]}
    assert filtros["municipio"] and filtros["bairro"] and doc["listas"]["bairro"][0]["municipio"]
    ok = sessao_a.post(f"/api/formularios/{f['id']}/respostas", json={
        "valores": {"estado": "ba", "municipio": "ssa", "bairro": "ssa_pit"}})
    assert ok.status_code == 201, ok.text
    ruim = sessao_a.post(f"/api/formularios/{f['id']}/respostas", json={
        "valores": {"estado": "ba", "municipio": "spo", "bairro": "spo_pin"}})
    assert ruim.status_code == 422
    # spo não é município da Bahia (fora da lista filtrada); spo_pin é bairro válido de spo, então só um erro
    assert [e["campo"] for e in ruim.json()["detalhe"] if e["erro"] == "fora_da_lista"] == ["municipio"]


def test_repeticao_grava_n_linhas_relacionadas(sessao_a, conexao_plat_app, limpeza):
    f = _importar(sessao_a, "repeticao.xlsx")
    doc = f["documento"]
    filha = doc["camadas_filhas"]["membros"]
    r = sessao_a.post(f"/api/formularios/{f['id']}/respostas", json={
        "valores": {"domicilio": "D-1"},
        "repeticoes": {"membros": [{"nome_m": "Ana", "idade_m": 40, "trabalha": "sim"},
                                   {"nome_m": "Bia", "idade_m": 10, "trabalha": "sim"},
                                   {"nome_m": "Caio", "idade_m": 3}]}})
    assert r.status_code == 201, r.text
    assert r.json()["repeticoes"] == {"membros": 3}
    pai = _linhas(conexao_plat_app, _camada(sessao_a, doc["camada_destino"]))
    assert len(pai) == 1 and pai[0]["n_membros"] == "3" and pai[0]["soma_idades"] == "53"
    filhas = _linhas(conexao_plat_app, _camada(sessao_a, filha))
    assert [x["nome_m"] for x in filhas] == ["Ana", "Bia", "Caio"]
    assert {str(x["pai_globalid"]) for x in filhas} == {str(pai[0]["globalid"])}
    assert [x["indice"] for x in filhas] == [0, 1, 2]
    assert filhas[1]["trabalha"] is None  # `trabalha` só é relevante com idade >= 14
    # restrição dentro da repetição barra a resposta inteira: nada gravado nas duas camadas
    r = sessao_a.post(f"/api/formularios/{f['id']}/respostas", json={
        "valores": {"domicilio": "D-2"}, "repeticoes": {"membros": [{"nome_m": "X", "idade_m": 999}]}})
    assert r.status_code == 422
    assert r.json()["detalhe"][0]["repeticao"] == "membros" and r.json()["detalhe"][0]["indice"] == 0
    assert len(_linhas(conexao_plat_app, _camada(sessao_a, doc["camada_destino"]))) == 1
    assert len(_linhas(conexao_plat_app, _camada(sessao_a, filha))) == 3


def test_formulario_de_a_e_invisivel_para_b(sessao_a, sessao_b, limpeza):
    f = _importar(sessao_a, "basico.xlsx")
    assert sessao_b.get(f"/api/formularios/{f['id']}").status_code == 404
    r = sessao_b.post(f"/api/formularios/{f['id']}/respostas", json={"valores": {"nome": "x"}})
    assert r.status_code == 404


def test_tabela_de_equivalencia_publicada(sessao_a):
    r = sessao_a.get("/api/formularios/equivalencia")
    assert r.status_code == 200
    estados = {f["funcao"]: f["estado"] for f in r.json()["funcoes"]}
    assert estados["if"] == "feito" and estados["regex"] == "fora" and estados["pulldata"] == "parcial"


def test_conteudo_invalido_e_422(sessao_a):
    r = sessao_a.post("/api/formularios/xlsform", json={"nome": "x.xlsx", "conteudo": "AAAA"})
    assert r.status_code == 422 and r.json()["erro"] == "xlsform_invalido"
    r = sessao_a.post("/api/formularios/xlsform", json={"nome": "x.txt", "conteudo": "AAAA"})
    assert r.status_code == 422 and r.json()["erro"] == "xlsform_formato"


def test_cruzado_camada_de_b_nao_vira_destino(sessao_a, sessao_b, conexao_plat_app, limpeza):
    fb = _importar(sessao_b, "basico.xlsx")
    r = sessao_a.post("/api/formularios/xlsform", json={
        "nome": "basico.xlsx", "conteudo": _b64("basico.xlsx"), "camada_destino": fb["documento"]["camada_destino"]})
    assert r.status_code == 404
    # limpeza de B
    admin_b = _admin_id(conexao_plat_app, "demo2")
    contexto(conexao_plat_app, ids_por_slug(conexao_plat_app)["demo2"], usuario_id=admin_b, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT id, tipo, dados FROM plat.item WHERE titulo LIKE %s AND tipo IN ('formulario', "
                    "'camada_vetorial')", (f"{PREFIXO_TESTE} %",))
        for row in cur.fetchall():
            d = row["dados"] or {}
            if row["tipo"] == "camada_vetorial" and d.get("schema"):
                cur.execute(f'DROP TABLE IF EXISTS "{d["schema"]}"."{d["tabela"]}" CASCADE')
            cur.execute("DELETE FROM plat.item WHERE id = %s", (row["id"],))
    conexao_plat_app.commit()
