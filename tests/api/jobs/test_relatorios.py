"""Relatórios do admin (item L0-07-e-relatorios) num inquilino temporário com worker próprio em subprocesso:
cada relatório gera CSV com o cabeçalho documentado (GET /api/relatorios/tipos) e N linhas = COUNT do dado sob a
RLS; agendamento cria `plat.agenda` com cron e roda agora; relatório de outro inquilino inacessível (404);
24 meses = 422; 2º pedido do mesmo tipo na mesma hora = 429; CSV de membros sem CPF e só com e-mail corporativo;
medida: relatório de itens com 10 mil itens ≤ 10 s (carga da máquina gravada junto)."""

import csv
import datetime
import io
import os
import re
import secrets
import socket
import time

import psycopg2
import pytest

from app.relatorios import tarefas
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api import semear_catalogo
from tests.api.conftest import InquilinoTemporario, entrar, novo_cliente
from tests.api.jobs.conftest import WorkerExtra, esperar
from tests.api.test_rls import contexto

ITEM = "L0-07-e-relatorios"
CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")


def _porta_livre(inicio: int = 18540, fim: int = 18599) -> int:
    for p in range(inicio, fim):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    pytest.fail("sem porta livre para o worker de teste")


@pytest.fixture(scope="module")
def worker(env):
    w = WorkerExtra(env, f"relatorios-{secrets.token_hex(2)}", 1, _porta_livre())
    yield w
    w.parar()


@pytest.fixture(scope="module")
def inq(sessao_plat):
    """Inquilino temporário com 3 membros (um com e-mail fora do domínio corporativo), 1 grupo, 3 itens."""
    i = InquilinoTemporario(sessao_plat)
    a = i.admin
    r = a.post("/api/usuarios", json={"login": "pessoal", "nome": "Conta pessoal", "perfil": "editor",
                                     "email": "pessoal@exemplo-pessoal.test"})
    assert r.status_code == 201, r.text
    org = a.get("/api/org").json()
    corpo = {"nome": org["nome"], "cor": org["cor"], "idioma_padrao": org["idioma_padrao"],
             "centro": org["mapa"]["centro"], "zoom": org["mapa"]["zoom"], "basemap": org["mapa"]["basemap"],
             "srid_padrao": org["mapa"]["srid_padrao"], "cota_bytes": org["armazenamento"]["cota_bytes"],
             "cota_usuarios": org["usuarios"]["cota"], "auth": {**org["auth"], "dominios_email": ["orgao.gov.test"]}}
    assert a.put("/api/org", json=corpo).status_code == 200
    r = a.post("/api/usuarios", json={"login": "corporativo", "nome": "Conta corporativa", "perfil": "visualizador",
                                     "email": "corporativo@orgao.gov.test"})
    assert r.status_code == 201, r.text
    r = a.post("/api/grupos", json={"nome": "grupo-relatorio"})
    assert r.status_code == 201, r.text
    i.grupo_id = r.json()["id"]
    i.itens = []
    for n in range(3):
        corpo_item = {"tipo": "mapa", "titulo": f"mapa relatório {n}", "dados": {"esquema_versao": 1, "corpo": {}}}
        r = a.post("/api/itens", json=corpo_item)
        assert r.status_code == 201, r.text
        i.itens.append(r.json()["id"])
        assert a.get(f"/api/itens/{r.json()['id']}").status_code == 200  # acesso contado no log (itens.acessos_30d)
    yield i
    i.apagar()


def _conexao(env):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    return con


def _contagem(env, inq, sql: str, params=()) -> int:
    con = _conexao(env)
    try:
        contexto(con, inq.id, usuario_id=inq.admin_id, login="admin")
        with con.cursor() as cur:
            cur.execute(sql, params)
            return int(cur.fetchone()["n"])
    finally:
        con.rollback()
        con.close()


