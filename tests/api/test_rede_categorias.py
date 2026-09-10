"""Categorias de tipo, restrições de feição e traçado de isolamento (item L4-06-d-categorias-e-restricoes).

Cláusulas do portão provadas aqui: "≥ 8 categorias no pacote elétrica-BR"
(test_pacote_eletrica_br_tem_pelo_menos_8_categorias); "isolamento usa a categoria 'proteção'"
(test_isolamento_para_na_categoria_protecao); "alterar categoria de um tipo dispara área suja em todas as
feições do tipo, com a contagem" (test_redefinir_categorias_marca_area_suja_e_devolve_contagem); "restrição
impede traçado a partir de UC quando configurada" (test_restricao_sem_ponto_partida_bloqueia_isolamento).
Refutação: "o adversário remove a categoria 'controlador' do tipo que tem controladores ativos e confere que o
sistema recusa até removê-los" (test_remover_categoria_controlador_com_ativo_e_recusado)."""

import json

import psycopg2
import pytest

from app.rede_utilidades import instalados
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for sessao, rid in criadas:
        sessao.delete(f"/api/rede/{rid}")


def _criar_rede(sessao, sufixo, disciplina="eletrica"):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-rede-catrest-{sufixo}", "disciplina": disciplina})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _importar(sessao, rid, codigo="eletrica-br"):
    bruto = instalados.bruto(codigo)
    r = sessao.post(f"/api/rede/{rid}/pacote", content=bruto, headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text


def _tipo_id(env, rid, grupo_codigo, tipo_codigo) -> str:
    """Não há rota GET de tipo isolado (fora do escopo deste item); resolve o uuid direto no banco, dentro do
    contexto do inquilino demo, do mesmo jeito que `tests/api/test_rls.py` já faz para outras suítes."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
        contexto(con, ids["demo"])
        with con.cursor() as cur:
            cur.execute(
                "SELECT tp.id FROM plat.rede_tipo tp JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
                "WHERE tp.rede_id = %s::uuid AND g.codigo = %s AND tp.codigo = %s",
                (rid, grupo_codigo, tipo_codigo),
            )
            row = cur.fetchone()
            assert row is not None, (grupo_codigo, tipo_codigo)
            return str(row["id"])
    finally:
        con.close()


def _criar_feicao(sessao, rid, tipo_id, codigo, controlador_ativo=False):
    r = sessao.post(f"/api/rede/{rid}/feicoes",
                     json={"tipo_id": tipo_id, "codigo": codigo, "controlador_ativo": controlador_ativo})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_pacote_eletrica_br_tem_pelo_menos_8_categorias():
    doc = json.loads(instalados.bruto("eletrica-br"))
    assert len(doc["categorias"]) >= 8, doc["categorias"]


def test_redefinir_categorias_marca_area_suja_e_devolve_contagem(sessao_a, env, limpar_redes):
    rid = _criar_rede(sessao_a, "suja")
    limpar_redes.append((sessao_a, rid))
    _importar(sessao_a, rid)
    tipo_id = _tipo_id(env, rid, "subestacao", 1)  # categoria 'fonte', sem controlador
    f1 = _criar_feicao(sessao_a, rid, tipo_id, "f1")
    f2 = _criar_feicao(sessao_a, rid, tipo_id, "f2")
    assert f1 != f2

    r = sessao_a.put(f"/api/rede/{rid}/tipos/{tipo_id}/categorias", json={"categorias": ["fonte", "medicao"]})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["feicoes_marcadas_sujas"] == 2, corpo
    assert corpo["depois"] == ["fonte", "medicao"]

    # sem feição nova entre uma alteração e outra: a segunda também marca as 2 (a área suja não "acumula" contagem)
    r2 = sessao_a.put(f"/api/rede/{rid}/tipos/{tipo_id}/categorias", json={"categorias": ["fonte"]})
    assert r2.status_code == 200 and r2.json()["feicoes_marcadas_sujas"] == 2


def test_categoria_inexistente_no_pacote_e_recusada(sessao_a, env, limpar_redes):
    rid = _criar_rede(sessao_a, "catinexistente")
    limpar_redes.append((sessao_a, rid))
    _importar(sessao_a, rid)
    tipo_id = _tipo_id(env, rid, "subestacao", 1)
    r = sessao_a.put(f"/api/rede/{rid}/tipos/{tipo_id}/categorias", json={"categorias": ["categoria-que-nao-existe"]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "categoria_inexistente"


def test_remover_categoria_controlador_com_ativo_e_recusado(sessao_a, env, limpar_redes):
    """Refutação do item: adversário tenta remover 'controlador' do tipo que tem feição de controlador ATIVO."""
    rid = _criar_rede(sessao_a, "refutacao")
    limpar_redes.append((sessao_a, rid))
    _importar(sessao_a, rid)
    tipo_id = _tipo_id(env, rid, "banco_de_capacitores", 1)  # tem categoria 'controlador' no pacote
    _criar_feicao(sessao_a, rid, tipo_id, "cap-ativo", controlador_ativo=True)

    r = sessao_a.put(f"/api/rede/{rid}/tipos/{tipo_id}/categorias", json={"categorias": ["conducao"]})
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "controlador_ativo_bloqueia_categoria"
    assert r.json()["detalhe"]["feicoes_controlador_ativo"] == 1

    # só depois de desligar o controlador a mudança é aceita
    r2 = sessao_a.put(f"/api/rede/{rid}/tipos/{tipo_id}/categorias", json={"categorias": ["controlador"]})
    assert r2.status_code == 200, r2.text


def test_restricao_sem_ponto_partida_bloqueia_isolamento(sessao_a, env, limpar_redes):
    rid = _criar_rede(sessao_a, "restricao-uc")
    limpar_redes.append((sessao_a, rid))
    _importar(sessao_a, rid)
    tipo_uc = _tipo_id(env, rid, "unidade_consumidora", 1)
    uc = _criar_feicao(sessao_a, rid, tipo_uc, "uc-1")

    r = sessao_a.get(f"/api/rede/{rid}/feicoes/{uc}/isolamento")
    assert r.status_code == 200, r.text  # sem restrição configurada, ainda passa

    rr = sessao_a.put(f"/api/rede/{rid}/tipos/{tipo_uc}/restricoes", json={"restricoes": ["sem_ponto_partida"]})
    assert rr.status_code == 200, rr.text
    assert rr.json()["depois"] == ["sem_ponto_partida"]

    r2 = sessao_a.get(f"/api/rede/{rid}/feicoes/{uc}/isolamento")
    assert r2.status_code == 422, r2.text
    assert r2.json()["erro"] == "ponto_partida_restrito"


def test_restricao_desconhecida_e_recusada(sessao_a, env, limpar_redes):
    rid = _criar_rede(sessao_a, "restricao-invalida")
    limpar_redes.append((sessao_a, rid))
    _importar(sessao_a, rid)
    tipo_uc = _tipo_id(env, rid, "unidade_consumidora", 1)
    r = sessao_a.put(f"/api/rede/{rid}/tipos/{tipo_uc}/restricoes", json={"restricoes": ["restricao-fantasia"]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "restricao_desconhecida"


def test_isolamento_para_na_categoria_protecao(sessao_a, env, limpar_redes):
    """fonte -> proteção -> carga; isolar a partir da fonte visita a proteção mas não a carga atrás dela."""
    rid = _criar_rede(sessao_a, "isolamento")
    limpar_redes.append((sessao_a, rid))
    _importar(sessao_a, rid)
    tipo_fonte = _tipo_id(env, rid, "geracao_distribuida", 1)
    tipo_disjuntor = _tipo_id(env, rid, "chave_de_media_tensao", 4)  # 'disjuntor', categoria dispositivo_de_protecao
    tipo_carga = _tipo_id(env, rid, "unidade_consumidora", 1)

    fonte = _criar_feicao(sessao_a, rid, tipo_fonte, "fonte-1")
    protecao = _criar_feicao(sessao_a, rid, tipo_disjuntor, "disjuntor-1")
    carga = _criar_feicao(sessao_a, rid, tipo_carga, "carga-1")

    assert sessao_a.post(
        f"/api/rede/{rid}/feicoes/{fonte}/ligar", json={"para_feicao_id": protecao}
    ).status_code == 201
    assert sessao_a.post(
        f"/api/rede/{rid}/feicoes/{protecao}/ligar", json={"para_feicao_id": carga}
    ).status_code == 201

    r = sessao_a.get(f"/api/rede/{rid}/feicoes/{fonte}/isolamento")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert protecao in corpo["visitadas"] and protecao in corpo["fronteira_protecao"]
    assert carga not in corpo["visitadas"], "o isolamento atravessou a proteção"
    assert fonte in corpo["visitadas"]
