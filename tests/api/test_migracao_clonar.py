"""Item L2-08-b-clonar-camadas-hospedadas.

Duas fontes: (1) um serviço PÚBLICO da Esri gravado com URL e data (`tests/migracao/respostas/publicas/`) servido
pelo portal de mentira — camada com domínios codificados, subtipos, relacionamento 1:N com uma tabela e anexos;
(2) o PRÓPRIO FeatureServer da plataforma, subido na trilha em IP público (a defesa de SSRF recusa loopback),
lido com token de serviço pelo cabeçalho X-Esri-Authorization. A clonagem roda de forma síncrona (`CtxFalso` do
inventário) — o job real é o mesmo código com o worker por fora."""

import base64
import hashlib
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import psycopg2
import pytest

from app.migracao import tarefas
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_migracao_inventario import CtxFalso, _conexao_direta
from tests.api.test_rls import contexto, ids_por_slug
from tests.migracao.portal_falso import PortalFalso, ip_publico

RAIZ = Path(__file__).resolve().parents[2]
PORTA_FONTE = 8503


@pytest.fixture
def limpar(sessao_a, conexao_plat_app):
    """Apaga conexões, registros de clonagem, camadas e domínios `zt`/clonados criados pelo teste."""
    criados = {"conexoes": [], "clones": [], "itens": [], "dominios": []}
    yield criados
    ids = ids_por_slug(conexao_plat_app)
    admin = _admin_id(conexao_plat_app, "demo")
    contexto(conexao_plat_app, ids["demo"], usuario_id=admin, login="admin")
    with conexao_plat_app.cursor() as cur:
        # camadas criadas pela clonagem mesmo quando o job falhou no meio (o cartão não as lista ainda)
        cur.execute("SELECT id FROM plat.item WHERE dados->'clonagem'->>'clone_id' = ANY(%s)", (criados["clones"],))
        for r in cur.fetchall():
            if str(r["id"]) not in criados["itens"]:
                criados["itens"].append(str(r["id"]))
    conexao_plat_app.commit()
    for c in criados["clones"]:
        sessao_a.delete(f"/api/migracao/clones/{c}")
    for c in criados["conexoes"]:
        sessao_a.delete(f"/api/conexoes/{c}")
    contexto(conexao_plat_app, ids["demo"], usuario_id=admin, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "DELETE FROM plat.relacionamento WHERE origem_item_id = ANY(%s::uuid[]) "
            "OR destino_item_id = ANY(%s::uuid[])",
            (criados["itens"], criados["itens"]),
        )
        for item_id in criados["itens"]:
            cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (item_id,))
            r = cur.fetchone()
            if r and r["dados"].get("schema"):
                cur.execute(f'DROP TABLE IF EXISTS "{r["dados"]["schema"]}"."{r["dados"]["tabela"]}" CASCADE')
            cur.execute("DELETE FROM plat.dominio_campo WHERE item_id = %s::uuid", (item_id,))
            cur.execute("DELETE FROM plat.camada_subtipo WHERE item_id = %s::uuid", (item_id,))
            cur.execute("DELETE FROM plat.item WHERE id = %s::uuid", (item_id,))
        for d in criados["dominios"]:
            cur.execute("DELETE FROM plat.dominio_campo WHERE dominio_id = %s::uuid", (d,))
            cur.execute("DELETE FROM plat.dominio WHERE id = %s::uuid", (d,))
    conexao_plat_app.commit()


def _admin_id(con, slug):
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        return cur.fetchone()["usuario_id"]


def _rodar(sessao_a, env, clone_id: str) -> dict:
    eu = sessao_a.get("/api/eu").json()
    con = _conexao_direta(env)
    try:
        tenant_id = ids_por_slug(con)[eu["inquilino"]["slug"]]
    finally:
        con.close()
    ctx = CtxFalso(tenant_id, eu["id"], str(uuid.uuid4()))
    return tarefas.migracao_clonar(ctx, clone_id)


def _pedir_clone(sessao_a, limpar, base: str, url_servico: str, credencial: str | None = None) -> dict:
    r = sessao_a.post(
        "/api/conexoes",
        json={
            "tipo": "esri_rest",
            "nome": f"{PREFIXO_TESTE}-clone-{uuid.uuid4().hex[:6]}",
            "url": base,
            "credencial": credencial,
        },
    )
    assert r.status_code == 201, r.text
    limpar["conexoes"].append(r.json()["id"])
    r = sessao_a.post("/api/migracao/clones", json={"conexao_id": r.json()["id"], "url_servico": url_servico})
    assert r.status_code == 201, r.text
    limpar["clones"].append(r.json()["id"])
    return r.json()