def _gerar(inq, worker, tipo: str, **params) -> dict:
    r = inq.admin.post("/api/relatorios", json={"tipo": tipo, **params})
    assert r.status_code == 201, r.text
    job = esperar(inq.admin, r.json()["id"], timeout=120)
    assert job["estado"] == "concluido", job
    return job


def _csv(inq, job_id: str) -> tuple[list[str], list[dict]]:
    r = inq.admin.get(f"/api/relatorios/{job_id}/csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv"), r.text[:200]
    leitor = csv.DictReader(io.StringIO(r.text))
    linhas = list(leitor)
    return list(leitor.fieldnames or []), linhas


def test_tipos_com_cabecalho_documentado_e_limites(inq):
    r = inq.admin.get("/api/relatorios/tipos")
    assert r.status_code == 200, r.text
    tipos = {x["tipo"]: x for x in r.json()["tipos"]}
    assert set(tipos) == set(tarefas.TIPOS)
    for t in tarefas.TIPOS:
        assert tipos[t]["cabecalho"] == tarefas.CABECALHOS[t] and tipos[t]["descricao"]
    assert r.json()["limites"] == {"janela_dias": 366, "linhas_max": 10000, "por_tipo_por_hora": 1}


def test_cada_relatorio_gera_csv_com_n_linhas_igual_ao_count(env, inq, worker):
    esperados = {
        "membros": _contagem(env, inq, "SELECT count(*) AS n FROM plat.usuario"),
        "itens": _contagem(env, inq, "SELECT count(*) AS n FROM plat.item WHERE apagado_em IS NULL"),
        "grupos": _contagem(env, inq, "SELECT count(*) AS n FROM plat.grupo"),
    }
    assert esperados["membros"] == 3 and esperados["itens"] == 3 and esperados["grupos"] >= 1
    jobs = {}
    for tipo in ("membros", "itens", "grupos", "atividade", "uso"):
        jobs[tipo] = _gerar(inq, worker, tipo)
    fim = datetime.datetime.fromisoformat(jobs["atividade"]["resultado"]["ate"].replace("Z", "+00:00"))
    inicio = datetime.datetime.fromisoformat(jobs["atividade"]["resultado"]["desde"].replace("Z", "+00:00"))
    esperados["atividade"] = _contagem(
        env, inq,
        "SELECT count(*) AS n FROM (SELECT 1 FROM plat.evento WHERE em >= %s AND em < %s "
        "GROUP BY (em AT TIME ZONE 'UTC')::date, tipo) x",
        (inicio, fim),
    )
    assert esperados["atividade"] >= 1  # os eventos de preparação (usuarios/criar, grupos/criar, itens/adicionar)
    esperados["uso"] = (fim.date() - inicio.date()).days + (1 if fim.time() > datetime.time(0, 0) else 0)
    for tipo, job in jobs.items():
        cab, linhas = _csv(inq, job["id"])
        assert cab == tarefas.CABECALHOS[tipo], (tipo, cab)
        assert len(linhas) == esperados[tipo], (tipo, len(linhas), esperados[tipo])
        assert job["resultado"]["linhas"] == esperados[tipo] and job["resultado"]["truncado"] is False
    # membros: e-mail só corporativo, nunca CPF; itens: o acesso de preparação aparece em acessos_30d
    _, membros = _csv(inq, jobs["membros"]["id"])
    por_login = {m["login"]: m for m in membros}
    assert por_login["corporativo"]["email_corporativo"] == "corporativo@orgao.gov.test"
    assert por_login["pessoal"]["email_corporativo"] == ""
    assert not CPF.search(inq.admin.get(f"/api/relatorios/{jobs['membros']['id']}/csv").text)
    assert por_login["admin"]["itens"] == "3" and por_login["admin"]["grupos"] == "1"
    _, itens = _csv(inq, jobs["itens"]["id"])
    assert all(int(x["acessos_30d"]) >= 1 for x in itens), itens
    _, grupos = _csv(inq, jobs["grupos"]["id"])
    assert grupos[0]["membros"] == "1" and grupos[0]["dono"] == "admin"
    # a lista de relatórios mostra os 5, com filtro por tipo
    lista = inq.admin.get("/api/relatorios?limite=50").json()
    assert {j["parametros"]["tipo"] for j in lista["itens"]} >= set(tarefas.TIPOS)
    assert all(j["parametros"]["tipo"] == "uso" for j in inq.admin.get("/api/relatorios?tipo=uso").json()["itens"])
    assert "relatorios/gerar" in {e["tipo"] for e in inq.admin.get("/api/eventos?limite=50").json()["itens"]}


