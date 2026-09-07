"""Item `L5-31-construtor-de-camada-esquema` (linha L5 builder). Portão de pronto:
- camada criada por arrasto de campos aparece no PostgreSQL com os tipos certos (compara information_schema)
  e no formato `fields` de FeatureServer;
- migração destrutiva (texto→inteiro com dado) é recusada com mensagem;
- alias e domínio refletem no formulário (GET /campos) sem reconfigurar a camada.
Refutação: 300 campos, um deles nome reservado do PostgreSQL e outro com acento/símbolo — tem de normalizar
sem quebrar nada, nunca 500."""

from __future__ import annotations

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug


class FabricaCamada:
    """Cria camadas via a API e apaga (lixeira + expurgo físico, que dropa a tabela) no fim do teste."""

    def __init__(self, sessao, env):
        self.sessao = sessao
        self.env = env
        self.itens: list[str] = []

    def criar(self, **kw) -> dict:
        corpo = {"titulo": f"{PREFIXO_TESTE} camada esquema", "geometria": "Point", "srid": 4674, "campos": []}
        corpo.update(kw)
        r = self.sessao.post("/api/camadas/esquema", json=corpo)
        if r.status_code == 201:
            self.itens.append(r.json()["item_id"])
        return r

    def limpar(self) -> None:
        if not self.itens:
            return
        from app.catalogo import destruidores

        con = psycopg2.connect(self.env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
        try:
            ids = ids_por_slug(con)
            with con.cursor() as cur:
                cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
                adm = cur.fetchone()["usuario_id"]
            contexto(con, ids["demo"], usuario_id=adm, login="admin")
            with con.cursor() as cur:
                cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
                for iid in self.itens:
                    cur.execute("SELECT tipo, dados, miniatura_chave FROM plat.item WHERE id = %s::uuid", (iid,))
                    item = cur.fetchone()
                    cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (iid,))
                    if item is not None:
                        try:
                            destruidores.destruir(cur, item["tipo"], item["dados"], item["miniatura_chave"],
                                                  lambda *_a: None)
                        except destruidores.Recusado:
                            pass
                    cur.execute("SELECT plat.item_expurgar(%s::uuid)", (iid,))
            con.commit()
        finally:
            con.close()


@pytest.fixture
def camada_a(sessao_a, env):
    f = FabricaCamada(sessao_a, env)
    yield f
    f.limpar()


def _admin_ctx(con, env):
    ids = ids_por_slug(con)
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(con, ids["demo"], usuario_id=adm, login="admin")


def _tabela_de(item_id: str, env) -> tuple[str, str]:
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        _admin_ctx(con, env)
        with con.cursor() as cur:
            cur.execute("SELECT dados->>'schema' AS schema, dados->>'tabela' AS tabela FROM plat.item "
                        "WHERE id=%s::uuid", (item_id,))
            r = cur.fetchone()
            return r["schema"], r["tabela"]
    finally:
        con.close()


def _inserir_linha(env, schema: str, tabela: str, colunas: dict) -> None:
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        _admin_ctx(con, env)
        with con.cursor() as cur:
            campos = ", ".join(f'"{c}"' for c in colunas)
            marcas = ", ".join(["%s"] * len(colunas))
            cur.execute(f'INSERT INTO "{schema}"."{tabela}" ({campos}, geom) VALUES ({marcas}, '
                        f"ST_SetSRID(ST_MakePoint(-47, -15), 4674))", list(colunas.values()))
        con.commit()
    finally:
        con.close()


