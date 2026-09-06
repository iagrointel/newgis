"""Item L3-01-a (modelo de dado do motor multicritério) pela API e pelo banco.

Cláusulas do portão provadas aqui:
- JSON Schema validado no POST; modelo inválido (peso negativo, fator sem transformação, soma de pesos zero, fator
  duplicado) devolve 422 com a cláusula violada;
- teste cruzado A→B falha em `plat.amc_modelo`, `plat.amc_execucao` e `plat.amc_resultado`, tanto pela API (por id
  direto) quanto pela role da aplicação com o contexto do outro inquilino;
- o hash gravado é o que o script independente (`scripts/amc_hash_independente.py`, que não importa o módulo da
  aplicação) recomputa a partir do que está no banco;
- REFUTAÇÃO do adversário: editar um modelo já executado cria versão nova, e a execução antiga continua apontando
  para a versão antiga, com o resultado inalterado.
"""

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from tests.api.amc import exemplos
from tests.api.test_rls import contexto, ids_por_slug

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "amc_hash_independente.py"
PREFIXO = "zt-amc"


# ---------------------------------------------------------------- apoio
def _criar_item(sessao, titulo: str) -> str:
    r = sessao.post("/api/itens", json={"tipo": "mapa", "titulo": f"{PREFIXO} {titulo}",
                                        "dados": {"esquema_versao": 1, "corpo": {}}})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _modelo_com_itens(sessao) -> dict:
    """O modelo de exemplo com as camadas apontando para itens REAIS do inquilino (a execução resolve a
    proveniência de cada camada e recusa camada inexistente)."""
    m = exemplos.modelo_valido()
    m["nome"] = f"{PREFIXO} modelo"
    m["fatores"][0]["camada"]["id"] = _criar_item(sessao, "raster")
    m["fatores"][1]["camada"]["id"] = _criar_item(sessao, "vias")
    m["restricoes"][0]["camada"]["id"] = _criar_item(sessao, "alagavel")
    return m


def _hash_por_fora(definicao: dict, tmp_path: Path) -> str:
    arquivo = tmp_path / "m.json"
    arquivo.write_text(json.dumps(definicao, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), "--arquivo", str(arquivo)], capture_output=True, text=True,
                       cwd=ROOT)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture
def modelo_a(sessao_a):
    """Modelo criado em A, escondido no fim (apagar = apagado_em; as versões ficam, é a proveniência)."""
    definicao = _modelo_com_itens(sessao_a)
    r = sessao_a.post("/api/amc/modelos", json={"definicao": definicao})
    assert r.status_code == 201, r.text
    modelo = r.json()
    yield modelo, definicao
    sessao_a.delete(f"/api/amc/modelos/{modelo['id']}")


@pytest.fixture
def conjunto_a(sessao_a):
    """Conjunto pequeno de feições (síncrono, sem job): 2 quadrados de ~1 km em Goiás."""
    colecao = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": "u1", "properties": {},
         "geometry": exemplos.area_retangulo(-49.30, -16.70, 0.01, 0.01)},
        {"type": "Feature", "id": "u2", "properties": {},
         "geometry": exemplos.area_retangulo(-49.28, -16.70, 0.01, 0.01)},
    ]}
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} conjunto", "tipo": "feicoes", "feicoes": colecao})
    assert r.status_code == 201, r.text
    conjunto = r.json()
    yield conjunto
    sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")


# ---------------------------------------------------------------- validação
def test_modelo_valido_nasce_com_hash_e_versao_1(modelo_a, tmp_path):
    modelo, definicao = modelo_a
    assert modelo["n_versoes"] == 1
    assert modelo["versao_hash"] == _hash_por_fora(definicao, tmp_path)
    assert modelo["definicao"] == definicao


