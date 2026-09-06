"""Item L3-01-a-modelo-dado pela API: as cláusulas do portão (JSON Schema no POST, as quatro violações
nomeadas, imutabilidade do modelo executado, hash reproduzido pelo script independente, isolamento entre
inquilinos) e o CRUD que sustenta o resto da linha L3 (conjunto de unidades, execução, listagem de
resultado). ESTA É A CLÁUSULA INEGOCIÁVEL do item: `test_a_nao_le_modelo_execucao_nem_resultado_de_b_pela_api`
e `test_rls_no_banco_esconde_amc_de_outro_inquilino`."""

import secrets
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest

from app.amc.esquema import hash_canonico
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug

RAIZ = Path(__file__).resolve().parents[3]


def _nome(base="modelo"):
    return f"{PREFIXO_TESTE}-amc-{base}-{secrets.token_hex(4)}"


def _def(**over):
    d = {
        "combinador": "soma_ponderada",
        "fatores": [
            {"id": "declividade", "criterio": "menor declive é melhor", "peso": 2,
             "transformacao": {"tipo": "linear", "minimo": 0, "maximo": 45, "inverter": True}},
            {"id": "distancia_via", "criterio": "perto de via é melhor", "peso": 1,
             "transformacao": {"tipo": "faixas", "quebras": [500, 1500], "notas": [100, 60, 20]}},
        ],
    }
    d.update(over)
    return d


def _criar_modelo(sessao, **over):
    r = sessao.post("/api/amc/modelos", json={"nome": _nome(), "definicao": _def(**over)})
    assert r.status_code == 201, r.text
    return r.json()


def _criar_conjunto(sessao):
    r = sessao.post("/api/amc/conjuntos", json={"nome": _nome("conjunto"), "tipo": "hexagonal", "lado_m": 250})
    assert r.status_code == 201, r.text
    return r.json()