def test_camada_criada_por_esquema_aparece_no_postgres_com_tipos_certos(camada_a, env, medida):
    r = camada_a.criar(campos=[
        {"nome": "Nome do Talhão", "tipo": "text", "tamanho": 80, "alias": "Nome do talhão", "obrigatorio": True},
        {"nome": "área_ha", "tipo": "double precision"},
        {"nome": "plantado_em", "tipo": "date"},
        {"nome": "ativo", "tipo": "boolean", "padrao": "true"},
        {"nome": "safra", "tipo": "integer", "dominio": [{"codigo": 1, "rotulo": "2025/26"},
                                                          {"codigo": 2, "rotulo": "2026/27"}]},
    ])
    assert r.status_code == 201, r.text
    corpo = r.json()
    item_id = corpo["item_id"]
    assert corpo["campos"] == 5

    schema, tabela = corpo["schema"], corpo["tabela"]
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        _admin_ctx(con, env)
        with con.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type, is_nullable, character_maximum_length "
                "FROM information_schema.columns WHERE table_schema=%s AND table_name=%s", (schema, tabela),
            )
            colunas = {r2["column_name"]: r2 for r2 in cur.fetchall()}
            cur.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s", (tabela,))
            rls = cur.fetchone()
    finally:
        con.close()

    assert colunas["nome_do_talhao"]["data_type"] == "character varying"
    assert colunas["nome_do_talhao"]["character_maximum_length"] == 80
    assert colunas["nome_do_talhao"]["is_nullable"] == "NO"  # obrigatorio
    assert colunas["area_ha"]["data_type"] == "double precision"  # acento caiu
    assert colunas["plantado_em"]["data_type"] == "date"
    assert colunas["ativo"]["data_type"] == "boolean"
    assert colunas["safra"]["data_type"] == "integer"
    assert colunas["geom"] is not None  # coluna de geometria criada
    # colunas obrigatórias de toda camada (plat.camada_preparar, L0-04) também nasceram aqui
    for obrigatoria in ("globalid", "versao", "tenant_id", "criado_em", "atualizado_em"):
        assert obrigatoria in colunas
    assert rls["relrowsecurity"] and rls["relforcerowsecurity"], "FORCE ROW LEVEL SECURITY ausente"

    r2 = camada_a.sessao.get(f"/api/camadas/{item_id}/campos")
    assert r2.status_code == 200, r2.text
    fields = {f["name"]: f for f in r2.json()["fields"]}
    assert fields["nome_do_talhao"]["alias"] == "Nome do talhão"
    assert fields["nome_do_talhao"]["type"] == "esriFieldTypeString"
    assert fields["nome_do_talhao"]["length"] == 80
    assert fields["nome_do_talhao"]["nullable"] is False
    assert fields["safra"]["domain"]["type"] == "codedValue"
    assert fields["safra"]["domain"]["codedValues"] == [{"codigo": 1, "rotulo": "2025/26"},
                                                          {"codigo": 2, "rotulo": "2026/27"}]
    # colunas de sistema nunca aparecem no fields (é o que a tela do formulário usa)
    assert "tenant_id" not in fields and "geom" not in fields and "fid" not in fields
    medida("L5-31-construtor-de-camada-esquema")("campos_criados_e_lidos", len(fields), "campos",
                                                  "GET /api/camadas/{id}/campos")


def test_migracao_destrutiva_texto_para_inteiro_com_dado_e_recusada(camada_a, env):
    r = camada_a.criar(campos=[{"nome": "codigo", "tipo": "text"}])
    assert r.status_code == 201, r.text
    item_id = r.json()["item_id"]
    schema, tabela = r.json()["schema"], r.json()["tabela"]
    _inserir_linha(env, schema, tabela, {"codigo": "AB-12"})  # não é número: a conversão perderia o dado

    corpo = {"mudancas": [{"tipo": "mudar_tipo", "campo": "codigo", "novo_tipo": "integer"}]}
    rp = camada_a.sessao.post(f"/api/camadas/{item_id}/esquema/plano", json=corpo)
    assert rp.status_code == 200, rp.text
    plano = rp.json()["plano"][0]
    assert plano["aplicavel"] is False
    assert "recusad" in plano["motivo"]

    ra = camada_a.sessao.put(f"/api/camadas/{item_id}/esquema", json=corpo)
    assert ra.status_code == 200, ra.text
    assert ra.json()["aplicadas"] == []
    assert len(ra.json()["recusadas"]) == 1

    # a coluna continua texto no banco (nada foi aplicado calado)
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        _admin_ctx(con, env)
        with con.cursor() as cur:
            cur.execute("SELECT data_type FROM information_schema.columns "
                        "WHERE table_schema=%s AND table_name=%s AND column_name='codigo'", (schema, tabela))
            assert cur.fetchone()["data_type"] == "text"
    finally:
        con.close()


def test_migracao_destrutiva_em_tabela_vazia_e_aceita(camada_a):
    """A MESMA mudança (texto->inteiro) sem dado nenhum não perde nada: aplica."""
    r = camada_a.criar(campos=[{"nome": "codigo", "tipo": "text"}])
    item_id = r.json()["item_id"]
    corpo = {"mudancas": [{"tipo": "mudar_tipo", "campo": "codigo", "novo_tipo": "integer"}]}
    ra = camada_a.sessao.put(f"/api/camadas/{item_id}/esquema", json=corpo)
    assert ra.status_code == 200, ra.text
    assert len(ra.json()["aplicadas"]) == 1
    assert ra.json()["recusadas"] == []


def test_alargar_tamanho_de_texto_aplica_sem_ressalva(camada_a):
    r = camada_a.criar(campos=[{"nome": "nome", "tipo": "text", "tamanho": 10}])
    item_id = r.json()["item_id"]
    corpo = {"mudancas": [{"tipo": "mudar_tamanho", "campo": "nome", "novo_tamanho": 200}]}
    ra = camada_a.sessao.put(f"/api/camadas/{item_id}/esquema", json=corpo)
    assert ra.status_code == 200, ra.text
    assert len(ra.json()["aplicadas"]) == 1