@pytest.mark.parametrize("nome", sorted(exemplos.INVALIDOS))
def test_modelo_invalido_devolve_422_com_a_clausula(sessao_a, nome):
    construir, clausula = exemplos.INVALIDOS[nome]
    r = sessao_a.post("/api/amc/modelos", json={"definicao": construir()})
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "modelo_invalido"
    clausulas = [v["clausula"] for v in corpo["detalhe"]["violacoes"]]
    assert any(clausula in c for c in clausulas), (nome, clausulas)
    assert corpo["detalhe"]["esquema"] == "amc_modelo.v1"


def test_validar_nao_grava(sessao_a):
    antes = sessao_a.get("/api/amc/modelos").json()["total"]
    r = sessao_a.post("/api/amc/modelos/validar", json={"definicao": exemplos.modelo_sem_camada_externa()})
    assert r.status_code == 200 and r.json()["valido"] is True and len(r.json()["versao_hash"]) == 64
    r = sessao_a.post("/api/amc/modelos/validar", json={"definicao": exemplos.peso_negativo()})
    assert r.status_code == 422
    assert sessao_a.get("/api/amc/modelos").json()["total"] == antes


# ---------------------------------------------------------------- versionamento e imutabilidade
def test_editar_cria_versao_nova_e_a_anterior_continua_legivel(sessao_a, modelo_a, tmp_path):
    modelo, definicao = modelo_a
    hash_v1 = modelo["versao_hash"]
    nova = json.loads(json.dumps(definicao))
    nova["fatores"][0]["peso"] = 9.0
    r = sessao_a.put(f"/api/amc/modelos/{modelo['id']}", json={"definicao": nova})
    assert r.status_code == 200, r.text
    assert r.json()["versao_nova"] is True and r.json()["n_versoes"] == 2
    hash_v2 = r.json()["versao_hash"]
    assert hash_v2 != hash_v1 and hash_v2 == _hash_por_fora(nova, tmp_path)
    versoes = sessao_a.get(f"/api/amc/modelos/{modelo['id']}/versoes").json()
    assert [v["numero"] for v in versoes["versoes"]] == [1, 2]
    assert versoes["versao_atual"] == hash_v2
    antiga = sessao_a.get(f"/api/amc/modelos/{modelo['id']}/versoes/{hash_v1}")
    assert antiga.status_code == 200 and antiga.json()["definicao"] == definicao


def test_reenviar_a_mesma_definicao_nao_cria_versao(sessao_a, modelo_a):
    modelo, definicao = modelo_a
    r = sessao_a.put(f"/api/amc/modelos/{modelo['id']}", json={"definicao": definicao})
    assert r.status_code == 200 and r.json()["versao_nova"] is False and r.json()["n_versoes"] == 1


def test_versao_gravada_e_imutavel_para_a_aplicacao(conexao_plat_app, sessao_a, modelo_a):
    """Nem a role da aplicação edita ou apaga uma versão: o gatilho da migração 044 recusa."""
    import psycopg2

    modelo, _ = modelo_a
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    for sql in ("UPDATE plat.amc_modelo_versao SET definicao = '{}'::jsonb WHERE modelo_id = %s::uuid",
                "DELETE FROM plat.amc_modelo_versao WHERE modelo_id = %s::uuid"):
        with conexao_plat_app.cursor() as cur, pytest.raises(psycopg2.Error) as e:
            cur.execute(sql, (modelo["id"],))
        assert "amc_versao_imutavel" in str(e.value)
        conexao_plat_app.rollback()
        contexto(conexao_plat_app, ids["demo"])


def test_script_independente_confere_o_que_esta_no_banco(conexao_plat_app, modelo_a):
    """Cláusula do portão: o hash gravado é recomputável por fora, direto das linhas de plat.amc_modelo_versao."""
    ids = ids_por_slug(conexao_plat_app)
    r = subprocess.run([sys.executable, str(SCRIPT), "--tenant", str(ids["demo"])], capture_output=True, text=True,
                       cwd=ROOT)
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "divergentes: 0" in r.stdout and "cabeças órfãs: 0" in r.stdout
    assert modelo_a[0]["versao_hash"] in r.stdout