def _criar_execucao(sessao, modelo_id, conjunto_id, **over):
    corpo = {"modelo_id": modelo_id, "conjunto_id": conjunto_id, "semente": 42}
    corpo.update(over)
    r = sessao.post("/api/amc/execucoes", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ criação e hash
def test_modelo_valido_nasce_com_hash_e_versao_1(sessao_a):
    m = _criar_modelo(sessao_a)
    assert len(m["versao_hash"]) == 64 and all(c in "0123456789abcdef" for c in m["versao_hash"])
    assert m["executado"] is False
    assert m["versao_hash"] == hash_canonico(m["definicao"])
    assert sessao_a.delete(f"/api/amc/modelos/{m['id']}").status_code == 204


def test_validar_sem_gravar_nao_cria_nada(sessao_a):
    r = sessao_a.post("/api/amc/modelos/validar", json={"definicao": _def()})
    assert r.status_code == 200
    j = r.json()
    assert j["valido"] is True and j["versao_hash"] == hash_canonico(_def()) and j["erros"] == []
    total_antes = sessao_a.get("/api/amc/modelos").json()["total"]
    r2 = sessao_a.post("/api/amc/modelos/validar", json={"definicao": {"fatores": []}})
    assert r2.status_code == 200 and r2.json()["valido"] is False
    assert sessao_a.get("/api/amc/modelos").json()["total"] == total_antes


# ------------------------------------------------------------------ as quatro cláusulas do portão, pela API
@pytest.mark.parametrize(
    "quebra,clausula",
    [
        ("peso_negativo", "fatores[].peso >= 0"),
        ("fator_sem_transformacao", "fatores[].transformacao obrigatória"),
        ("soma_de_pesos_zero", "soma(fatores[].peso) > 0"),
        ("fator_duplicado", "fatores[].id único"),
    ],
)
def test_modelo_invalido_devolve_422_com_a_clausula(sessao_a, quebra, clausula):
    d = _def()
    if quebra == "peso_negativo":
        d["fatores"][0]["peso"] = -1
    elif quebra == "fator_sem_transformacao":
        del d["fatores"][0]["transformacao"]
    elif quebra == "soma_de_pesos_zero":
        for f in d["fatores"]:
            f["peso"] = 0
    elif quebra == "fator_duplicado":
        d["fatores"].append(dict(d["fatores"][0]))
    r = sessao_a.post("/api/amc/modelos", json={"nome": _nome(), "definicao": d})
    assert r.status_code == 422, r.text
    j = r.json()
    assert j["erro"] == "modelo_invalido"
    clausulas = [e["clausula"] for e in j["detalhe"]]
    assert clausula in clausulas, j


# ------------------------------------------------------------------ CRUD e edição
def test_listar_e_ver_modelo(sessao_a):
    m = _criar_modelo(sessao_a)
    lista = sessao_a.get("/api/amc/modelos").json()
    assert any(i["id"] == m["id"] for i in lista["itens"])
    r = sessao_a.get(f"/api/amc/modelos/{m['id']}")
    assert r.status_code == 200 and r.json()["id"] == m["id"]
    assert sessao_a.delete(f"/api/amc/modelos/{m['id']}").status_code == 204


def test_editar_nome_nao_muda_hash(sessao_a):
    m = _criar_modelo(sessao_a)
    r = sessao_a.put(f"/api/amc/modelos/{m['id']}", json={"nome": _nome("renomeado")})
    assert r.status_code == 200 and r.json()["versao_hash"] == m["versao_hash"]
    assert sessao_a.delete(f"/api/amc/modelos/{m['id']}").status_code == 204


def test_editar_definicao_gera_hash_novo(sessao_a):
    m = _criar_modelo(sessao_a)
    novo = _def(descricao="mudou")
    r = sessao_a.put(f"/api/amc/modelos/{m['id']}", json={"definicao": novo})
    assert r.status_code == 200
    assert r.json()["versao_hash"] == hash_canonico(novo) != m["versao_hash"]
    assert sessao_a.delete(f"/api/amc/modelos/{m['id']}").status_code == 204


def test_editar_definicao_invalida_e_422_e_nao_grava(sessao_a):
    m = _criar_modelo(sessao_a)
    r = sessao_a.put(f"/api/amc/modelos/{m['id']}", json={"definicao": {"fatores": []}})
    assert r.status_code == 422
    assert sessao_a.get(f"/api/amc/modelos/{m['id']}").json()["versao_hash"] == m["versao_hash"]
    assert sessao_a.delete(f"/api/amc/modelos/{m['id']}").status_code == 204


def test_apagar_modelo_nao_executado_funciona(sessao_a):
    m = _criar_modelo(sessao_a)
    assert sessao_a.delete(f"/api/amc/modelos/{m['id']}").status_code == 204
    assert sessao_a.get(f"/api/amc/modelos/{m['id']}").status_code == 404


# ------------------------------------------------------------------ conjunto de unidades
def test_conjunto_crud(sessao_a):
    c = _criar_conjunto(sessao_a)
    assert c["tipo"] == "hexagonal" and c["lado_m"] == 250
    assert sessao_a.get(f"/api/amc/conjuntos/{c['id']}").json()["id"] == c["id"]
    lista = sessao_a.get("/api/amc/conjuntos").json()
    assert any(i["id"] == c["id"] for i in lista["itens"])
    assert sessao_a.delete(f"/api/amc/conjuntos/{c['id']}").status_code == 204
    assert sessao_a.get(f"/api/amc/conjuntos/{c['id']}").status_code == 404


# ------------------------------------------------------------------ execução: proveniência congelada
def test_execucao_congela_versao_do_modelo_e_marca_executado(sessao_a):
    m = _criar_modelo(sessao_a)
    c = _criar_conjunto(sessao_a)
    e = _criar_execucao(
        sessao_a, m["id"], c["id"], camadas=[{"id": "acervo:teste", "sha256": "a" * 64, "contagem": 10}]
    )
    assert e["modelo_id"] == m["id"] and e["modelo_versao_hash"] == m["versao_hash"]
    assert e["estado"] == "registrada" and e["semente"] == 42
    assert e["camadas"][0]["sha256"] == "a" * 64
    assert sessao_a.get(f"/api/amc/modelos/{m['id']}").json()["executado"] is True


def test_execucao_com_peso_de_fator_desconhecido_e_422(sessao_a):
    m = _criar_modelo(sessao_a)
    c = _criar_conjunto(sessao_a)
    r = sessao_a.post("/api/amc/execucoes", json={
        "modelo_id": m["id"], "conjunto_id": c["id"], "semente": 1, "pesos": {"fator_que_nao_existe": 1},
    })
    assert r.status_code == 422 and r.json()["erro"] == "pesos_fator_desconhecido"
    assert sessao_a.delete(f"/api/amc/modelos/{m['id']}").status_code == 204
    assert sessao_a.delete(f"/api/amc/conjuntos/{c['id']}").status_code == 204


def test_execucao_com_modelo_ou_conjunto_inexistente_e_404(sessao_a):
    c = _criar_conjunto(sessao_a)
    falso = "00000000-0000-0000-0000-000000000000"
    r = sessao_a.post("/api/amc/execucoes", json={"modelo_id": falso, "conjunto_id": c["id"], "semente": 1})
    assert r.status_code == 404 and r.json()["erro"] == "modelo_inexistente"
    m = _criar_modelo(sessao_a)
    r = sessao_a.post("/api/amc/execucoes", json={"modelo_id": m["id"], "conjunto_id": falso, "semente": 1})
    assert r.status_code == 404 and r.json()["erro"] == "conjunto_inexistente"
    sessao_a.delete(f"/api/amc/modelos/{m['id']}")
    sessao_a.delete(f"/api/amc/conjuntos/{c['id']}")


# ------------------------------------------------------------------ REFUTAÇÃO: editar modelo executado não
# muda a execução nem o resultado (resultado inserido à mão: nada calcula favorabilidade ainda, L3-01-c/d/e)
def test_refutacao_editar_modelo_executado_nao_muda_a_execucao_nem_o_resultado(
    sessao_a, conexao_plat_app, ids,
):
    m = _criar_modelo(sessao_a)
    c = _criar_conjunto(sessao_a)
    e = _criar_execucao(sessao_a, m["id"], c["id"])

    tenant_id = ids_por_slug(conexao_plat_app)["demo"]
    contexto(conexao_plat_app, tenant_id, usuario_id=ids["a"]["id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "INSERT INTO plat.amc_resultado(execucao_id, unidade_id, favorabilidade, vetado, cobertura) "
            "VALUES (%s, 'u1', 71.5, false, 1.0), (%s, 'u2', 12.0, false, 0.8)",
            (e["id"], e["id"]),
        )
    conexao_plat_app.commit()

    # 1) PUT com definição nova: 200, mas devolve o modelo com versao_hash NOVO (é um modelo novo em
    #    termos de conteúdo — a garantia não é "não editar", é "a execução não muda")
    r = sessao_a.put(f"/api/amc/modelos/{m['id']}", json={"definicao": _def(descricao="ataque")})
    assert r.status_code == 409 and r.json()["erro"] == "amc_modelo_identidade_imutavel", r.text

    # 2) a execução continua com o versao_hash antigo e a definição do modelo não mudou
    e_depois = sessao_a.get(f"/api/amc/execucoes/{e['id']}").json()
    assert e_depois["modelo_versao_hash"] == m["versao_hash"] == e["modelo_versao_hash"]
    assert sessao_a.get(f"/api/amc/modelos/{m['id']}").json()["definicao"] == m["definicao"]

    # 3) os resultados são bit a bit os mesmos
    res = sessao_a.get(f"/api/amc/execucoes/{e['id']}/resultados").json()
    assert res["total"] == 2
    valores = {r_["unidade_id"]: r_["favorabilidade"] for r_ in res["itens"]}
    assert valores == {"u1": 71.5, "u2": 12.0}

    # 4) UPDATE/DELETE direto no banco, como plat_app: barrados pelos gatilhos (o contexto é LOCAL à
    #    transação — o commit do INSERT de resultado acima já o apagou; refaz antes de cada bloco)
    contexto(conexao_plat_app, tenant_id, usuario_id=ids["a"]["id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.RaiseException, match="amc_modelo_identidade_imutavel"):
            cur.execute("UPDATE plat.amc_modelo SET definicao = '{}'::jsonb WHERE id = %s", (m["id"],))
    conexao_plat_app.rollback()
    contexto(conexao_plat_app, tenant_id, usuario_id=ids["a"]["id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.RaiseException, match="amc_execucao_proveniencia_imutavel"):
            cur.execute("UPDATE plat.amc_execucao SET semente = 999 WHERE id = %s", (e["id"],))
    conexao_plat_app.rollback()
    contexto(conexao_plat_app, tenant_id, usuario_id=ids["a"]["id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.RaiseException, match="amc_materializado_imutavel"):
            cur.execute("UPDATE plat.amc_resultado SET favorabilidade = 0 WHERE execucao_id = %s", (e["id"],))
    conexao_plat_app.rollback()

    # modelo executado nunca se apaga
    contexto(conexao_plat_app, tenant_id, usuario_id=ids["a"]["id"], login="admin")
    r = sessao_a.delete(f"/api/amc/modelos/{m['id']}")
    assert r.status_code == 409 and r.json()["erro"] == "amc_modelo_nao_apaga"


def test_versao_gravada_e_imutavel_para_a_aplicacao(sessao_a, conexao_plat_app, ids):
    """UPDATE/DELETE em plat.amc_modelo já executado como plat_app: sempre amc_modelo_identidade_imutavel /
    amc_modelo_nao_apaga, mesmo direto no banco (não só pela rota)."""
    m = _criar_modelo(sessao_a)
    c = _criar_conjunto(sessao_a)
    _criar_execucao(sessao_a, m["id"], c["id"])
    tenant_id = ids_por_slug(conexao_plat_app)["demo"]
    contexto(conexao_plat_app, tenant_id, usuario_id=ids["a"]["id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.RaiseException, match="amc_modelo_nao_apaga"):
            cur.execute("DELETE FROM plat.amc_modelo WHERE id = %s", (m["id"],))
    conexao_plat_app.rollback()


# ------------------------------------------------------------------ hash: script independente confere o banco
def test_script_independente_confere_o_que_esta_no_banco(sessao_a, env, ids, conexao_plat_app):
    m = _criar_modelo(sessao_a)
    tenant_id = ids_por_slug(conexao_plat_app)["demo"]
    ambiente = dict(__import__("os").environ)
    ambiente["PLAT_DSN"] = env["PLAT_DSN"]
    ambiente["PLAT_SCHEMA"] = env.get("PLAT_SCHEMA") or "plat"
    r = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "amc_hash_independente.py"), "--tenant", str(tenant_id),
         "--modelo", m["id"]],
        capture_output=True, text=True, cwd=RAIZ, env=ambiente,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "divergentes: 0" in r.stdout
    assert m["versao_hash"] in r.stdout
    assert sessao_a.delete(f"/api/amc/modelos/{m['id']}").status_code == 204


# ------------------------------------------------------------------ CLÁUSULA INEGOCIÁVEL: A nunca lê amc_* de B
def test_a_nao_le_modelo_execucao_nem_resultado_de_b_pela_api(sessao_a, sessao_b, conexao_plat_app, ids):
    m_b = _criar_modelo(sessao_b)
    c_b = _criar_conjunto(sessao_b)
    e_b = _criar_execucao(sessao_b, m_b["id"], c_b["id"])
    tenant_b = ids_por_slug(conexao_plat_app)["demo2"]
    contexto(conexao_plat_app, tenant_b, usuario_id=ids["b"]["id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "INSERT INTO plat.amc_resultado(execucao_id, unidade_id, favorabilidade) VALUES (%s, 'u1', 50.0)",
            (e_b["id"],),
        )
    conexao_plat_app.commit()

    sondas = [
        ("GET", f"/api/amc/modelos/{m_b['id']}"),
        ("PUT", f"/api/amc/modelos/{m_b['id']}"),
        ("DELETE", f"/api/amc/modelos/{m_b['id']}"),
        ("GET", f"/api/amc/conjuntos/{c_b['id']}"),
        ("DELETE", f"/api/amc/conjuntos/{c_b['id']}"),
        ("GET", f"/api/amc/execucoes/{e_b['id']}"),
        ("DELETE", f"/api/amc/execucoes/{e_b['id']}"),
        ("GET", f"/api/amc/execucoes/{e_b['id']}/resultados"),
    ]
    for metodo, url in sondas:
        r = sessao_a.request(metodo, url, json={"nome": "invadido"} if metodo == "PUT" else None)
        assert r.status_code in (401, 403, 404), (metodo, url, r.status_code, r.text)
        assert m_b["id"] not in r.text and m_b["nome"] not in r.text
        assert "u1" not in r.text

    # POST /api/amc/execucoes com modelo_id/conjunto_id de B no CORPO: 404, nunca resolve a camada de B
    r = sessao_a.post("/api/amc/execucoes", json={"modelo_id": m_b["id"], "conjunto_id": c_b["id"], "semente": 1})
    assert r.status_code == 404, r.text

    # listagem com filtro apontando para modelo de B: 200 com lista VAZIA (o filtro é só um WHERE dentro
    # do RLS do próprio A; o id de B não pertence a A, então nunca aparece — nunca 404 aqui, só 0 itens)
    r = sessao_a.get(f"/api/amc/execucoes?modelo_id={m_b['id']}")
    assert r.status_code == 200 and r.json() == {"total": 0, "itens": []}, r.text

    # listagens gerais de A nunca trazem nada de B
    assert m_b["id"] not in str(sessao_a.get("/api/amc/modelos").json())
    assert c_b["id"] not in str(sessao_a.get("/api/amc/conjuntos").json())
    assert e_b["id"] not in str(sessao_a.get("/api/amc/execucoes").json())

    # limpeza: modelo de B já está "executado" (a sonda de execução acima foi recusada antes de existir,
    # mas e_b já existia) — apaga execução primeiro, depois conjunto; o modelo fica (não se apaga executado,
    # é o comportamento correto do produto, não resíduo de teste a esconder)
    contexto(conexao_plat_app, tenant_b, usuario_id=ids["b"]["id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("DELETE FROM plat.amc_resultado WHERE execucao_id = %s", (e_b["id"],))
    conexao_plat_app.commit()
    assert sessao_b.delete(f"/api/amc/execucoes/{e_b['id']}").status_code == 204
    assert sessao_b.delete(f"/api/amc/conjuntos/{c_b['id']}").status_code == 204


def test_rls_no_banco_esconde_amc_de_outro_inquilino(sessao_a, conexao_plat_app, ids):
    """Direto no banco, como plat_app: sem contexto, 0 linhas; com o contexto do OUTRO inquilino, 0 linhas;
    INSERT com tenant_id alheio é barrado pelo WITH CHECK — nas seis tabelas (a policy cobre até as duas que
    não têm rota de escrita própria, amc_fator_bruto/amc_resultado, herdando o tenant da execução)."""
    m = _criar_modelo(sessao_a)
    c = _criar_conjunto(sessao_a)
    e = _criar_execucao(sessao_a, m["id"], c["id"])
    ids_tenant = ids_por_slug(conexao_plat_app)
    tenant_a, tenant_b = ids_tenant["demo"], ids_tenant["demo2"]

    with conexao_plat_app.cursor() as cur:  # sem contexto nenhum: RLS não libera NADA, nem do próprio A
        for tabela in ("amc_modelo", "amc_conjunto_unidade", "amc_execucao", "amc_resultado"):
            cur.execute(f"SELECT count(*) AS n FROM plat.{tabela}")  # noqa: S608 — nome de tabela fixo, sem dado do chamador
            assert cur.fetchone()["n"] == 0, tabela

    contexto(conexao_plat_app, tenant_b, usuario_id=ids["b"]["id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.amc_modelo WHERE id = %s", (m["id"],))
        assert cur.fetchone()["n"] == 0
        cur.execute("SELECT count(*) AS n FROM plat.amc_execucao WHERE id = %s", (e["id"],))
        assert cur.fetchone()["n"] == 0
        with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="row-level security"):
            cur.execute(
                "INSERT INTO plat.amc_modelo(tenant_id, nome, definicao, versao_hash) "
                "VALUES (%s, 'intruso', '{}'::jsonb, %s)",
                (tenant_a, "0" * 64),
            )
    conexao_plat_app.rollback()

    contexto(conexao_plat_app, tenant_a, usuario_id=ids["a"]["id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.amc_modelo WHERE id = %s", (m["id"],))
        assert cur.fetchone()["n"] == 1
    conexao_plat_app.rollback()
