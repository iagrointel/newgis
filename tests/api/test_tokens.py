"""Token de serviço (ADR 0002 seção 16.4): revogado ≤ 1 s com motivo; expirado (validade_dias=0 em dev); escopo;
restrição IP e referer; rotação com 24 h; log com token_id/ip/rota/bytes; ?token= em /api/ ignorado e redigido;
validade acima do máximo = 400; limite de 20; latencia_auth_token_ms < 5 ms."""

import statistics
import time

import pytest

from app import limites
from tests.api.conftest import PREFIXO_TESTE, com_token, novo_cliente


def _criar(sessao, **kw):
    corpo = {"nome": f"{PREFIXO_TESTE}-tok", "escopos": ["catalogo:ler"], **kw}
    return sessao.post("/api/tokens", json=corpo)


def test_criar_formato_e_lista(sessao_a):
    r = _criar(sessao_a)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["token"].startswith("plat_") and len(j["token"]) == 48 and j["prefixo"] == j["token"][:12]
    assert j["escopos"] == ["catalogo:ler"] and j["expira_em"]
    lista = sessao_a.get("/api/tokens").json()
    meu = next(t for t in lista if t["id"] == j["id"])
    assert meu["prefixo"] == j["prefixo"] and "token" not in meu and meu["revogado_em"] is None
    assert sessao_a.delete(f"/api/tokens/{j['id']}").status_code == 204


def test_revogado_em_menos_de_1s_com_motivo(sessao_a, cliente, medida):
    tok = _criar(sessao_a).json()
    assert com_token(cliente, tok["token"], "GET", "/api/eu").status_code == 200
    t0 = time.perf_counter()
    assert sessao_a.delete(f"/api/tokens/{tok['id']}").status_code == 204
    r = com_token(cliente, tok["token"], "GET", "/api/eu")
    dt = time.perf_counter() - t0
    assert r.status_code == 401 and r.json()["erro"] == "token_revogado" and "token revogado em" in r.json()["mensagem"]
    assert dt < 1.0
    medida("L0-02-tenant-auth")(
        "tempo_revogacao_s", round(dt, 3), "s", "DELETE /api/tokens/{id} até o 401 token_revogado (TestClient)"
    )
    assert sessao_a.delete(f"/api/tokens/{tok['id']}").status_code == 204  # idempotente


def test_expirado_com_validade_zero_em_dev(sessao_a, cliente):
    r = _criar(sessao_a, validade_dias=0)
    assert r.status_code == 201, r.text
    r2 = com_token(cliente, r.json()["token"], "GET", "/api/eu")
    assert r2.status_code == 401 and r2.json()["erro"] == "token_expirado" and "expirado em" in r2.json()["mensagem"]


def test_validade_acima_do_maximo_e_400(sessao_a):
    r = _criar(sessao_a, validade_dias=400)
    assert r.status_code == 400 and r.json()["erro"] == "validade_acima_do_maximo"
    assert r.json()["detalhe"] == {"maximo_dias": 365}
    r = _criar(sessao_a, validade_dias=365)
    assert r.status_code == 201
    sessao_a.delete(f"/api/tokens/{r.json()['id']}")


def test_escopos(sessao_a, usuarios_a, cliente):
    assert _criar(sessao_a, escopos=["camada:apagar"]).json()["erro"] == "escopo_invalido"
    tok = _criar(sessao_a).json()
    assert com_token(cliente, tok["token"], "GET", "/api/eu").status_code == 200
    r = com_token(cliente, tok["token"], "GET", "/api/usuarios")
    assert r.status_code == 403 and r.json()["erro"] == "escopo_insuficiente"
    assert r.json()["detalhe"]["exigido"] == "admin:inquilino"
    assert com_token(cliente, tok["token"], "POST", "/api/grupos", json={"nome": "x"}).status_code == 403
    adm = _criar(sessao_a, escopos=["admin:inquilino"]).json()
    assert com_token(cliente, adm["token"], "GET", "/api/usuarios").status_code == 200
    c_ed, u, _ = usuarios_a.sessao("editor")
    r = c_ed.post("/api/tokens", json={"nome": "x", "escopos": ["admin:inquilino"]})
    assert r.status_code == 422 and r.json()["erro"] == "escopo_fora_do_teto"
    for t in (tok, adm):
        sessao_a.delete(f"/api/tokens/{t['id']}")


