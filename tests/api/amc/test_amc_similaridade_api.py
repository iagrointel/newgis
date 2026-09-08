"""API do item L3-17-similaridade: `/api/amc/similaridade` e `/api/amc/similaridade/exportar`. Sem tabela
própria (o pedido traz a matriz inteira), então os testes só precisam de sessão autenticada com o privilégio
`analise.amc` — `sessao_a` (admin do inquilino demo, tests/api/conftest.py) tem todos os privilégios."""

import csv
import io

UNIDADES = {
    "A": {"chuva": 1200.0, "temp": 22.0},
    "B": {"chuva": 1300.0, "temp": 23.0},
    "C": {"chuva": 800.0, "temp": 30.0},
    "D": {"chuva": 1250.0, "temp": 21.0},
}


def test_similaridade_ranking_json(sessao_a):
    r = sessao_a.post("/api/amc/similaridade", json={"unidades": UNIDADES, "referencias": ["A"]})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["campos"] == ["chuva", "temp"]
    assert corpo["referencias"] == ["A"]
    assert len(corpo["ranking"]) == 4
    primeira = corpo["ranking"][0]
    assert primeira["unidade_id"] == "A" and primeira["posicao"] == 1
    assert abs(primeira["indice_similaridade"] - 1.0) < 1e-9
    assert corpo["excluidas"] == []
    assert "chuva" in corpo["estatisticas"] and "media" in corpo["estatisticas"]["chuva"]


def test_similaridade_escolha_de_campos(sessao_a):
    so_chuva = sessao_a.post("/api/amc/similaridade",
                              json={"unidades": UNIDADES, "referencias": ["A"], "campos": ["chuva"]})
    assert so_chuva.status_code == 200, so_chuva.text
    assert so_chuva.json()["campos"] == ["chuva"]


def test_similaridade_metrica_invalida_e_422(sessao_a):
    r = sessao_a.post("/api/amc/similaridade",
                       json={"unidades": UNIDADES, "referencias": ["A"], "metrica": "manhattan"})
    assert r.status_code == 422, r.text


def test_similaridade_referencia_desconhecida_e_422(sessao_a):
    r = sessao_a.post("/api/amc/similaridade", json={"unidades": UNIDADES, "referencias": ["Z"]})
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "referencia_desconhecida"


def test_similaridade_sem_autenticacao_e_401(sessao_a):
    from tests.api.conftest import novo_cliente

    anonimo = novo_cliente()
    r = anonimo.post("/api/amc/similaridade", json={"unidades": UNIDADES, "referencias": ["A"]})
    assert r.status_code == 401, r.text


def test_similaridade_exportar_csv(sessao_a):
    r = sessao_a.post("/api/amc/similaridade/exportar", json={"unidades": UNIDADES, "referencias": ["A"]})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    linhas = list(csv.reader(io.StringIO(r.text)))
    assert linhas[0] == ["posicao", "unidade_id", "indice_similaridade"]
    assert len(linhas) == 5
    assert linhas[1][1] == "A" and linhas[1][0] == "1"


def test_similaridade_exportar_geojson(sessao_a):
    r = sessao_a.post("/api/amc/similaridade/exportar?formato=geojson",
                       json={"unidades": UNIDADES, "referencias": ["A"]})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["type"] == "FeatureCollection"
    assert len(corpo["features"]) == 4


def test_similaridade_refutacao_referencia_igual_candidato_indice_1_1o_lugar(sessao_a):
    """Refutação exigida pelo item: candidato = referência tem de sair com índice 1 e em 1º lugar via API."""
    for metrica in ("cosseno", "euclidiana"):
        r = sessao_a.post("/api/amc/similaridade",
                           json={"unidades": UNIDADES, "referencias": ["C"], "metrica": metrica})
        assert r.status_code == 200, r.text
        corpo = r.json()
        linha_c = next(linha for linha in corpo["ranking"] if linha["unidade_id"] == "C")
        assert abs(linha_c["indice_similaridade"] - 1.0) < 1e-9, metrica
        assert linha_c["posicao"] == 1, metrica


def test_similaridade_unidades_acima_do_teto_e_422(sessao_a):
    from app import limites

    unidades = {f"u{i}": {"x": float(i)} for i in range(limites.SIMILARIDADE_UNIDADES_MAX + 1)}
    r = sessao_a.post("/api/amc/similaridade", json={"unidades": unidades, "referencias": ["u0"]})
    assert r.status_code == 422, r.text
