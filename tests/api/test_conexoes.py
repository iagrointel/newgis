"""Rotas de `plat.conexao` (item L6-02-a-modelo-conexao-e-seguranca): CRUD + `POST /api/conexoes/{id}/testar`.
Refutação do item: "adversário usa host público que redireciona para 127.0.0.1:8150 e host cujo DNS muda entre
a validação e o uso" — a mecânica de SSRF em si é provada em `tests/unit/test_conexao_seguranca.py`; aqui
prova-se que a rota RECUSA na entrada (nunca deixa uma conexão insegura ser gravada), que a credencial nunca
sai na resposta, e a mesma trava cruzada A→B (RLS) do resto do catálogo."""

import json

import psycopg2.extras
import pytest

from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug

URL_PUBLICA = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/35"


def _conexao_direta(env):
    return psycopg2.connect(env["PLAT_DSN"], cursor_factory=psycopg2.extras.RealDictCursor)


@pytest.fixture
def limpar_conexoes(sessao_a):
    """Apaga pelo id, mesmo que a asserção falhe no meio."""
    criadas = []
    yield criadas
    for cid in criadas:
        sessao_a.delete(f"/api/conexoes/{cid}")


def _criar(sessao, nome_sufixo, url=URL_PUBLICA, tipo="ogc_api", **extra):
    corpo = {"tipo": tipo, "nome": f"{PREFIXO_TESTE}-conexao-{nome_sufixo}", "url": url, **extra}
    return sessao.post("/api/conexoes", json=corpo)


def test_criar_listar_ver_fluxo_basico(sessao_a, limpar_conexoes):
    r = _criar(sessao_a, "basica")
    assert r.status_code == 201, r.text
    item = r.json()
    limpar_conexoes.append(item["id"])
    assert item["tipo"] == "ogc_api"
    assert item["modo"] == "referenciada"  # padrão (decisão B6)
    assert item["saude"] == "nunca_testada"
    assert item["tem_credencial"] is False

    r_ver = sessao_a.get(f"/api/conexoes/{item['id']}")
    assert r_ver.status_code == 200
    assert r_ver.json()["url"] == URL_PUBLICA

    r_lista = sessao_a.get("/api/conexoes")
    assert r_lista.status_code == 200
    assert item["id"] in {i["id"] for i in r_lista.json()["itens"]}


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8150/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.1.2.3/geoserver/wms",
        "http://192.168.0.1/",
        "file:///etc/passwd",
    ],
)
def test_criar_recusa_url_insegura(sessao_a, url):
    r = _criar(sessao_a, "insegura", url=url)
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "url_insegura"
    # a conexão NUNCA fica gravada — nem em estado "bloqueada": a recusa é na entrada, não há linha nenhuma
    r_lista = sessao_a.get(f"/api/conexoes?q={PREFIXO_TESTE}")  # noqa: q não é filtro real, só documenta a intenção
    for it in r_lista.json()["itens"]:
        assert it["url"] != url


def test_criar_url_publica_normal_e_aceita(sessao_a, limpar_conexoes):
    r = _criar(sessao_a, "publica-normal")
    assert r.status_code == 201, r.text
    limpar_conexoes.append(r.json()["id"])


def test_editar_para_url_insegura_tambem_e_recusado(sessao_a, limpar_conexoes):
    r = _criar(sessao_a, "editar-para-insegura")
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    r2 = sessao_a.patch(f"/api/conexoes/{cid}", json={"url": "http://169.254.169.254/"})
    assert r2.status_code == 422, r2.text
    # a URL antiga continua valendo (a edição falhou inteira, não parcialmente)
    assert sessao_a.get(f"/api/conexoes/{cid}").json()["url"] == URL_PUBLICA


def test_credencial_nunca_aparece_na_resposta_nem_no_log(sessao_a, limpar_conexoes, caplog):
    segredo = "segredo-de-teste-nao-e-real-XYZ789"
    with caplog.at_level("DEBUG"):
        r = _criar(sessao_a, "com-credencial", credencial=segredo)
    assert r.status_code == 201, r.text
    item = r.json()
    limpar_conexoes.append(item["id"])
    assert item["tem_credencial"] is True
    assert "credencial" not in item
    assert segredo not in json.dumps(item)
    assert segredo not in r.text

    r_ver = sessao_a.get(f"/api/conexoes/{item['id']}")
    assert segredo not in r_ver.text
    r_lista = sessao_a.get("/api/conexoes")
    assert segredo not in r_lista.text

    for registro in caplog.records:
        assert segredo not in registro.getMessage()
        assert segredo not in json.dumps(registro.__dict__, default=str)


def test_rls_cruzada_nao_ve_edita_nem_apaga_conexao_de_outro_inquilino(sessao_a, sessao_b, env, limpar_conexoes):
    r = _criar(sessao_a, "rls")
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    limpar_conexoes.append(cid)

    con = _conexao_direta(env)
    try:
        ids = ids_por_slug(con)
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", ("demo",))
            admin_demo = cur.fetchone()["usuario_id"]
        contexto(con, ids["demo"], usuario_id=admin_demo, login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT tenant_id FROM plat.conexao WHERE id = %s::uuid", (cid,))
            row = cur.fetchone()
    finally:
        con.close()
    assert row["tenant_id"] == ids["demo"]

    assert sessao_b.get(f"/api/conexoes/{cid}").status_code == 404
    assert sessao_b.patch(f"/api/conexoes/{cid}", json={"nome": f"{PREFIXO_TESTE}-roubada"}).status_code == 404
    assert sessao_b.delete(f"/api/conexoes/{cid}").status_code == 404
    assert sessao_b.post(f"/api/conexoes/{cid}/testar").status_code == 404
    assert cid not in {i["id"] for i in sessao_b.get("/api/conexoes").json()["itens"]}


def test_nome_duplicado_409(sessao_a, limpar_conexoes):
    r1 = _criar(sessao_a, "duplicada")
    assert r1.status_code == 201
    limpar_conexoes.append(r1.json()["id"])
    r2 = _criar(sessao_a, "duplicada")  # mesmo nome final
    assert r2.status_code == 409, r2.text


def test_config_grande_demais_422(sessao_a):
    r = _criar(sessao_a, "config-grande", config={"camadas": ["x" * 10_000] * 10})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "config_grande_demais"


@pytest.mark.lento
def test_testar_conexao_publica_atualiza_saude(sessao_a, limpar_conexoes):
    r = _criar(sessao_a, "testar-saude")
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    limpar_conexoes.append(cid)

    r_teste = sessao_a.post(f"/api/conexoes/{cid}/testar")
    assert r_teste.status_code == 200, r_teste.text
    corpo = r_teste.json()
    assert corpo["ok"] is True
    assert corpo["status"] == 200
    assert corpo["saude"] == "ok"
    assert corpo["latencia_ms"] >= 0

    r_ver = sessao_a.get(f"/api/conexoes/{cid}")
    assert r_ver.json()["saude"] == "ok"
    assert r_ver.json()["saude_verificada_em"] is not None