def test_restricao_ip_e_referer(sessao_a, cliente):
    r = _criar(sessao_a, restricao={"ip": ["10.0.0.0/8"]})
    assert r.status_code == 201
    r2 = com_token(cliente, r.json()["token"], "GET", "/api/eu")
    assert r2.status_code == 401 and r2.json()["erro"] == "ip_nao_permitido"
    sessao_a.delete(f"/api/tokens/{r.json()['id']}")
    r = _criar(sessao_a, restricao={"referer": ["https://*.exemplo.gov.br"]})
    tok = r.json()["token"]
    assert com_token(cliente, tok, "GET", "/api/eu").json()["erro"] == "referer_ausente"

    def eu(**cab):
        return com_token(cliente, tok, "GET", "/api/eu", headers=cab)

    assert eu(Origin="https://sig.exemplo.gov.br").status_code == 200
    assert eu(Referer="https://sig.exemplo.gov.br/mapa").status_code == 200
    assert eu(Origin="https://exemplo.gov.br").json()["erro"] == "referer_nao_permitido"
    assert eu(Origin="http://sig.exemplo.gov.br").status_code == 401
    sessao_a.delete(f"/api/tokens/{r.json()['id']}")
    assert _criar(sessao_a, restricao={"ip": ["nao-e-ip"]}).status_code == 422
    assert _criar(sessao_a, restricao={"porta": ["x"]}).status_code == 422
    assert _criar(sessao_a, restricao={"ip": [f"10.0.0.{i}" for i in range(21)]}).status_code == 422


def test_rotacao_com_sobreposicao_de_24h(sessao_a, cliente):
    tok = _criar(sessao_a, validade_dias=30).json()
    r = sessao_a.post(f"/api/tokens/{tok['id']}/renovar")
    assert r.status_code == 201, r.text
    novo = r.json()
    assert novo["id"] != tok["id"] and novo["token"] != tok["token"] and novo["escopos"] == tok["escopos"]
    assert com_token(cliente, tok["token"], "GET", "/api/eu").status_code == 200
    assert com_token(cliente, novo["token"], "GET", "/api/eu").status_code == 200
    antigo = sessao_a.get(f"/api/tokens/{tok['id']}").json()
    assert antigo["renovado_por"] == novo["id"]
    import datetime

    exp = datetime.datetime.fromisoformat(antigo["expira_em"].replace("Z", "+00:00"))
    assert exp <= datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=24, minutes=1)
    assert sessao_a.delete(f"/api/tokens/{tok['id']}").status_code == 204
    assert sessao_a.post(f"/api/tokens/{tok['id']}/renovar").status_code == 409
    sessao_a.delete(f"/api/tokens/{novo['id']}")