def test_limites_24_meses_422_e_um_por_tipo_por_hora_429(inq, worker):
    ha_800_dias = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=800)).isoformat()
    r = inq.admin.post("/api/relatorios", json={"tipo": "atividade", "desde": ha_800_dias})
    assert r.status_code == 422 and "366" in r.json()["mensagem"], r.text
    r = inq.admin.post("/api/relatorios", json={"tipo": "atividade", "desde": "ontem"})
    assert r.status_code == 422
    # membros já foi pedido nesta hora pelo teste anterior: 429 com o limite declarado
    r = inq.admin.post("/api/relatorios", json={"tipo": "membros"})
    assert r.status_code == 429 and r.json()["erro"] == "relatorio_limite_hora", r.text
    assert r.json()["detalhe"] == {"tipo": "membros", "por_hora": 1}
    r = inq.admin.post("/api/relatorios", json={"tipo": "inexistente"})
    assert r.status_code == 422


def test_relatorio_de_outro_inquilino_inacessivel(inq, sessao_a, sessao_b):
    job = inq.admin.get("/api/relatorios?tipo=grupos").json()["itens"][0]
    assert inq.admin.get(f"/api/relatorios/{job['id']}/csv").status_code == 200
    for outra in (sessao_a, sessao_b):
        assert outra.get(f"/api/relatorios/{job['id']}").status_code == 404
        assert outra.get(f"/api/relatorios/{job['id']}/csv").status_code == 404
    # editor comum do mesmo inquilino não tem org.exportar
    c = novo_cliente()
    r = entrar(c, inq.slug, "pessoal", _senha_de(inq, "pessoal"))
    assert r.status_code == 200
    assert c.get("/api/relatorios/tipos").status_code == 403
    assert c.get(f"/api/relatorios/{job['id']}/csv").status_code == 403
    assert c.get("/api/atividade").status_code == 403


def _senha_de(inq, login: str) -> str:
    r = inq.admin.post(f"/api/usuarios/{_id_de(inq, login)}/senha")
    assert r.status_code == 200, r.text
    return r.json()["senha_temporaria"]


def _id_de(inq, login: str) -> int:
    return next(u["id"] for u in inq.admin.get("/api/usuarios?limite=100").json()["itens"] if u["login"] == login)


def test_agendamento_cria_agenda_e_roda_agora(inq, worker):
    pedido = {"tipo": "grupos", "periodicidade": "semanal", "hora": 7, "email": False}
    r = inq.admin.post("/api/relatorios/agendas", json=pedido)
    assert r.status_code == 201, r.text
    ag = r.json()
    try:
        assert ag["tipo"] == "relatorios.gerar" and ag["cron"] == "0 7 * * 1" and ag["ativa"] is True
        assert ag["parametros"] == {"tipo": "grupos", "dias": 7, "email": False} and ag["proxima_em"]
        repetido = inq.admin.post("/api/relatorios/agendas", json={"tipo": "grupos", "periodicidade": "semanal"})
        assert repetido.status_code == 409
        r = inq.admin.post("/api/relatorios/agendas", json={"tipo": "uso", "periodicidade": "mensal", "hora": 30})
        assert r.status_code == 422
        assert ag["id"] in {a["id"] for a in inq.admin.get("/api/relatorios/agendas").json()["itens"]}
        assert ag["id"] in {a["id"] for a in inq.admin.get("/api/agendas?tipo=relatorios.gerar").json()["itens"]}
        assert "relatorios/agendar" in {e["tipo"] for e in inq.admin.get("/api/eventos?limite=20").json()["itens"]}
        r = inq.admin.post(f"/api/agendas/{ag['id']}/rodar-agora")
        assert r.status_code == 201, r.text
        job = esperar(inq.admin, r.json()["id"], timeout=120)
        assert job["estado"] == "concluido" and job["agenda_id"] == ag["id"], job
        assert job["resultado"]["tipo"] == "grupos" and job["resultado"]["linhas"] >= 1
        assert job["resultado"]["email"] is None  # email=False: nada enviado
        cab, _ = _csv(inq, job["id"])
        assert cab == tarefas.CABECALHOS["grupos"]
    finally:
        assert inq.admin.delete(f"/api/agendas/{ag['id']}").status_code == 204