# ---------------------------------------------------------------- execução: proveniência congelada
def _criar_execucao(sessao, modelo_id: str, conjunto_id: str, **extra):
    return sessao.post("/api/amc/execucoes",
                       json={"modelo_id": modelo_id, "conjunto_id": conjunto_id, **extra})


def test_execucao_congela_versao_pesos_camadas_motor_e_semente(sessao_a, modelo_a, conjunto_a):
    modelo, definicao = modelo_a
    r = _criar_execucao(sessao_a, modelo["id"], conjunto_a["id"], semente=42)
    assert r.status_code == 201, r.text
    exec_json = r.json()
    assert exec_json["versao_hash"] == modelo["versao_hash"]
    assert exec_json["pesos"] == {"declividade": 3.0, "dist_via": 1.5}
    assert exec_json["semente"] == 42 and exec_json["estado"] == "registrada"
    assert exec_json["motor_versao"].startswith("amc/")
    camadas = exec_json["camadas"]
    assert len(camadas) == 3
    for c in camadas:
        assert c["tipo"] == "item" and c["titulo"].startswith(PREFIXO)
        assert "sha256" in c and "contagem" in c and "versao" in c
    sessao_a.delete(f"/api/amc/execucoes/{exec_json['id']}")


def test_execucao_recusa_camada_inexistente(sessao_a, conjunto_a):
    definicao = exemplos.modelo_sem_camada_externa()
    definicao["fatores"][0]["camada"] = {"tipo": "item", "id": str(uuid.uuid4())}
    r = sessao_a.post("/api/amc/modelos", json={"definicao": definicao})
    assert r.status_code == 201, r.text
    modelo = r.json()
    try:
        r = _criar_execucao(sessao_a, modelo["id"], conjunto_a["id"])
        assert r.status_code == 422 and r.json()["erro"] == "camada_inexistente"
    finally:
        sessao_a.delete(f"/api/amc/modelos/{modelo['id']}")


def test_pesos_da_execucao_sao_validados(sessao_a, modelo_a, conjunto_a):
    modelo, _ = modelo_a
    r = _criar_execucao(sessao_a, modelo["id"], conjunto_a["id"], pesos={"nao_existe": 1})
    assert r.status_code == 422 and r.json()["erro"] == "pesos_invalidos"
    r = _criar_execucao(sessao_a, modelo["id"], conjunto_a["id"], pesos={"declividade": 0, "dist_via": 0})
    assert r.status_code == 422 and r.json()["erro"] == "pesos_invalidos"


