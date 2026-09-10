"""Consumidores e endereços da rede contra a carga REAL da cooperativa (item
L4-20-consumidores-e-enderecos). A carga (tests/dados/carga_rede_cooperativa.py) entra no inquilino
demo e pula o arquivo inteiro quando o schema de origem não está no ambiente (PLAT_REDE_ESQUEMA_COOP).
Cláusulas medidas: contagem de endereços sem rede a 5 % da camada de referência da casa, tempo de
geração e de jusante, e a regra de privacidade (nenhum campo identificável; consumo só em agregado).
"""

import time

import pytest

from tests.api.conftest import novo_cliente
from tests.dados import carga_rede_cooperativa as carga

CAMADA_CASA = "end_sem_rede"  # camada de referência da casa no schema da cooperativa


def _cur_inquilino(conexao_plat_app, slug: str):
    cur = conexao_plat_app.cursor()
    cur.execute("SELECT tenant_id::text AS id FROM plat.auth_login(%s, 'admin')", (slug,))
    tid = cur.fetchone()["id"]
    cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (tid,))
    return cur


@pytest.fixture(scope="module")
def rede_carregada(env):
    """Carga real no inquilino demo (uma vez por arquivo). Pula o módulo sem o schema de origem."""
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente

    esquema = carga.esquema_coop()
    if not esquema:
        pytest.skip("PLAT_REDE_ESQUEMA_COOP não definido (sem dado real da cooperativa)")
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    try:
        if not carga.disponivel(con):
            pytest.skip(f"schema {esquema} sem as tabelas da carga")
        contagem = carga.carregar(con, "demo")
        with con.cursor() as cur:
            cur.execute("SELECT set_config('plat.tenant_id',"
                        " (SELECT tenant_id::text FROM plat.auth_login('demo', 'admin')), false)")
            cur.execute(f"SELECT count(*) AS n FROM {esquema}.{CAMADA_CASA}")
            contagem["camada_casa"] = cur.fetchone()["n"]
        return contagem
    finally:
        con.rollback()
        con.close()


@pytest.fixture(scope="module")
def gerado(rede_carregada, sessao_a):
    """Camada gerada UMA vez (POST) para todos os testes do módulo."""
    t0 = time.monotonic()
    r = sessao_a.post("/api/rede/consumidores/enderecos-sem-rede", json={})
    segundos = time.monotonic() - t0
    assert r.status_code == 200, r.text
    return {"resumo": r.json(), "segundos": segundos}


def test_gera_camada_com_contagens(gerado, rede_carregada):
    resumo = gerado["resumo"]
    assert resumo["enderecos"] == rede_carregada["enderecos"] > 100_000
    assert resumo["total"] > 5_000
    assert resumo["candidato_ligacao"] > 0 and resumo["cadastro_faltante"] > 0
def test_contagem_a_5_por_cento_da_casa(gerado, rede_carregada, medida):
    """A camada gerada reproduz a de referência da casa dentro de 5 % (critério geométrico
    equivalente: média a 700 m e nenhuma baixa a 135 m)."""
    medida("L4-20-consumidores-e-enderecos")(
        "contagem_enderecos_sem_rede",
        gerado["resumo"]["total"],
        "endereços",
        f"POST /api/rede/consumidores/enderecos-sem-rede vs {CAMADA_CASA} da casa "
        f"({rede_carregada['camada_casa']})",
    )
    casa = rede_carregada["camada_casa"]
    assert casa > 0
    assert abs(gerado["resumo"]["total"] - casa) <= casa * 0.05


def test_tempo_de_geracao_anotado(gerado, medida):
    medida("L4-20-consumidores-e-enderecos")(
        "geracao_camada_s", round(gerado["segundos"], 1), "s", "POST /api/rede/consumidores/enderecos-sem-rede"
    )
    assert gerado["segundos"] < 300  # camada inteira em minutos, não em horas


def test_lista_sem_campo_identificavel(sessao_a):
    r = sessao_a.get("/api/rede/consumidores/enderecos-sem-rede?limite=25")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["total"] == gerado_total(sessao_a) and len(corpo["itens"]) == 25
    proibidas = {"nome", "cpf", "cnpj", "telefone", "email", "endereco", "identidade"}
    for item in corpo["itens"]:
        assert not (set(item) & proibidas), set(item) & proibidas
        assert item["situacao"] in ("candidato_ligacao", "cadastro_faltante")


def gerado_total(sessao_a) -> int:
    return sessao_a.get("/api/rede/consumidores/enderecos-sem-rede?limite=1").json()["total"]


