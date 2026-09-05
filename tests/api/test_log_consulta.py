"""GET /api/log e /api/eventos (ADR 0002 seção 9.3): filtros, janela > 92 dias = 422, CSV, org.log_ver exigido,
superadmin com X-Plat-Inquilino lê outro inquilino em transação só leitura e deixa evento de trilha."""

import csv
import io


def test_log_json_filtros_e_janela(sessao_a, ids):
    sessao_a.get("/api/eu")
    r = sessao_a.get("/api/log?limite=5&rota=/api/eu&status=200")
    assert r.status_code == 200 and r.json()["total"] >= 1
    item = r.json()["itens"][0]
    assert {
        "id",
        "em",
        "usuario_id",
        "usuario",
        "token_id",
        "ip",
        "metodo",
        "rota",
        "status",
        "bytes",
        "tempo_ms",
        "agente",
        "resultado",
    } <= set(item)
    assert item["usuario"] == ids["a"]["login"] and item["rota"].startswith("/api/eu")
    assert sessao_a.get("/api/log?status=2xx&limite=1").status_code == 200
    assert sessao_a.get("/api/log?status=abc").status_code == 422
    r = sessao_a.get("/api/log?desde=2026-01-01T00:00:00Z&ate=2026-06-01T00:00:00Z")
    assert r.status_code == 422 and r.json()["erro"] == "janela_maior_que_92_dias"
    assert sessao_a.get("/api/log?desde=lixo").status_code == 422
    assert sessao_a.get("/api/log?limite=1001").status_code == 422
    assert sessao_a.get(f"/api/log?usuario_id={ids['a']['id']}&limite=1").json()["total"] >= 1


def test_log_csv(sessao_a):
    r = sessao_a.get("/api/log?formato=csv&limite=5")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers.get("content-disposition", "")
    linhas = list(csv.DictReader(io.StringIO(r.text)))
    assert linhas and {"em", "rota", "status", "bytes"} <= set(linhas[0])


def test_log_exige_org_log_ver(usuarios_a):
    c, _, _ = usuarios_a.sessao("editor")
    r = c.get("/api/log")
    assert (
        r.status_code == 403
        and r.json()["erro"] == "sem_privilegio"
        and r.json()["detalhe"]["exigido"] == "org.log_ver"
    )
    assert c.get("/api/eventos").status_code == 403


def test_eventos_filtros(sessao_a, ids):
    r = sessao_a.get("/api/eventos?tipo=usuarios/entrar&limite=5")
    assert r.status_code == 200 and r.json()["total"] >= 1
    e = r.json()["itens"][0]
    assert (
        e["tipo"] == "usuarios/entrar"
        and e["ator"]["login"]
        and e["propriedades"].get("fator") in ("senha", "totp", "recuperacao")
    )
    assert {"id", "em", "tipo", "ator", "alvo_tipo", "alvo_id", "propriedades", "ip", "req_id"} == set(e)
    assert sessao_a.get(f"/api/eventos?ator_id={ids['a']['id']}&limite=1").json()["total"] >= 1
    assert sessao_a.get("/api/eventos?desde=2020-01-01T00:00:00Z").status_code == 422


def test_superadmin_le_outro_inquilino_so_leitura_com_trilha(sessao_plat, sessao_b, ids):
    r = sessao_plat.get("/api/log?limite=3", headers={"X-Plat-Inquilino": "demo2"})
    assert r.status_code == 200
    assert all(
        i["usuario_id"] in (None, ids["b"]["id"]) or i["usuario_id"] != ids["plat"]["id"] for i in r.json()["itens"]
    )
    r = sessao_plat.get("/api/usuarios", headers={"X-Plat-Inquilino": "demo2"})
    assert r.status_code == 200 and any(u["login"] == ids["b"]["login"] for u in r.json()["itens"])
    ev = sessao_b.get("/api/eventos?tipo=inquilinos/leitura_superadmin&limite=5").json()
    assert ev["total"] >= 2 and ev["itens"][0]["propriedades"]["operador"] == ids["plat"]["login"]
    # escrita com o cabeçalho não existe: a rota recusa o cabeçalho (400) antes de qualquer efeito
    r = sessao_plat.post(
        "/api/usuarios",
        json={"login": "zt-intruso", "nome": "x", "perfil": "editor"},
        headers={"X-Plat-Inquilino": "demo2"},
    )
    assert r.status_code == 400 and r.json()["erro"] == "cabecalho_nao_aceito"
    assert not any(u["login"] == "zt-intruso" for u in sessao_b.get("/api/usuarios?q=zt-intruso").json()["itens"])