def test_alias_e_dominio_refletem_no_formulario_sem_reconfigurar(camada_a):
    """Renomear o alias (metadado puro, plat.camada_campo_meta) aparece no GET /campos na hora, sem recriar
    a camada nem reenviar o esquema inteiro — é a cláusula 'sem reconfigurar' do portão."""
    r = camada_a.criar(campos=[{"nome": "responsavel", "tipo": "text", "alias": "Responsável"}])
    item_id = r.json()["item_id"]

    antes = camada_a.sessao.get(f"/api/camadas/{item_id}/campos").json()["fields"]
    assert {f["name"]: f["alias"] for f in antes}["responsavel"] == "Responsável"

    corpo = {"mudancas": [{"tipo": "renomear_alias", "campo": "responsavel", "novo_alias": "Técnico responsável"}]}
    ra = camada_a.sessao.put(f"/api/camadas/{item_id}/esquema", json=corpo)
    assert ra.status_code == 200, ra.text
    assert len(ra.json()["aplicadas"]) == 1

    depois = camada_a.sessao.get(f"/api/camadas/{item_id}/campos").json()["fields"]
    assert {f["name"]: f["alias"] for f in depois}["responsavel"] == "Técnico responsável"


def test_adicionar_campo_com_dominio_por_plano_de_migracao(camada_a):
    r = camada_a.criar(campos=[{"nome": "id_talhao", "tipo": "text"}])
    item_id = r.json()["item_id"]
    corpo = {"mudancas": [{
        "tipo": "adicionar_campo",
        "novo_campo": {"nome": "status", "tipo": "text", "dominio": [{"codigo": "ok", "rotulo": "Regular"},
                                                                       {"codigo": "pendente", "rotulo": "Pendente"}]},
    }]}
    rp = camada_a.sessao.post(f"/api/camadas/{item_id}/esquema/plano", json=corpo)
    assert rp.status_code == 200 and rp.json()["plano"][0]["aplicavel"] is True, rp.text

    ra = camada_a.sessao.put(f"/api/camadas/{item_id}/esquema", json=corpo)
    assert ra.status_code == 200 and len(ra.json()["aplicadas"]) == 1, ra.text

    fields = {f["name"]: f for f in camada_a.sessao.get(f"/api/camadas/{item_id}/campos").json()["fields"]}
    assert "status" in fields
    assert fields["status"]["domain"]["codedValues"][0]["codigo"] == "ok"


def test_adversario_300_campos_com_reservada_e_acento_normaliza_sem_quebrar(camada_a, medida):
    """Refutação do item: 300 campos, um com nome de palavra reservada do PostgreSQL ('select'), outro com
    acento inicial/símbolo e maiúsculas ('Área (m²) - Útil'), e duplicatas propositais ('Campo' repetido 5x).
    Tem de normalizar tudo (nunca 500) e o FeatureServer (`GET /campos`) tem de continuar respondendo certo
    para as 300 colunas."""
    campos = [{"nome": "select", "tipo": "text"}, {"nome": "Área (m²) - Útil", "tipo": "double precision"}]
    campos += [{"nome": "Campo", "tipo": "text"} for _ in range(5)]  # dedup: campo, campo_2 .. campo_5, e a
    #                                                                   primeira 'Campo' vira "campo"
    campos += [{"nome": f"c{i}", "tipo": "integer"} for i in range(len(campos), 300)]
    assert len(campos) == 300

    r = camada_a.criar(campos=campos)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["campos"] == 300
    avisos = {a["campo"]: a["motivo"] for a in corpo["avisos"]}
    assert avisos.get("select_") == "reservado"
    assert avisos.get("campo_2") == "duplicado" and avisos.get("campo_5") == "duplicado"

    fields = camada_a.sessao.get(f"/api/camadas/{corpo['item_id']}/campos")
    assert fields.status_code == 200, fields.text
    nomes = [f["name"] for f in fields.json()["fields"]]
    assert len(nomes) == 300
    assert len(set(nomes)) == 300  # nenhuma colisão de nome sobrou
    assert "select_" in nomes  # a palavra reservada ganhou sufixo, nunca foi rejeitada nem quebrou a DDL
    assert "area_m2_util" in nomes  # acento/símbolo/maiúscula normalizados sem perder o campo
    medida("L5-31-construtor-de-camada-esquema")("adversario_300_campos_ok", 1, "bool",
                                                  "POST /api/camadas/esquema com 300 campos hostis")


def test_geometria_invalida_e_tipo_invalido_recusam_com_422(camada_a):
    r = camada_a.criar(geometria="Circulo")
    assert r.status_code == 422, r.text
    r2 = camada_a.criar(campos=[{"nome": "x", "tipo": "jsonb"}])
    assert r2.status_code == 422, r2.text


def test_item_de_outro_tipo_nao_serve_campos(sessao_a):
    r = sessao_a.post("/api/itens", json={
        "tipo": "mapa", "titulo": f"{PREFIXO_TESTE} mapa qualquer",
        "dados": {"esquema_versao": 1, "corpo": {}},
    })
    assert r.status_code == 201, r.text
    item_id = r.json()["id"]
    try:
        rc = sessao_a.get(f"/api/camadas/{item_id}/campos")
        assert rc.status_code == 422 and rc.json()["erro"] == "tipo_incompativel"
    finally:
        sessao_a.delete(f"/api/itens/{item_id}")