def _registrar_itens(sessao_a, limpar, clone_id: str) -> dict:
    cartao = sessao_a.get(f"/api/migracao/clones/{clone_id}").json()
    for c in cartao["camadas"]:
        if c.get("item_id") and c["item_id"] not in limpar["itens"]:
            limpar["itens"].append(c["item_id"])
    return cartao


# ---------------------------------------------------------------- fonte 1: serviço público gravado
def test_servico_publico_gravado_clona_esquema_dominios_relacionamento_e_anexos(sessao_a, env, limpar, medida):
    with PortalFalso() as portal:
        url = f"{portal.base}/server/rest/services/publico/FeatureServer"
        pedido = _pedir_clone(sessao_a, limpar, portal.base, url)
        assert pedido["estado"] == "pendente" and pedido["job_id"]
        t0 = time.perf_counter()
        relatorio = _rodar(sessao_a, env, pedido["id"])
        segundos = round(time.perf_counter() - t0, 2)
        cartao = _registrar_itens(sessao_a, limpar, pedido["id"])
        assert cartao["estado"] == "concluido", cartao
        por_origem = {c["origem_id"]: c for c in cartao["camadas"]}
        camada, tabela = por_origem[0], por_origem[1]
        # contagem igual nas duas (amostra gravada: 20 feições e as linhas relacionadas)
        assert camada["verificacao"]["contagem_igual"] and camada["verificacao"]["contagem_destino"] == 20
        assert tabela["verificacao"]["contagem_igual"] and tabela["e_tabela"] is True
        assert camada["verificacao"]["hash_amostra_igual"] is True, camada["verificacao"]
        # domínios e subtipos reproduzidos na camada
        doms = sessao_a.get(f"/api/camadas/{camada['item_id']}/dominios").json()["ligacoes"]
        assert {d["campo"] for d in doms} >= {"requesttype", "status"}
        limpar["dominios"] += list({d["dominio_id"] for d in doms if d.get("dominio_id")})
        # os `types` deste serviço têm id texto: não são subtipos (aviso no relatório), o domínio do campo fica
        assert any("tipos de feição" in a for a in camada["avisos"])
        fs = sessao_a.get(f"/rest/services/{camada['item_id']}/FeatureServer/0").json()
        assert any(f.get("domain") for f in fs["fields"])
        # relacionamento reproduzido e consultável por queryRelatedRecords no NOSSO FeatureServer
        rels = relatorio["relacionamentos"]
        assert rels and rels[0].get("id"), rels
        nome_rel = rels[0]["nome"]
        con = _conexao_direta(env)
        try:
            eu = sessao_a.get("/api/eu").json()
            contexto(con, ids_por_slug(con)["demo"], usuario_id=eu["id"], login="admin")
            with con.cursor() as cur:
                cur.execute(
                    f'SELECT fid, requestid FROM "{_dados(sessao_a, tabela["item_id"])["schema"]}".'
                    f'"{_dados(sessao_a, tabela["item_id"])["tabela"]}" LIMIT 1'
                )
                filha = cur.fetchone()
                d0 = _dados(sessao_a, camada["item_id"])
                cur.execute(
                    f'SELECT fid FROM "{d0["schema"]}"."{d0["tabela"]}" WHERE requestid = %s', (filha["requestid"],)
                )
                pai = cur.fetchone()
        finally:
            con.rollback()
            con.close()
        assert pai is not None
        r = sessao_a.get(
            f"/rest/services/{camada['item_id']}/FeatureServer/0/queryRelatedRecords",
            params={"relationshipId": nome_rel, "objectIds": str(pai["fid"])},
        )
        assert r.status_code == 200, r.text
        grupos = r.json().get("relatedRecordGroups") or []
        relacionados = {g2["objectId"] for g in grupos for g2 in g.get("relatedRecordGroups", [])}
        assert filha["fid"] in relacionados, r.json()
        # anexos: sha256 igual ao dos bytes gravados (3 amostras)
        publico = portal.servidor.publico
        esperados = {
            hashlib.sha256(base64.b64decode(b)).hexdigest()
            for oid in publico["anexos"]["0"].values()
            for b in oid["bytes"].values()
        }
        obtidos = {a["sha256"] for a in camada["anexos"]["sha256"]}
        assert camada["anexos"]["anexos"] == 3 and obtidos == esperados
        assert relatorio["escritas"] == 20 + tabela["verificacao"]["contagem_destino"]
        # relatório por camada
        assert {"origem_id", "item_id", "verificacao", "dominios", "anexos", "avisos"} <= set(camada)
        medida("L2-08-b-clonar-camadas-hospedadas")(
            "segundos_clone_servico_publico_gravado",
            segundos,
            "s",
            "2 camadas, 20+ feições, 3 anexos, portal de mentira",
        )
        # re-execução sem mudança na origem: nenhuma escrita
        relatorio2 = _rodar(sessao_a, env, pedido["id"])
        assert relatorio2["escritas"] == 0
        cartao2 = sessao_a.get(f"/api/migracao/clones/{pedido['id']}").json()
        assert all(c.get("reexecucao") == "sem_mudanca" for c in cartao2["camadas"]), cartao2["camadas"]


