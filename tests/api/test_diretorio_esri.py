"""Diretório de serviços compatível com Esri por token (item L2-04-b).

O que se prova aqui: um cliente que recebe SÓ a URL `/svc/<token>/rest/services` descobre as camadas
sozinho, lê o descritor do serviço e da camada com as chaves que a doc da Esri obriga, troca
usuário/senha por um token curto em `generateToken`, e NÃO enxerga camada de outro inquilino.

A segregação não é filtro de aplicação: a consulta corre como `plat_app` com o inquilino do token no
contexto, e a RLS é quem apaga a camada do vizinho. O teste cruzado (`test_camada_de_b_ausente...`)
existe para que isso pare de ser afirmação e vire medida."""

from __future__ import annotations

import json
import secrets

import psycopg2
import psycopg2.extras
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE, novo_cliente

# chaves que a doc da Esri obriga em cada recurso (services-reference/enterprise)
CHAVES_INFO = {"currentVersion", "fullVersion", "authInfo"}
CHAVES_AUTHINFO = {"isTokenBasedSecurity", "tokenServicesUrl", "shortLived"}
CHAVES_CATALOGO = {"currentVersion", "folders", "services"}
CHAVES_SERVICO = {
    "currentVersion", "serviceDescription", "hasVersionedData", "supportsDisconnectedEditing",
    "syncEnabled", "maxRecordCount", "supportedQueryFormats", "capabilities", "description",
    "copyrightText", "spatialReference", "initialExtent", "fullExtent", "allowGeometryUpdates",
    "units", "layers", "tables",
}
CHAVES_CAMADA = {
    "currentVersion", "id", "name", "type", "description", "geometryType", "extent", "objectIdField",
    "globalIdField", "displayField", "fields", "capabilities", "supportedQueryFormats",
    "hasAttachments", "relationships", "typeIdField", "types", "timeInfo", "editFieldsInfo",
    "indexes", "advancedQueryCapabilities", "maxRecordCount", "drawingInfo",
    "ownershipBasedAccessControlForFeatures",
}
CHAVES_CAMPO = {"name", "type", "alias", "nullable", "editable", "domain"}


def _sufixo() -> str:
    return secrets.token_hex(4)


