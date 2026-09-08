"""Rotas de `plat.conexao` (item L6-02-a-modelo-conexao-e-seguranca): CRUD + `POST /api/conexoes/{id}/testar`.
Refutação do item: "adversário usa host público que redireciona para 127.0.0.1:8150 e host cujo DNS muda entre
a validação e o uso" — a mecânica de SSRF em si é provada em `tests/unit/test_conexao_seguranca.py`; aqui
prova-se que a rota RECUSA na entrada (nunca deixa uma conexão insegura ser gravada), que a credencial nunca
sai na resposta, e a mesma trava cruzada A→B (RLS) do resto do catálogo."""

import json

import psycopg2.extras
import pytest

from app.schema_ambiente import CursorSchemaAmbiente  # honra PLAT_SCHEMA (make homolog / bases por trilha)
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug

URL_PUBLICA = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/35"


def _conexao_direta(env):
    return psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)


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


# ---------------------------------------------------------------- L6-02-l-saude: histórico + estado agregado
URL_404_ESTAVEL = "https://api.github.com/repos/inexistente-zt-l6-02-l/tambem-inexistente"  # API estável, 404 rápido
URL_ESRI_CENSUS = "https://sampleserver6.arcgisonline.com/arcgis/rest/services/Census/MapServer"  # amostra da Esri
URL_ESRI_FREEWAY = "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/USA_Freeway_System/FeatureServer"  # noqa: E501
URL_STAC_S2 = "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a"
URL_WMS_OSM = "https://ows.terrestris.de/osm/service"


@pytest.mark.lento
def test_saude_historico_vazio_antes_do_primeiro_teste(sessao_a, limpar_conexoes):
    r = _criar(sessao_a, "historico-vazio")
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    r_hist = sessao_a.get(f"/api/conexoes/{cid}/saude-historico")
    assert r_hist.status_code == 200, r_hist.text
    assert r_hist.json()["itens"] == []
    assert sessao_a.get(f"/api/conexoes/{cid}").json()["estado_saude"] == "nunca_testada"


@pytest.mark.lento
def test_saude_historico_grava_apos_testar_e_estado_fica_ok(sessao_a, limpar_conexoes):
    r = _criar(sessao_a, "historico-ok")
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    assert sessao_a.post(f"/api/conexoes/{cid}/testar").status_code == 200

    r_hist = sessao_a.get(f"/api/conexoes/{cid}/saude-historico")
    itens = r_hist.json()["itens"]
    assert len(itens) == 1
    assert itens[0]["ok"] is True
    assert itens[0]["status"] == 200
    assert itens[0]["verificada_em"] is not None

    r_ver = sessao_a.get(f"/api/conexoes/{cid}")
    assert r_ver.json()["estado_saude"] == "ok"
    assert r_ver.json()["disponibilidade_30d_pct"] == 100.0
    assert r_ver.json()["disponibilidade_30d_total"] == 1


@pytest.mark.lento
def test_conexao_com_url_que_responde_404_fica_fora_em_1_teste(sessao_a, limpar_conexoes):
    """Refutação do item: "URL inválida fica vermelha em <= 1 ciclo" — aqui "1 ciclo" é o 1º teste (manual ou
    periódico); URL real (passa na validação de SSRF na entrada) mas que sempre responde 404."""
    r = _criar(sessao_a, "fora-do-ar", url=URL_404_ESTAVEL)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    assert sessao_a.get(f"/api/conexoes/{cid}").json()["estado_saude"] == "nunca_testada"

    r_teste = sessao_a.post(f"/api/conexoes/{cid}/testar")
    assert r_teste.status_code == 200, r_teste.text
    assert r_teste.json()["ok"] is False
    assert r_teste.json()["saude"] == "erro"

    r_ver = sessao_a.get(f"/api/conexoes/{cid}")
    assert r_ver.json()["estado_saude"] == "fora"
    r_hist = sessao_a.get(f"/api/conexoes/{cid}/saude-historico").json()["itens"]
    assert len(r_hist) == 1 and r_hist[0]["ok"] is False and r_hist[0]["status"] == 404


@pytest.mark.lento
def test_conexao_degradada_quando_a_mais_recente_passa_mas_uma_das_5_falhou(sessao_a, limpar_conexoes):
    r = _criar(sessao_a, "degradado", url=URL_404_ESTAVEL)
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    assert sessao_a.post(f"/api/conexoes/{cid}/testar").status_code == 200  # falha (404) -> fora
    assert sessao_a.get(f"/api/conexoes/{cid}").json()["estado_saude"] == "fora"

    assert sessao_a.patch(f"/api/conexoes/{cid}", json={"url": URL_PUBLICA}).status_code == 200
    assert sessao_a.post(f"/api/conexoes/{cid}/testar").status_code == 200  # passa (200) -> degradado (falhou antes)
    r_ver = sessao_a.get(f"/api/conexoes/{cid}")
    assert r_ver.json()["estado_saude"] == "degradado"
    assert r_ver.json()["disponibilidade_30d_total"] == 2
    assert r_ver.json()["disponibilidade_30d_pct"] == 50.0