def _dados(sessao_a, item_id: str) -> dict:
    r = sessao_a.get(f"/api/itens/{item_id}")
    assert r.status_code == 200, r.text
    return r.json()["dados"]


# ---------------------------------------------------------------- fonte 2: o próprio FeatureServer da plataforma
@pytest.fixture
def servidor_fonte(env):
    ip = ip_publico()
    if ip is None:
        pytest.skip("máquina sem IP público (a defesa de SSRF recusa loopback)")
    amb = {**os.environ, **env, "PLAT_POOL_MIN": "1", "PLAT_POOL_MAX": "2"}
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tests.e2e.servidor_local:app",
            "--host",
            ip,
            "--port",
            str(PORTA_FONTE),
            "--log-level",
            "warning",
        ],
        cwd=str(RAIZ),
        env=amb,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://{ip}:{PORTA_FONTE}"
    limite = time.monotonic() + 40
    while time.monotonic() < limite:
        try:
            if httpx.get(base + "/api/saude", timeout=2).status_code in (200, 401, 404):
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    else:
        proc.send_signal(signal.SIGTERM)
        pytest.fail("servidor-fonte da trilha não subiu em 40 s")
    yield base
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def _camada_fonte(conexao_plat_app, n_feicoes: int, com_dominio: bool = True) -> tuple[str, dict]:
    """Camada de pontos em demo com `n_feicoes` linhas e um domínio codificado no campo categoria."""
    from app.catalogo.camada_nova import criar_camada

    ids = ids_por_slug(conexao_plat_app)
    admin = _admin_id(conexao_plat_app, "demo")
    contexto(conexao_plat_app, ids["demo"], usuario_id=admin, login="admin")
    with conexao_plat_app.cursor() as cur:
        item_id, dados = criar_camada(
            cur,
            admin,
            f"{PREFIXO_TESTE} fonte clone",
            [
                {"nome": "nome", "tipo": "text", "alias": "Nome"},
                {"nome": "categoria", "tipo": "text"},
                {"nome": "valor", "tipo": "double precision"},
                {"nome": "quando", "tipo": "timestamptz"},
            ],
            geometria="Point",
            srid=4326,
        )
        psycopg2.extras.execute_values(
            cur,
            f'INSERT INTO "{dados["schema"]}"."{dados["tabela"]}" (nome, categoria, valor, quando, geom) VALUES %s',
            [
                (
                    f"f{i}",
                    "AB"[i % 2],
                    i * 1.5,
                    "1969-07-20T20:17:00Z",
                    f"SRID=4326;POINT({-46 + i * 0.001} {-23 + i * 0.001})",
                )
                for i in range(n_feicoes)
            ],
            template="(%s, %s, %s, %s, ST_GeomFromEWKT(%s))",
            page_size=1000,
        )
        if com_dominio:
            cur.execute(
                "INSERT INTO plat.dominio (tenant_id, nome, tipo, tipo_campo, valores, criado_por, atualizado_por) "
                "VALUES (plat.tenant_atual(), %s, 'codificado', 'text', %s::jsonb, %s, %s) RETURNING id",
                (
                    f"{PREFIXO_TESTE} categoria {uuid.uuid4().hex[:6]}",
                    '[{"codigo":"A","descricao":"Alfa","ordem":1,"ativo":true},{"codigo":"B","descricao":"Beta","ordem":2,"ativo":true}]',
                    admin,
                    admin,
                ),
            )
            dom = cur.fetchone()["id"]
            cur.execute(
                "INSERT INTO plat.dominio_campo (tenant_id, item_id, campo, dominio_id) VALUES (plat.tenant_atual(), "
                "%s::uuid, 'categoria', %s::uuid)",
                (item_id, dom),
            )
    conexao_plat_app.commit()
    return item_id, dados


