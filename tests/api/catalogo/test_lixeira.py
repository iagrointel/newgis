"""Lixeira, proteção e status (L0-03-h; ADR 0004 seção 9): apagar → lixeira → restaurar (uuid e compartilhamentos
iguais: diff = 0) → apagar → esvaziar (job); protegido 409; admin de inquilino não apaga protegido; superadmin apaga
com evento forcado; expurgo com relógio simulado (+31 d) apaga registro e tabela física (pg_class); restaurar item de
outro inquilino 404; camada usada por mapa sem cascata 409; lote apagar/restaurar/proteger; medida expurgo_s."""

import os
import time

import psycopg2
import pytest

from tests.api.catalogo.conftest import esperar_job, titulo_zt
from tests.api.test_rls import contexto, ids_por_slug

# 07/09: a base por trilha reescreve só o texto SQL, não o metadado do item
_TRAB = os.environ.get("PLAT_SCHEMA_TRABALHO", "plat_trabalho")

ITEM = "L0-03-catalogo"


def _snapshot(sessao, iid: str) -> dict:
    j = sessao.get(f"/api/itens/{iid}").json()
    comp = sessao.get(f"/api/itens/{iid}/compartilhamento").json()
    return {k: j[k] for k in ("id", "titulo", "tags", "acesso", "versao_atual", "favorito", "categorias")} | {
        "grupos": sorted(g["id"] for g in comp["grupos"]),
        "links": sorted(x["id"] for x in comp["links"]),
    }


def test_apagar_lixeira_restaurar_diff_zero(sessao_a, itens_a, editor_a):
    dono_c, _ = editor_a
    it = itens_a.criar("mapa", sessao=dono_c, tags=["zt", "lixeira"])
    iid = it["id"]
    g = dono_c.post("/api/grupos", json={"nome": titulo_zt("g-lixeira")}).json()
    assert (
        dono_c.put(f"/api/itens/{iid}/compartilhamento", json={"grupos": [g["id"]], "acesso": "inquilino"}).status_code
        == 200
    )
    assert dono_c.post(f"/api/itens/{iid}/links", json={}).status_code == 201
    assert dono_c.put(f"/api/favoritos/{iid}").status_code == 204
    antes = _snapshot(dono_c, iid)
    assert dono_c.delete(f"/api/itens/{iid}").status_code == 204
    assert dono_c.get(f"/api/itens/{iid}").status_code == 404
    assert dono_c.get(f"/api/itens?q=id:{iid}").json()["total"] == 0
    assert dono_c.get("/api/itens?favoritos=true&q=id:" + iid).json()["total"] == 0
    lix = dono_c.get("/api/lixeira").json()
    linha = next(x for x in lix["itens"] if x["id"] == iid)
    assert linha["apagado_por"]["id"] and linha["expurga_em"] > linha["apagado_em"]
    assert sessao_a.get(f"/api/lixeira?q=id:{iid}").json()["total"] == 1  # admin (apagar_tudo) vê a lixeira de todos
    r = dono_c.post(f"/api/lixeira/{iid}/restaurar")
    assert r.status_code == 200 and r.json()["id"] == iid
    assert _snapshot(dono_c, iid) == antes  # diff = 0: uuid, tags, acesso, grupos, links, favorito, versão
    assert dono_c.post(f"/api/lixeira/{iid}/restaurar").status_code == 409


def test_protegido_admin_do_inquilino_nao_apaga_superadmin_apaga_com_evento(sessao_a, sessao_plat, itens_a):
    it = itens_a.criar("mapa", titulo=titulo_zt("protegido"))
    iid = it["id"]
    assert sessao_a.put(f"/api/itens/{iid}", json={"protegido": True}).status_code == 200
    r = sessao_a.delete(f"/api/itens/{iid}")
    assert r.status_code == 409 and r.json()["erro"] == "item_protegido" and "proteção" in r.json()["mensagem"]
    r = sessao_a.post("/api/itens/lote", json={"ids": [iid], "acao": "apagar"})
    assert r.json()["feitos"] == 0 and r.json()["recusados"][0]["erro"] == "item_protegido"
    # superadmin sem o cabeçalho: não vê o item (404); com X-Plat-Inquilino: apaga com evento forcado
    assert sessao_plat.delete(f"/api/itens/{iid}").status_code == 404
    r = sessao_plat.delete(f"/api/itens/{iid}", headers={"X-Plat-Inquilino": "demo"})
    assert r.status_code == 204, r.text
    assert sessao_a.get(f"/api/itens/{iid}").status_code == 404
    ev = [
        e
        for e in sessao_a.get("/api/eventos?limite=30").json()["itens"]
        if e["tipo"] == "itens/apagar" and e["alvo_id"] == iid
    ]
    assert ev and ev[0]["propriedades"]["forcado"] is True and ev[0]["propriedades"]["protegido_em"] is True
    # o ator é o superadmin, que pertence ao inquilino plataforma: o id fica gravado, mas o login não resolve dentro
    # de demo (a junção com plat.usuario roda sob a RLS do inquilino). Quem apagou aparece por inteiro no log de
    # acesso (L0-02), não neste evento.
    assert ev[0]["ator"]["id"] == sessao_plat.get("/api/eu").json()["id"] and ev[0]["ator"]["login"] is None
    assert sessao_a.post(f"/api/lixeira/{iid}/restaurar").status_code == 200
    assert sessao_a.put(f"/api/itens/{iid}", json={"protegido": False}).status_code == 200
    # a variável plat.superadmin sozinha não basta (usuário comum forjando set_config)