def test_saude_historico_limite_e_teto(sessao_a, limpar_conexoes):
    r = _criar(sessao_a, "limite-historico")
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    r0 = sessao_a.get(f"/api/conexoes/{cid}/saude-historico")
    assert r0.status_code == 200
    r1 = sessao_a.get(f"/api/conexoes/{cid}/saude-historico?limite=0")
    assert r1.status_code == 200  # limite < 1 é grampeado para 1, nunca 422 (a tela nunca quebra por isso)
    r2 = sessao_a.get(f"/api/conexoes/{cid}/saude-historico?limite=9999")
    assert r2.status_code == 200  # grampeado para o teto (30), nunca um erro


def test_saude_historico_rls_cruzada_404(sessao_a, sessao_b, limpar_conexoes):
    r = _criar(sessao_a, "historico-rls")
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    assert sessao_b.get(f"/api/conexoes/{cid}/saude-historico").status_code == 404


# ---------------------------------------------------------------- L6-05-proveniencia-camada-externa
@pytest.mark.lento
def test_publicar_camada_le_licenca_declarada_do_arcgis_rest(sessao_a, limpar_conexoes):
    r = _criar(sessao_a, "publicar-esri", url=URL_ESRI_CENSUS, tipo="esri_rest")
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    r_pub = sessao_a.post(f"/api/conexoes/{cid}/publicar")
    assert r_pub.status_code == 201, r_pub.text
    item = r_pub.json()
    assert item["tipo"] == "conexao"
    proc = item["dados"]["procedencia"]
    assert proc["licenca"] == "US Bureau of the Census: http://www.census.gov"
    assert proc["url"] == URL_ESRI_CENSUS
    assert proc["data_do_dado"] is None  # referenciada, nunca copiada: não existe "data do dado"
    assert proc["sha256"]  # hash do corpo lido, prova de que algo foi de fato baixado e conferido
    assert item["dados"]["parametros"]["conexao_id"] == cid
    assert item["creditos"] == proc["licenca"]  # atribuicao = licenca quando o esri_rest so declara copyrightText


@pytest.mark.lento
def test_publicar_camada_licenca_nao_e_valor_padrao(sessao_a, limpar_conexoes):
    """Refutação do item: confere que a licença é a do SERVIÇO (duas conexões, dois protocolos, dois textos
    DIFERENTES e verificáveis contra o que o serviço de fato devolve — nunca um valor fixo do nosso código)."""
    r1 = _criar(sessao_a, "licenca-esri", url=URL_ESRI_FREEWAY, tipo="esri_rest")
    r2 = _criar(sessao_a, "licenca-stac", url=URL_STAC_S2, tipo="stac")
    c1, c2 = r1.json()["id"], r2.json()["id"]
    limpar_conexoes.extend([c1, c2])
    proc1 = sessao_a.post(f"/api/conexoes/{c1}/publicar").json()["dados"]["procedencia"]
    proc2 = sessao_a.post(f"/api/conexoes/{c2}/publicar").json()["dados"]["procedencia"]
    assert proc1["licenca"] and proc2["licenca"]
    assert proc1["licenca"] != proc2["licenca"]
    assert "Esri" in proc1["licenca"]
    assert proc2["licenca"] == "proprietary"


@pytest.mark.lento
def test_publicar_camada_wms_le_access_constraints_e_titulo(sessao_a, limpar_conexoes):
    r = _criar(sessao_a, "publicar-wms", url=URL_WMS_OSM, tipo="wms")
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    item = sessao_a.post(f"/api/conexoes/{cid}/publicar").json()
    proc = item["dados"]["procedencia"]
    assert proc["licenca"] and "OpenStreetMap" in proc["licenca"]
    assert item["creditos"] and "OpenStreetMap" in item["creditos"]


def test_publicar_camada_campo_nao_declarado_fica_none_nao_valor_padrao(sessao_a, limpar_conexoes):
    """protocolo sem sondagem (http) nunca INVENTA licença/fonte: fica None, e a ressalva explica por quê."""
    r = _criar(sessao_a, "publicar-http", url=URL_PUBLICA, tipo="http")
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    item = sessao_a.post(f"/api/conexoes/{cid}/publicar").json()
    proc = item["dados"]["procedencia"]
    assert proc["licenca"] is None
    assert proc["fonte"] is None
    assert proc["limites"] and any("não tem metadado padronizado" in m for m in proc["limites"])


def test_publicar_conexao_inexistente_404(sessao_a):
    assert sessao_a.post("/api/conexoes/00000000-0000-0000-0000-000000000000/publicar").status_code == 404


def test_publicar_credencial_nunca_aparece_na_procedencia(sessao_a, limpar_conexoes):
    segredo = "segredo-l6-05-nao-e-real-XYZ"
    r = _criar(sessao_a, "publicar-com-credencial", url=URL_PUBLICA, tipo="http", credencial=segredo)
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    item = sessao_a.post(f"/api/conexoes/{cid}/publicar")
    assert segredo not in item.text