def test_proprio_featureserver_como_fonte(sessao_a, env, limpar, servidor_fonte, conexao_plat_app, token_a, medida):
    n = 2000
    fonte_id, _dados_fonte = _camada_fonte(conexao_plat_app, n)
    limpar["itens"].append(fonte_id)
    url = f"{servidor_fonte}/rest/services/{fonte_id}/FeatureServer"
    # o token viaja em X-Esri-Authorization (mesmo cabeçalho que os clientes Esri usam contra o nosso servidor)
    assert (
        httpx.get(
            url + "/0?f=json", headers={"X-Esri-Authorization": f"Bearer {token_a['token']}"}, timeout=20
        ).status_code
        == 200
    )
    pedido = _pedir_clone(sessao_a, limpar, servidor_fonte, url, credencial=token_a["token"])
    carga = os.getloadavg()[0]
    t0 = time.perf_counter()
    relatorio = _rodar(sessao_a, env, pedido["id"])
    segundos = round(time.perf_counter() - t0, 2)
    cartao = _registrar_itens(sessao_a, limpar, pedido["id"])
    assert cartao["estado"] == "concluido", cartao
    (camada,) = cartao["camadas"]
    assert camada["verificacao"]["contagem_origem"] == n == camada["verificacao"]["contagem_destino"]
    assert camada["verificacao"]["hash_amostra_igual"] is True, camada["verificacao"]
    assert relatorio["escritas"] == n
    doms = sessao_a.get(f"/api/camadas/{camada['item_id']}/dominios").json()["ligacoes"]
    assert any(d["campo"] == "categoria" for d in doms)
    limpar["dominios"] += [d["dominio_id"] for d in doms if d.get("dominio_id")]
    d = _dados(sessao_a, camada["item_id"])
    con = _conexao_direta(env)
    try:
        contexto(con, ids_por_slug(con)["demo"], usuario_id=_admin_id(con, "demo"), login="admin")
        with con.cursor() as cur:
            cur.execute(
                f'SELECT quando, ST_X(geom) AS x FROM "{d["schema"]}"."{d["tabela"]}" ORDER BY oid_origem LIMIT 1'
            )
            primeira = cur.fetchone()
    finally:
        con.rollback()
        con.close()
    assert primeira["quando"].year == 1969 and abs(primeira["x"] - (-46)) < 1e-6  # data antes de 1970 preservada
    medida("L2-08-b-clonar-camadas-hospedadas")(
        "segundos_clone_2000_feicoes_fonte_propria",
        segundos,
        "s",
        f"carga_1min={carga:.1f} (clone do próprio FeatureServer da trilha)",
    )
    # segunda execução sem mudança = 0 escritas
    assert _rodar(sessao_a, env, pedido["id"])["escritas"] == 0


def test_clone_de_a_invisivel_para_b_e_url_fora_da_conexao(sessao_a, sessao_b, limpar):
    with PortalFalso() as portal:
        pedido = _pedir_clone(
            sessao_a, limpar, portal.base, f"{portal.base}/server/rest/services/publico/FeatureServer"
        )
        assert sessao_b.get(f"/api/migracao/clones/{pedido['id']}").status_code == 404
        assert sessao_b.delete(f"/api/migracao/clones/{pedido['id']}").status_code == 404
        r = sessao_a.post(
            "/api/migracao/clones",
            json={
                "conexao_id": limpar["conexoes"][-1],
                "url_servico": "https://outro-host.invalido/rest/services/x/FeatureServer",
            },
        )
        assert r.status_code == 422 and r.json()["erro"] == "url_servico_fora_da_conexao"