def test_variavel_superadmin_forjada_nao_desprotege(conexao_plat_app, sessao_a, itens_a):
    it = itens_a.criar("mapa")
    sessao_a.put(f"/api/itens/{it['id']}", json={"protegido": True})
    ids = ids_por_slug(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT set_config('plat.superadmin', 'on', true)")
        cur.execute("SELECT plat.modo_superadmin() AS m")
        assert cur.fetchone()["m"] is False
        with pytest.raises(psycopg2.errors.RaiseException, match="item_protegido"):
            cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (it["id"],))
    conexao_plat_app.rollback()
    sessao_a.put(f"/api/itens/{it['id']}", json={"protegido": False})


def test_autoritativo_e_obsoleto(sessao_a, editor_a, itens_a):
    dono_c, _ = editor_a
    it = itens_a.criar("mapa", sessao=dono_c)
    r = dono_c.put(f"/api/itens/{it['id']}", json={"status": "autoritativo"})
    assert r.status_code == 403  # só editar_tudo
    r = dono_c.put(f"/api/itens/{it['id']}", json={"status": "obsoleto"})
    assert r.status_code == 200 and r.json()["status"] == "obsoleto"
    r = sessao_a.put(f"/api/itens/{it['id']}", json={"status": "autoritativo"})
    assert r.status_code == 200 and r.json()["status"] == "autoritativo" and r.json()["protegido"] is True
    assert dono_c.put(f"/api/itens/{it['id']}", json={"status": "nenhum"}).status_code == 403
    r = sessao_a.get("/api/eventos?limite=10").json()["itens"]
    st = next(e for e in r if e["tipo"] == "itens/status" and e["alvo_id"] == it["id"])
    assert st["propriedades"] == {"de": "obsoleto", "para": "autoritativo"}
    sessao_a.put(f"/api/itens/{it['id']}", json={"status": "nenhum", "protegido": False})


def test_restaurar_item_de_outro_inquilino_e_404(sessao_a, sessao_b, itens_b):
    it = itens_b.criar("mapa")
    assert sessao_b.delete(f"/api/itens/{it['id']}").status_code == 204
    assert sessao_a.post(f"/api/lixeira/{it['id']}/restaurar").status_code == 404
    assert sessao_a.get(f"/api/lixeira?q=id:{it['id']}").json()["total"] == 0
    assert sessao_b.post(f"/api/lixeira/{it['id']}/restaurar").status_code == 200