class Camada:
    """Tabela física + item de catálogo, como a ingestão os deixa. Sem worker: o que este item mede é
    o DIRETÓRIO, e uma tabela criada aqui é indistinguível, para o descritor, de uma carregada."""

    def __init__(self, env, sessao, titulo: str):
        self.env = env
        self.sessao = sessao
        self.schema = env["PLAT_SCHEMA_TRABALHO"]
        self.tabela = f"zt_l204b_{_sufixo()}"
        self.item_id: str | None = None
        self.estilo_id: str | None = None
        self._criar_tabela()
        self._criar_item(titulo)

    def _con(self):
        con = psycopg2.connect(self.env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
        con.autocommit = True
        return con

    def _criar_tabela(self):
        with self._con() as con, con.cursor() as cur:
            cur.execute(
                f'CREATE TABLE "{self.schema}"."{self.tabela}" ('
                "  fid bigserial PRIMARY KEY,"
                "  globalid uuid NOT NULL DEFAULT gen_random_uuid(),"
                "  nome text,"
                "  populacao integer,"
                "  medido_em date,"
                "  criado_em timestamptz NOT NULL DEFAULT now(),"
                "  atualizado_em timestamptz NOT NULL DEFAULT now(),"
                "  geom geometry(Polygon, 4326))"
            )
            cur.execute(
                f'CREATE INDEX "ix_{self.tabela}_geom" ON "{self.schema}"."{self.tabela}" USING gist (geom)')
            cur.execute(f'CREATE INDEX "ix_{self.tabela}_nome" ON "{self.schema}"."{self.tabela}" (nome)')
            cur.execute(
                f'INSERT INTO "{self.schema}"."{self.tabela}"(nome, populacao, medido_em, geom) VALUES '
                "('Alfa', 120, '2026-01-10', ST_MakeEnvelope(-47.1, -15.9, -47.0, -15.8, 4326)),"
                "('Beta', 4300, '2026-02-20', ST_MakeEnvelope(-46.9, -15.7, -46.8, -15.6, 4326))"
            )

    def _criar_item(self, titulo: str):
        r = self.sessao.post("/api/itens", json={
            "tipo": "camada_vetorial",
            "titulo": titulo,
            "resumo": "camada do teste do diretório Esri",
            "tags": ["teste", "esri"],
            "dados": {
                "schema": self.schema, "tabela": self.tabela, "geometria": "Polygon", "srid": 4326,
                "campos": [{"nome": "nome", "tipo": "text"}, {"nome": "populacao", "tipo": "integer"}],
                "fonte": "hospedada",
            },
        })
        assert r.status_code == 201, r.text
        self.item_id = r.json()["id"]

    def dar_estilo(self, corpo: dict):
        r = self.sessao.post("/api/itens", json={
            "tipo": "estilo",
            "titulo": f"{PREFIXO_TESTE} estilo {_sufixo()}",
            "dados": {"esquema_versao": 1, "corpo": corpo},
        })
        assert r.status_code == 201, r.text
        self.estilo_id = r.json()["id"]
        # a ligação estilo -> camada é a relação `estilo_de_camada`, declarada pela API do catálogo
        r = self.sessao.put(f"/api/itens/{self.estilo_id}/relacoes", json={
            "relacoes": [{"destino": self.item_id, "tipo": "estilo_de_camada"}]})
        assert r.status_code == 200, r.text

    def apagar(self):
        for iid in (self.estilo_id, self.item_id):
            if iid:
                self.sessao.delete(f"/api/itens/{iid}")
        with self._con() as con, con.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{self.schema}"."{self.tabela}"')


@pytest.fixture
def camada_a(env, sessao_a):
    c = Camada(env, sessao_a, f"{PREFIXO_TESTE} camada A {_sufixo()}")
    yield c
    c.apagar()


@pytest.fixture
def camada_b(env, sessao_b):
    c = Camada(env, sessao_b, f"{PREFIXO_TESTE} camada B {_sufixo()}")
    yield c
    c.apagar()


@pytest.fixture
def token_leitura_a(sessao_a):
    r = sessao_a.post("/api/tokens", json={
        "nome": f"{PREFIXO_TESTE}-svc-{_sufixo()}", "escopos": ["catalogo:ler", "camada:ler"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    yield tok["token"]
    sessao_a.delete(f"/api/tokens/{tok['id']}")


@pytest.fixture
def anonimo():
    return novo_cliente()


def _json(resposta):
    assert resposta.status_code == 200, resposta.text
    return json.loads(resposta.text)


# ---------------------------------------------------------------- rest/info e conformidade de esquema
def test_rest_info_traz_authinfo_apontando_para_generate_token(anonimo, token_leitura_a):
    d = _json(anonimo.get(f"/svc/{token_leitura_a}/rest/info", params={"f": "json"}))
    assert CHAVES_INFO <= set(d)
    assert d["currentVersion"] == 11.4
    assert CHAVES_AUTHINFO <= set(d["authInfo"])
    assert d["authInfo"]["isTokenBasedSecurity"] is True
    assert d["authInfo"]["tokenServicesUrl"].endswith(f"/svc/{token_leitura_a}/rest/generateToken")


def test_catalogo_lista_a_camada_e_a_pasta(anonimo, token_leitura_a, camada_a):
    d = _json(anonimo.get(f"/svc/{token_leitura_a}/rest/services"))
    assert CHAVES_CATALOGO <= set(d)
    nomes = [s["name"] for s in d["services"]]
    assert camada_a.item_id in nomes
    assert all(s["type"] == "FeatureServer" for s in d["services"])


def test_descritor_do_servico_tem_as_chaves_obrigatorias(anonimo, token_leitura_a, camada_a):
    d = _json(anonimo.get(f"/svc/{token_leitura_a}/rest/services/{camada_a.item_id}/FeatureServer"))
    faltando = CHAVES_SERVICO - set(d)
    assert faltando == set(), faltando
    assert d["layers"][0]["id"] == 0 and d["layers"][0]["geometryType"] == "esriGeometryPolygon"
    assert d["spatialReference"] == {"wkid": 4326}
    assert d["fullExtent"]["xmin"] == pytest.approx(-47.1)
    assert d["tables"] == []


def test_descritor_da_camada_tem_campos_tipos_e_indices_do_banco(anonimo, token_leitura_a, camada_a):
    d = _json(anonimo.get(f"/svc/{token_leitura_a}/rest/services/{camada_a.item_id}/FeatureServer/0"))
    faltando = CHAVES_CAMADA - set(d)
    assert faltando == set(), faltando
    por_nome = {c["name"]: c for c in d["fields"]}
    assert CHAVES_CAMPO <= set(por_nome["nome"])
    assert por_nome["fid"]["type"] == "esriFieldTypeOID" and d["objectIdField"] == "fid"
    assert por_nome["globalid"]["type"] == "esriFieldTypeGlobalID" and d["globalIdField"] == "globalid"
    assert por_nome["populacao"]["type"] == "esriFieldTypeInteger"
    assert por_nome["medido_em"]["type"] == "esriFieldTypeDateOnly"   # tipo novo de 11.3
    assert por_nome["nome"]["length"] == 255 and por_nome["nome"]["domain"] is None
    assert "tenant_id" not in por_nome and "geom" not in por_nome     # controle interno nunca é atributo
    assert d["editFieldsInfo"]["creationDateField"] == "criado_em"
    indices = {i["fields"] for i in d["indexes"]}
    assert {"geom", "nome", "fid"} <= indices
    assert d["types"] == [] and d["typeIdField"] == "" and d["relationships"] == []


def test_layers_devolve_o_mesmo_descritor_da_camada(anonimo, token_leitura_a, camada_a):
    base = f"/svc/{token_leitura_a}/rest/services/{camada_a.item_id}/FeatureServer"
    lista = _json(anonimo.get(f"{base}/layers"))
    uma = _json(anonimo.get(f"{base}/0"))
    assert lista["tables"] == [] and lista["layers"][0]["name"] == uma["name"]
    assert lista["layers"][0]["fields"] == uma["fields"]


def test_item_info_e_metadata_vem_do_catalogo(anonimo, token_leitura_a, camada_a):
    base = f"/svc/{token_leitura_a}/rest/services/{camada_a.item_id}/FeatureServer"
    ficha = _json(anonimo.get(f"{base}/info/itemInfo"))
    assert ficha["title"].startswith(PREFIXO_TESTE) and "esri" in ficha["tags"]
    r = anonimo.get(f"{base}/info/metadata")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/xml")
    assert "MD_Metadata" in r.text and ficha["title"] in r.text


def test_camada_id_inexistente_e_404_nao_500(anonimo, token_leitura_a, camada_a):
    r = anonimo.get(f"/svc/{token_leitura_a}/rest/services/{camada_a.item_id}/FeatureServer/7")
    assert r.status_code == 404


# ---------------------------------------------------------------- f, callback e CORS
def test_pjson_e_html_e_jsonp_respondem_e_nunca_500(anonimo, token_leitura_a, camada_a):
    base = f"/svc/{token_leitura_a}/rest/services/{camada_a.item_id}/FeatureServer"
    assert anonimo.get(base, params={"f": "pjson"}).status_code == 200
    r = anonimo.get(base, params={"f": "html"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    r = anonimo.get(base, params={"callback": "cb"})
    assert r.status_code == 200 and r.text.startswith("cb(") and r.text.endswith(");")


def test_callback_com_script_e_recusado_sem_ecoar(anonimo, token_leitura_a, camada_a):
    base = f"/svc/{token_leitura_a}/rest/services/{camada_a.item_id}/FeatureServer"
    r = anonimo.get(base, params={"callback": "</script><script>alert(1)</script>"})
    assert r.status_code == 400 and "<script>" not in r.text


def test_formato_desconhecido_e_400(anonimo, token_leitura_a, camada_a):
    base = f"/svc/{token_leitura_a}/rest/services/{camada_a.item_id}/FeatureServer"
    assert anonimo.get(base, params={"f": "kmz"}).status_code == 400


def test_cors_aberto_em_svc_e_fechado_em_api(anonimo, token_leitura_a, camada_a):
    base = f"/svc/{token_leitura_a}/rest/services/{camada_a.item_id}/FeatureServer"
    r = anonimo.get(base, headers={"Origin": "https://outro.exemplo"})
    assert r.headers.get("access-control-allow-origin") == "*"
    assert "access-control-allow-credentials" not in {k.lower() for k in r.headers}
    pre = anonimo.options(base, headers={"Origin": "https://outro.exemplo",
                                         "Access-Control-Request-Method": "GET"})
    assert pre.status_code == 204 and pre.headers.get("access-control-allow-origin") == "*"
    api = anonimo.get("/api/versao", headers={"Origin": "https://outro.exemplo"})
    assert api.headers.get("access-control-allow-origin") is None


# ---------------------------------------------------------------- generateToken
def test_generate_token_devolve_token_de_leitura_com_validade_de_ate_24h(anonimo, token_leitura_a, cred):
    login, senha = cred["demo"]
    r = anonimo.post(f"/svc/{token_leitura_a}/rest/generateToken",
                     data={"username": login, "password": senha, "expiration": "100000", "f": "json"})
    d = _json(r)
    assert "error" not in d and d["token"].startswith("plat_")
    assert d["scopes"] == ["catalogo:ler", "camada:ler", "tiles:ler"]
    import time
    faltam = d["expires"] / 1000 - time.time()
    assert 0 < faltam <= 24 * 3600 + 60           # teto de 24 h aplicado apesar do pedido maior
    # o token gerado abre o diretório e NÃO abre a criação de token (escopo de leitura)
    assert anonimo.get(f"/svc/{d['token']}/rest/services").status_code == 200
    negado = anonimo.post("/api/tokens", json={"nome": "zt-nao", "escopos": ["catalogo:ler"]},
                          headers={"Authorization": f"Bearer {d['token']}"})
    assert negado.status_code in (401, 403)


def test_generate_token_com_senha_errada_nao_gera(anonimo, token_leitura_a, cred):
    login, _ = cred["demo"]
    d = _json(anonimo.post(f"/svc/{token_leitura_a}/rest/generateToken",
                           data={"username": login, "password": "errada-" + _sufixo()}))
    assert d["error"]["code"] == 400 and "token" not in d


def test_generate_token_sem_credencial_devolve_erro_do_protocolo(anonimo, token_leitura_a):
    d = _json(anonimo.post(f"/svc/{token_leitura_a}/rest/generateToken", data={}))
    assert d["error"]["code"] == 400


# ---------------------------------------------------------------- isolamento entre inquilinos
def test_camada_de_b_ausente_no_diretorio_de_a(anonimo, token_leitura_a, camada_a, camada_b):
    d = _json(anonimo.get(f"/svc/{token_leitura_a}/rest/services"))
    nomes = [s["name"] for s in d["services"]]
    assert camada_a.item_id in nomes
    assert camada_b.item_id not in nomes
    r = anonimo.get(f"/svc/{token_leitura_a}/rest/services/{camada_b.item_id}/FeatureServer")
    assert r.status_code == 404
    r = anonimo.get(f"/svc/{token_leitura_a}/rest/services/{camada_b.item_id}/FeatureServer/0")
    assert r.status_code == 404


def test_token_invalido_ou_revogado_nao_abre_o_diretorio(anonimo, sessao_a, camada_a):
    r = sessao_a.post("/api/tokens", json={
        "nome": f"{PREFIXO_TESTE}-svc-rev-{_sufixo()}", "escopos": ["catalogo:ler", "camada:ler"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    assert anonimo.get(f"/svc/{tok['token']}/rest/services").status_code == 200
    assert sessao_a.delete(f"/api/tokens/{tok['id']}").status_code in (200, 204)
    assert anonimo.get(f"/svc/{tok['token']}/rest/services").status_code == 401
    assert anonimo.get("/svc/plat_naoexiste/rest/services").status_code == 401


def test_token_sem_escopo_de_catalogo_nao_abre_o_diretorio(anonimo, sessao_a, camada_a):
    r = sessao_a.post("/api/tokens", json={
        "nome": f"{PREFIXO_TESTE}-svc-rota-{_sufixo()}", "escopos": ["rota:usar"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    try:
        assert anonimo.get(f"/svc/{tok['token']}/rest/services").status_code == 403
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


# ---------------------------------------------------------------- drawingInfo vindo do estilo
def test_estilo_da_camada_vira_renderer_unique_value(anonimo, token_leitura_a, camada_a):
    camada_a.dar_estilo({"type": "fill", "paint": {
        "fill-color": ["match", ["get", "nome"], "Alfa", "#0a0", "Beta", "#00a", "#cccccc"],
        "fill-opacity": 0.8}})
    d = _json(anonimo.get(f"/svc/{token_leitura_a}/rest/services/{camada_a.item_id}/FeatureServer/0"))
    r = d["drawingInfo"]["renderer"]
    assert r["type"] == "uniqueValue" and r["field1"] == "nome"
    assert [i["value"] for i in r["uniqueValueInfos"]] == ["Alfa", "Beta"]
    assert r["uniqueValueInfos"][0]["symbol"]["color"] == [0, 170, 0, 204]


def test_camada_sem_estilo_tem_renderer_simples_declarado(anonimo, token_leitura_a, camada_a):
    d = _json(anonimo.get(f"/svc/{token_leitura_a}/rest/services/{camada_a.item_id}/FeatureServer/0"))
    assert d["drawingInfo"]["renderer"]["type"] == "simple"
    assert d["drawingInfo"]["_conversao"] == "sem cor no estilo"