def test_refutacao_editar_modelo_executado_nao_muda_a_execucao_nem_o_resultado(
        sessao_a, conexao_plat_app, modelo_a, conjunto_a):
    """A refutação pedida no item: o adversário edita um modelo JÁ EXECUTADO e confere que (1) a execução antiga
    continua apontando para a versão antiga e (2) o resultado gravado não muda."""
    modelo, definicao = modelo_a
    r = _criar_execucao(sessao_a, modelo["id"], conjunto_a["id"], semente=7)
    assert r.status_code == 201, r.text
    execucao = r.json()
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "INSERT INTO plat.amc_resultado(execucao_id, tenant_id, unidade_id, favorabilidade, cobertura) "
            "VALUES (%s::uuid, %s, 'u1', 61.5, 1.0), (%s::uuid, %s, 'u2', 12.25, 0.5)",
            (execucao["id"], ids["demo"], execucao["id"], ids["demo"]),
        )
    conexao_plat_app.commit()
    try:
        antes = sessao_a.get(f"/api/amc/execucoes/{execucao['id']}/resultados").json()["resultados"]
        nova = json.loads(json.dumps(definicao))
        nova["fatores"][0]["peso"] = 99.0
        nova["fatores"][0]["transformacao"] = {"tipo": "linear", "minimo": 0, "maximo": 5, "direcao": "crescente"}
        r = sessao_a.put(f"/api/amc/modelos/{modelo['id']}", json={"definicao": nova})
        assert r.status_code == 200 and r.json()["versao_nova"] is True
        depois_modelo = sessao_a.get(f"/api/amc/modelos/{modelo['id']}").json()
        assert depois_modelo["versao_hash"] != execucao["versao_hash"]

        agora = sessao_a.get(f"/api/amc/execucoes/{execucao['id']}").json()
        assert agora["versao_hash"] == execucao["versao_hash"], "a execução mudou de versão ao editar o modelo"
        assert agora["pesos"] == execucao["pesos"] and agora["camadas"] == execucao["camadas"]
        assert agora["definicao"] == definicao, "a execução tem de devolver a definição QUE RODOU"
        depois = sessao_a.get(f"/api/amc/execucoes/{execucao['id']}/resultados").json()["resultados"]
        assert depois == antes and [x["favorabilidade"] for x in depois] == [61.5, 12.25]
    finally:
        contexto(conexao_plat_app, ids["demo"])
        with conexao_plat_app.cursor() as cur:
            cur.execute("DELETE FROM plat.amc_resultado WHERE execucao_id = %s::uuid", (execucao["id"],))
        conexao_plat_app.commit()
        sessao_a.delete(f"/api/amc/execucoes/{execucao['id']}")


# ---------------------------------------------------------------- inquilino cruzado (A→B)
def test_a_nao_le_modelo_execucao_nem_resultado_de_b_pela_api(sessao_a, sessao_b, conexao_plat_app):
    """Recursos criados em B, lidos por id direto com a sessão de A: 404 em toda rota."""
    definicao = _modelo_com_itens(sessao_b)
    r = sessao_b.post("/api/amc/modelos", json={"definicao": definicao})
    assert r.status_code == 201, r.text
    modelo_b = r.json()
    colecao = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": "b1", "properties": {},
         "geometry": exemplos.area_retangulo(-49.30, -16.70, 0.01, 0.01)}]}
    r = sessao_b.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} conjunto B", "tipo": "feicoes",
                                                  "feicoes": colecao})
    assert r.status_code == 201, r.text
    conjunto_b = r.json()
    r = sessao_b.post("/api/amc/execucoes", json={"modelo_id": modelo_b["id"], "conjunto_id": conjunto_b["id"]})
    assert r.status_code == 201, r.text
    execucao_b = r.json()
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo2"])
    with conexao_plat_app.cursor() as cur:
        cur.execute("INSERT INTO plat.amc_resultado(execucao_id, tenant_id, unidade_id, favorabilidade) "
                    "VALUES (%s::uuid, %s, 'b1', 88.0)", (execucao_b["id"], ids["demo2"]))
    conexao_plat_app.commit()
    try:
        alvos = [
            ("GET", f"/api/amc/modelos/{modelo_b['id']}"),
            ("GET", f"/api/amc/modelos/{modelo_b['id']}/versoes"),
            ("GET", f"/api/amc/modelos/{modelo_b['id']}/versoes/{modelo_b['versao_hash']}"),
            ("PUT", f"/api/amc/modelos/{modelo_b['id']}"),
            ("DELETE", f"/api/amc/modelos/{modelo_b['id']}"),
            ("GET", f"/api/amc/conjuntos/{conjunto_b['id']}"),
            ("GET", f"/api/amc/conjuntos/{conjunto_b['id']}/unidades"),
            ("DELETE", f"/api/amc/conjuntos/{conjunto_b['id']}"),
            ("GET", f"/api/amc/execucoes/{execucao_b['id']}"),
            ("GET", f"/api/amc/execucoes/{execucao_b['id']}/resultados"),
            ("DELETE", f"/api/amc/execucoes/{execucao_b['id']}"),
        ]
        for metodo, url in alvos:
            corpo = {"definicao": definicao} if metodo == "PUT" else None
            resposta = sessao_a.request(metodo, url, json=corpo)
            assert resposta.status_code in (401, 403, 404), (metodo, url, resposta.status_code, resposta.text)
        # e a execução de B não aparece na lista de A
        lista = sessao_a.get("/api/amc/execucoes?limite=200").json()["execucoes"]
        assert execucao_b["id"] not in [e["id"] for e in lista]
        assert modelo_b["id"] not in [m["id"] for m in sessao_a.get("/api/amc/modelos?limite=200").json()["modelos"]]
    finally:
        contexto(conexao_plat_app, ids["demo2"])
        with conexao_plat_app.cursor() as cur:
            cur.execute("DELETE FROM plat.amc_resultado WHERE execucao_id = %s::uuid", (execucao_b["id"],))
        conexao_plat_app.commit()
        sessao_b.delete(f"/api/amc/execucoes/{execucao_b['id']}")
        sessao_b.delete(f"/api/amc/conjuntos/{conjunto_b['id']}")
        sessao_b.delete(f"/api/amc/modelos/{modelo_b['id']}")