def test_painel_atividade(inq):
    r = inq.admin.get("/api/atividade?dias=7")
    assert r.status_code == 200, r.text
    p = r.json()
    assert set(p) == {"janela", "totais", "top_itens", "eventos_por_dia", "eventos_por_tipo", "acessos_por_dia"}
    assert p["janela"]["dias"] == 7 and p["totais"]["eventos"] >= 3 and p["totais"]["acessos"] >= 3
    assert p["totais"]["usuarios_ativos"] >= 1 and p["totais"]["itens_novos"] >= 3
    assert len(p["top_itens"]) == 3 and {x["id"] for x in p["top_itens"]} == set(inq.itens)
    assert all(x["acessos"] >= 1 and x["dono"] == "admin" for x in p["top_itens"])
    assert p["eventos_por_dia"] and sum(x["n"] for x in p["eventos_por_dia"]) == p["totais"]["eventos"]
    assert {"itens/adicionar", "grupos/criar"} <= {x["tipo"] for x in p["eventos_por_tipo"]}
    assert inq.admin.get("/api/atividade?dias=400").status_code == 422


def test_medida_relatorio_de_itens_com_10_mil_itens(env, inq, worker, medida):
    con = _conexao(env)
    try:
        semear_catalogo.semear(con, inq.slug, 10_000)
    finally:
        con.close()
    total = _contagem(env, inq, "SELECT count(*) AS n FROM plat.item WHERE apagado_em IS NULL")
    assert total >= 10_000
    carga = os.getloadavg()[0]
    with open("/proc/meminfo", encoding="utf-8") as f:
        livre_kb = next(int(li.split()[1]) for li in f if li.startswith("MemAvailable"))
    ontem = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)).isoformat()
    r = inq.admin.post("/api/relatorios", json={"tipo": "itens", "desde": ontem})
    assert r.status_code == 201, r.text
    t0 = time.perf_counter()
    job = esperar(inq.admin, r.json()["id"], timeout=300)
    parede = round(time.perf_counter() - t0, 2)
    assert job["estado"] == "concluido", job
    assert job["resultado"]["linhas"] == 10_000 and job["resultado"]["truncado"] is True
    cab, linhas = _csv(inq, job["id"])
    assert cab == tarefas.CABECALHOS["itens"] and len(linhas) == 10_000
    gravar = medida(ITEM)
    gravar("relatorio_itens_10k_duracao_s", job["duracao_s"], "s",
           f"job relatorios.gerar itens com {total} itens (duracao_s do job, worker em subprocesso na trilha)")
    gravar("relatorio_itens_10k_parede_s", parede, "s",
           "POST /api/relatorios até estado concluido (inclui a espera na fila)")
    gravar("carga_1min", round(carga, 2), "load", "os.getloadavg()[0] no instante do pedido")
    gravar("ram_livre_gb", round(livre_kb / 1024 / 1024, 2), "GB",
           "MemAvailable de /proc/meminfo no instante do pedido")
    gravar("medido_em", datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "instante", "relógio UTC")
    assert job["duracao_s"] <= 10, (job["duracao_s"], carga)