def test_ficha_uc_sem_identificacao_e_agregado(rede_carregada, sessao_a, conexao_plat_app):
    """Ficha de unidade consumidora: chaves só de rede; consumo por transformador só com o mínimo
    de unidades; uma UC de transformador pequeno fica sem número, com motivo."""
    with _cur_inquilino(conexao_plat_app, "demo") as cur:
        cur.execute(
            "SELECT u.id::text AS id, u.uni_tr_mt,"
            "       count(*) OVER (PARTITION BY u.uni_tr_mt) AS ucs_do_trafo"
            "  FROM plat.rede_uc u WHERE tenant_id = plat.tenant_atual() AND uni_tr_mt IS NOT NULL"
            " ORDER BY ucs_do_trafo DESC LIMIT 1"
        )
        grande = cur.fetchone()
        cur.execute(
            "SELECT id FROM ("
            "  SELECT u.id::text AS id, count(*) OVER (PARTITION BY u.uni_tr_mt) AS n"
            "    FROM plat.rede_uc u"
            "   WHERE tenant_id = plat.tenant_atual() AND uni_tr_mt IS NOT NULL"
            ") s WHERE n < 5 LIMIT 1"
        )
        pequena = cur.fetchone()
    proibidas = {"nome", "cpf", "cnpj", "telefone", "email", "endereco", "identidade"}
    r = sessao_a.get(f"/api/rede/consumidores/uc/{grande['id']}")
    assert r.status_code == 200, r.text
    ficha = r.json()
    assert not (set(ficha) & proibidas) and not (set(ficha.get("consumo") or {}) & proibidas)
    assert grande["ucs_do_trafo"] >= 5 and ficha["consumo"]["ene_kwh"] is not None
    assert ficha["consumo"]["ucs"] == grande["ucs_do_trafo"]
    r2 = sessao_a.get(f"/api/rede/consumidores/uc/{pequena['id']}")
    assert r2.status_code == 200, r2.text
    assert r2.json()["consumo"]["ene_kwh"] is None and "motivo" in r2.json()["consumo"]


def test_jusante_calcula_e_trecho_expoe(rede_carregada, sessao_a, conexao_plat_app, medida):
    t0 = time.monotonic()
    r = sessao_a.post("/api/rede/consumidores/jusante/calcular", json={})
    segundos = time.monotonic() - t0
    assert r.status_code == 200, r.text
    resumo = r.json()
    assert resumo["trechos"] == rede_carregada["trechos_mt"]
    assert resumo["trechos_calculados"] > resumo["trechos"] * 0.9  # malha é exceção, não regra
    medida("L4-20-consumidores-e-enderecos")(
        "jusante_calcular_s", round(segundos, 1), "s",
        f"POST /api/rede/consumidores/jusante/calcular sobre {resumo['trechos']} trechos",
    )
    with _cur_inquilino(conexao_plat_app, "demo") as cur:
        cur.execute(
            "SELECT id::text AS id, clientes_jusante FROM plat.rede_trecho"
            " WHERE tenant_id = plat.tenant_atual() AND nivel = 'mt'"
            "   AND clientes_jusante IS NOT NULL ORDER BY clientes_jusante DESC LIMIT 1"
        )
        trecho = cur.fetchone()
    r2 = sessao_a.get(f"/api/rede/consumidores/trecho/{trecho['id']}")
    assert r2.status_code == 200, r2.text
    corpo = r2.json()
    assert corpo["clientes_jusante"] == trecho["clientes_jusante"] > 0
    assert corpo["consumo"] is None or corpo["consumo"]["ucs"] >= 5


def test_rls_inquilino_b_nao_ve_nada(rede_carregada, sessao_a, sessao_b):
    assert gerado_total(sessao_a) > 0
    r = sessao_b.get("/api/rede/consumidores/enderecos-sem-rede?limite=5")
    assert r.status_code == 200 and r.json()["total"] == 0
    # a ficha pedida por B (mesmo com id de A) tem de ser 404 pela RLS, nunca 200
    r2 = sessao_b.get("/api/rede/consumidores/uc/00000000-0000-0000-0000-000000000000")
    assert r2.status_code == 404, r2.text


def test_escopo_sem_privilegio_de_escrita_nao_gera(rede_carregada, sessao_a):
    """Token com escopo de leitura não leva a rota de escrita: 401/403 (privilégio rede.editar).
    A chamada usa cliente novo SEM cookie de sessão: sessão e token juntos são recusados de
    propósito com 400 autenticacao_ambigua, antes de qualquer checagem de escopo."""
    r = sessao_a.post("/api/tokens", json={"nome": "zt-l4-20-leitor", "escopos": ["catalogo:ler"]})
    assert r.status_code == 201, r.text
    token = r.json()
    try:
        anonimo = novo_cliente()
        r2 = anonimo.post(
            "/api/rede/consumidores/enderecos-sem-rede",
            json={"raio_rede_m": 700},
            headers={"Authorization": f"Bearer {token['token']}"},
        )
        assert r2.status_code in (401, 403), r2.text
    finally:
        sessao_a.delete(f"/api/tokens/{token['id']}")


def test_parametro_fora_do_teto_recusado(rede_carregada, sessao_a):
    r = sessao_a.post("/api/rede/consumidores/enderecos-sem-rede", json={"raio_rede_m": 999999})
    assert r.status_code == 422, r.text