def test_rls_no_banco_esconde_amc_de_outro_inquilino(conexao_plat_app, sessao_a, modelo_a, conjunto_a):
    """Cláusula literal: o teste cruzado falha em plat.amc_modelo, plat.amc_execucao e plat.amc_resultado — aqui
    pela role da aplicação, que é quem a API usa."""
    modelo, _ = modelo_a
    r = _criar_execucao(sessao_a, modelo["id"], conjunto_a["id"])
    assert r.status_code == 201, r.text
    execucao = r.json()
    ids = ids_por_slug(conexao_plat_app)
    try:
        contexto(conexao_plat_app, ids["demo"])
        with conexao_plat_app.cursor() as cur:
            cur.execute("INSERT INTO plat.amc_resultado(execucao_id, tenant_id, unidade_id, favorabilidade) "
                        "VALUES (%s::uuid, %s, 'u1', 50.0)", (execucao["id"], ids["demo"]))
        conexao_plat_app.commit()

        contexto(conexao_plat_app, ids["demo2"])
        with conexao_plat_app.cursor() as cur:
            for tabela, coluna, valor in (("amc_modelo", "id", modelo["id"]),
                                          ("amc_modelo_versao", "modelo_id", modelo["id"]),
                                          ("amc_conjunto_unidade", "id", conjunto_a["id"]),
                                          ("amc_unidade", "conjunto_id", conjunto_a["id"]),
                                          ("amc_execucao", "id", execucao["id"]),
                                          ("amc_resultado", "execucao_id", execucao["id"])):
                cur.execute(f"SELECT count(*) AS n FROM plat.{tabela} WHERE {coluna} = %s::uuid", (valor,))
                assert cur.fetchone()["n"] == 0, f"{tabela} vazou para o outro inquilino"
        conexao_plat_app.rollback()

        # e nem escrever: WITH CHECK barra INSERT com tenant_id alheio
        import psycopg2

        contexto(conexao_plat_app, ids["demo2"])
        with conexao_plat_app.cursor() as cur, pytest.raises(psycopg2.Error):
            cur.execute("INSERT INTO plat.amc_resultado(execucao_id, tenant_id, unidade_id, favorabilidade) "
                        "VALUES (%s::uuid, %s, 'x', 1.0)", (execucao["id"], ids["demo"]))
        conexao_plat_app.rollback()
    finally:
        contexto(conexao_plat_app, ids["demo"])
        with conexao_plat_app.cursor() as cur:
            cur.execute("DELETE FROM plat.amc_resultado WHERE execucao_id = %s::uuid", (execucao["id"],))
        conexao_plat_app.commit()
        sessao_a.delete(f"/api/amc/execucoes/{execucao['id']}")