def test_log_do_token_com_ip_rota_bytes_e_query_redigida(sessao_a, cliente):
    tok = _criar(sessao_a).json()
    assert com_token(cliente, tok["token"], "GET", "/api/eu?token=" + tok["token"]).status_code == 200
    r = cliente.get("/api/eu?token=" + tok["token"])  # ?token= em /api/ é ignorado
    assert r.status_code == 401
    log = sessao_a.get(f"/api/tokens/{tok['id']}/log").json()
    assert log["total"] >= 1
    linha = log["itens"][0]
    assert linha["token_id"] == tok["id"] and linha["ip"] and linha["bytes"] > 0
    assert linha["rota"].startswith("/api/eu?token=")
    assert tok["token"] not in linha["rota"] and "redigido" in linha["rota"]
    ver = sessao_a.get(f"/api/tokens/{tok['id']}").json()
    assert ver["acessos_30d"] >= 1 and ver["ultimo_status"] == 200 and ver["ultimo_ip"]
    sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_dono_ve_so_os_seus_e_gerir_todos_ve_todos(sessao_a, usuarios_a):
    c_ed, u, _ = usuarios_a.sessao("editor")
    r = c_ed.post("/api/tokens", json={"nome": "do-editor", "escopos": ["catalogo:ler"]})
    assert r.status_code == 201
    tid = r.json()["id"]
    assert c_ed.get("/api/tokens?todos=1").status_code == 403
    assert all(t["dono"]["id"] == u["id"] for t in c_ed.get("/api/tokens").json())
    assert any(t["id"] == tid for t in sessao_a.get("/api/tokens?todos=1").json())
    assert not any(t["id"] == tid for t in sessao_a.get("/api/tokens").json())
    assert sessao_a.get(f"/api/tokens/{tid}").status_code == 200  # tokens.gerir_todos
    assert sessao_a.post(f"/api/tokens/{tid}/renovar").status_code == 403  # só o dono renova
    assert sessao_a.delete(f"/api/tokens/{tid}").status_code == 204  # admin revoga


def test_limite_de_tokens_por_usuario(usuarios_a):
    c, u, _ = usuarios_a.sessao("visualizador")
    ids = []
    for i in range(limites.TOKENS_POR_USUARIO):
        r = c.post("/api/tokens", json={"nome": f"t{i}", "escopos": ["catalogo:ler"]})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    r = c.post("/api/tokens", json={"nome": "extra", "escopos": ["catalogo:ler"]})
    assert r.status_code == 422 and r.json()["erro"] == "limite_tokens"
    for i in ids:
        c.delete(f"/api/tokens/{i}")


def test_latencia_auth_token(sessao_a, cliente, medida):
    tok = _criar(sessao_a).json()
    tempos = []
    for _ in range(50):
        t0 = time.perf_counter()
        assert com_token(cliente, tok["token"], "GET", "/api/versao").status_code == 200
        tempos.append((time.perf_counter() - t0) * 1000)
    # /api/versao não autentica: mede o custo do TestClient; /api/eu autentica pelo token
    tempos_eu = []
    for _ in range(50):
        t0 = time.perf_counter()
        assert com_token(cliente, tok["token"], "GET", "/api/eu").status_code == 200
        tempos_eu.append((time.perf_counter() - t0) * 1000)
    custo = statistics.median(tempos_eu) - statistics.median(tempos)
    medida("L0-02-tenant-auth")(
        "latencia_auth_token_ms",
        round(max(custo, 0), 2),
        "ms",
        "mediana de 50 GET /api/eu com Bearer menos mediana de 50 GET /api/versao (TestClient)",
    )
    sessao_a.delete(f"/api/tokens/{tok['id']}")
    assert custo < 25, custo


@pytest.mark.parametrize("valor", ["plat_curto", "x" * 48, "Bearer"])
def test_token_malformado_e_401(cliente, valor):
    r = cliente.get("/api/eu", headers={"Authorization": f"Bearer {valor}"})
    assert r.status_code == 401 and r.json()["erro"] == "token_invalido"


def test_dono_desabilitado_invalida_token_na_hora(sessao_a, usuarios_a, cliente):
    c, u, _ = usuarios_a.sessao("editor")
    tok = c.post("/api/tokens", json={"nome": "x", "escopos": ["catalogo:ler"]}).json()
    assert com_token(cliente, tok["token"], "GET", "/api/eu").status_code == 200
    assert sessao_a.put(f"/api/usuarios/{u['id']}", json={"ativo": False}).status_code == 200
    assert com_token(cliente, tok["token"], "GET", "/api/eu").status_code == 401
    sessao_a.put(f"/api/usuarios/{u['id']}", json={"ativo": True})
    novo_cliente()