def test_expurgo_com_relogio_simulado_apaga_tabela_fisica(sessao_a, itens_a, conexao_plat_app, medida, worker_vivo):
    ids = ids_por_slug(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
    tabela = "zt_expurgo_" + titulo_zt()[-6:]
    with conexao_plat_app.cursor() as cur:
        cur.execute(f"CREATE TABLE plat_trabalho.{tabela} (id serial PRIMARY KEY, geom geometry(Point, 4326))")
        cur.execute(f"INSERT INTO plat_trabalho.{tabela}(geom) VALUES (ST_SetSRID(ST_MakePoint(-47.9, -15.8), 4326))")
    conexao_plat_app.commit()
    it = itens_a.criar(
        "camada_vetorial",
        dados={
            "schema": _TRAB,
            "tabela": tabela,
            "geometria": "Point",
            "srid": 4326,
            "campos": [{"nome": "id", "tipo": "integer"}],
            "fonte": "hospedada",
        },
    )
    outro = itens_a.criar("mapa")  # apagado agora: NÃO expurga (30 dias não passaram)
    assert sessao_a.delete(f"/api/itens/{it['id']}").status_code == 204
    # o relógio não se simula: o worker roda na unidade systemd, em PLAT_AMBIENTE=producao, e o parâmetro `agora` da
    # tarefa só é aceito em dev (ExpurgoParametros._so_em_dev). Envelhece-se o registro: apagado_em 31 dias atrás.
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")  # o commit acima zerou o contexto local
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
        cur.execute("UPDATE plat.item SET apagado_em = now() - interval '31 days' WHERE id = %s::uuid RETURNING id",
                    (it["id"],))
        assert cur.fetchall(), "o item apagado tem de estar visível para envelhecer (contexto + plat.lixeira)"
    conexao_plat_app.commit()
    t0 = time.perf_counter()
    r = sessao_a.post(
        "/api/jobs",
        json={"tipo": "catalogo.lixeira_expurgar", "parametros": {"dias": 30, "ids": [it["id"]]}},
    )
    assert r.status_code == 201, r.text
    job = esperar_job(sessao_a, r.json()["id"], 120)
    dt = time.perf_counter() - t0
    assert job["estado"] == "concluido", job
    assert job["resultado"]["expurgados"] == 1 and job["resultado"]["recusados"] == []
    medida(ITEM)(
        "expurgo_s",
        round(dt, 2),
        "s",
        "POST /api/jobs catalogo.lixeira_expurgar (1 camada apagada há 31 dias) até concluido",
    )
    with conexao_plat_app.cursor() as cur:
        # 07/09: o nome do schema vai no TEXTO da consulta, não como parâmetro — é o texto que
        # CursorSchemaAmbiente reescreve para o schema da trilha (base própria da fila/homolog);
        # como parâmetro, `plat_trabalho` batia no schema de PRODUÇÃO e dava permission denied.
        cur.execute(f"SELECT to_regclass('plat_trabalho.{tabela}') AS t")
        assert cur.fetchone()["t"] is None, "a tabela física tem de sumir no expurgo"
        cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
        cur.execute("SELECT count(*) AS n FROM plat.item WHERE id = %s::uuid", (it["id"],))
        assert cur.fetchone()["n"] == 0
    conexao_plat_app.rollback()
    itens_a.criados.remove(it["id"])
    ev = [e for e in sessao_a.get("/api/eventos?limite=30").json()["itens"] if e["tipo"] == "lixeira/expurgar"]
    assert ev and ev[0]["alvo_id"] == it["id"] and ev[0]["propriedades"]["tipo"] == "camada_vetorial"
    assert sessao_a.get(f"/api/itens/{outro['id']}").status_code == 200
    # esvaziar lixeira = job com dias = 0 e ids explícitos
    assert sessao_a.delete(f"/api/itens/{outro['id']}").status_code == 204
    r = sessao_a.post("/api/lixeira/esvaziar", json={"ids": [outro["id"]]})
    assert r.status_code == 202, r.text
    job = esperar_job(sessao_a, r.json()["job_id"], 120)
    assert job["estado"] == "concluido" and job["resultado"]["expurgados"] == 1
    itens_a.criados.remove(outro["id"])


def test_camada_usada_por_mapa_nao_apaga_sem_cascata(sessao_a, itens_a):
    cam = itens_a.criar("camada_vetorial")
    itens_a.criar("mapa", dados={"esquema_versao": 1, "corpo": {"camadas": [cam["id"]]}})
    r = sessao_a.delete(f"/api/itens/{cam['id']}")
    assert r.status_code == 409 and r.json()["erro"] == "possui_dependentes"
    r = sessao_a.post("/api/itens/lote", json={"ids": [cam["id"]], "acao": "apagar"})
    assert r.json()["recusados"][0]["erro"] == "possui_dependentes"


def test_lote_proteger_restaurar(sessao_a, itens_a):
    a, b = itens_a.criar("mapa"), itens_a.criar("mapa")
    r = sessao_a.post("/api/itens/lote", json={"ids": [a["id"], b["id"]], "acao": "proteger"})
    assert r.json()["feitos"] == 2
    r = sessao_a.post("/api/itens/lote", json={"ids": [a["id"], b["id"]], "acao": "apagar"})
    assert r.json()["feitos"] == 0 and len(r.json()["recusados"]) == 2
    sessao_a.post("/api/itens/lote", json={"ids": [a["id"], b["id"]], "acao": "desproteger"})
    r = sessao_a.post(
        "/api/itens/lote", json={"ids": [a["id"], b["id"], str(__import__("uuid").uuid4())], "acao": "apagar"}
    )
    assert r.json()["feitos"] == 2 and r.json()["recusados"][0]["erro"] == "item_inexistente"
    r = sessao_a.post("/api/itens/lote", json={"ids": [a["id"], b["id"]], "acao": "restaurar"})
    assert r.json()["feitos"] == 2
    r = sessao_a.post("/api/itens/lote", json={"ids": [a["id"]], "acao": "tags", "tags": ["zt-lote"]})
    assert r.json()["feitos"] == 1 and "zt-lote" in sessao_a.get(f"/api/itens/{a['id']}").json()["tags"]
    r = sessao_a.post("/api/itens/lote", json={"ids": [str(__import__("uuid").uuid4())] * 101, "acao": "apagar"})
    assert r.status_code == 422
