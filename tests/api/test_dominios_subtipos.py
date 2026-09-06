"""Domínios de atributo e subtipos por camada (item L2-10-a-dominios-subtipos).

Cada teste aqui é uma cláusula do portão de pronto do item; as medidas (custo do gatilho, contagens) vão
para tests/medidas/L2-10-a-dominios-subtipos.json pelo fixture `medida`.

A camada de teste é uma tabela PostGIS de verdade em `d_demo`, criada como `plat_app` e preparada pela mesma
`plat.camada_preparar` da ingestão (029) — não é tabela de mentira nem mock: o gatilho que se testa é o que
roda em produção, e o INSERT "direto na tabela" do portão é um INSERT como `plat_app`, sem passar pela API.
"""

from __future__ import annotations

import json
import re
import secrets
import time

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import entrar, novo_cliente
from tests.api.test_rls import contexto

ITEM = "L2-10-a-dominios-subtipos"


# ------------------------------------------------------------------ apoio
class Inquilino:
    """Inquilino de teste com slug SEM hífen.

    Por que não o `inquilino_temporario` do conftest: o slug dele é `zt-inq-<hex>` e o schema de dado do
    inquilino vira `d_zt-inq-<hex>`, que NÃO passa na expressão de `plat.camada_preparar`
    (`^d_[a-z0-9_]{1,62}$`, migração 029). O slug aceito pela API admite hífen e a função de camada não —
    divergência real do repositório, anotada no handoff do item; aqui se contorna com um slug só de letras
    e dígitos. E por que não o inquilino `demo`: o schema `d_demo` é de produção e pertence ao `plat_app`
    de produção, então a role da trilha não cria tabela lá.
    """

    def __init__(self, sessao_plat):
        self.slug = "zt" + secrets.token_hex(4)
        r = sessao_plat.post("/api/plataforma/inquilinos", json={
            "slug": self.slug, "nome": f"Inquilino de teste {self.slug}",
            "admin_login": "admin", "admin_nome": "Administrador de teste"})
        assert r.status_code == 201, r.text
        self.id = r.json()["id"]
        self.admin_id = r.json()["admin"]["id"]
        temporaria = r.json()["senha_temporaria"]
        self.admin = novo_cliente()
        assert entrar(self.admin, self.slug, "admin", temporaria).status_code == 200
        self.senha = "Senha-do-admin-1" + secrets.token_hex(3)
        assert self.admin.put("/api/eu/senha", json={"atual": temporaria, "nova": self.senha}).status_code == 204
        self._plat = sessao_plat

    def apagar(self):
        self._plat.delete(f"/api/plataforma/inquilinos/{self.id}")


class Camada:
    """Uma camada vetorial de teste: tabela física + item de catálogo, com os campos declarados."""

    def __init__(self, con, inq: "Inquilino", campos: list[dict]):
        self.con = con
        self.inq = inq
        self.sessao = inq.admin
        self.tabela = "c_" + secrets.token_hex(8)
        self.esquema = "d_" + inq.slug
        self.campos = campos
        contexto(con, inq.id, usuario_id=inq.admin_id, login="admin")
        colunas = ", ".join(f'{c["nome"]} {c["tipo"]}' for c in campos)
        with con.cursor() as cur:
            cur.execute("SELECT plat.camada_schema_garantir(%s)", (inq.slug,))
            cur.execute(
                f"CREATE TABLE {self.esquema}.{self.tabela} "
                f"(fid serial PRIMARY KEY, geom geometry(Point, 4326), {colunas})"
            )
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                        (self.esquema, self.tabela, 4326, "Point", inq.admin_id))
        con.commit()
        r = self.sessao.post("/api/itens", json={
            "tipo": "camada_vetorial",
            "titulo": f"zt camada dominios {self.tabela}",
            "dados": {"schema": self.esquema, "tabela": self.tabela, "geometria": "Point", "srid": 4326,
                      "campos": campos, "fonte": "hospedada"},
        })
        assert r.status_code == 201, r.text
        self.item_id = r.json()["id"]

    def contexto(self):
        """set_config(..., true) é LOCAL à transação: todo commit apaga o contexto, e sem contexto a RLS da
        tabela de camada recusa a linha. Por isso o contexto é reposto no início de cada operação."""
        contexto(self.con, self.inq.id, usuario_id=self.inq.admin_id, login="admin")

    def inserir(self, **valores):
        """INSERT direto na tabela como plat_app (o caminho que o portão exige provar)."""
        self.contexto()
        colunas = ", ".join(valores)
        marcas = ", ".join(["%s"] * len(valores))
        with self.con.cursor() as cur:
            cur.execute(
                f"INSERT INTO {self.esquema}.{self.tabela} (geom, {colunas}) "
                f"VALUES (ST_SetSRID(ST_MakePoint(-46.5, -23.5), 4326), {marcas}) RETURNING fid",
                list(valores.values()),
            )
            return cur.fetchone()["fid"]

    def atualizar(self, fid: int, **valores):
        self.contexto()
        atribui = ", ".join(f"{k} = %s" for k in valores)
        with self.con.cursor() as cur:
            cur.execute(f"UPDATE {self.esquema}.{self.tabela} SET {atribui} WHERE fid = %s",
                        [*valores.values(), fid])

    def apagar(self):
        self.con.rollback()
        self.contexto()
        with self.con.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {self.esquema}.{self.tabela} CASCADE")
        self.con.commit()
        self.sessao.delete(f"/api/itens/{self.item_id}")


@pytest.fixture
def con(env):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    yield con
    con.rollback()
    con.close()


@pytest.fixture
def inquilino(sessao_plat):
    inq = Inquilino(sessao_plat)
    yield inq
    inq.apagar()


@pytest.fixture
def sessao(inquilino):
    """O admin do inquilino de teste recém-criado (não é o `sessao` do conftest, que é o admin do `demo`
    e tem escopo de sessão inteira)."""
    return inquilino.admin


@pytest.fixture
def camada(con, inquilino):
    c = Camada(con, inquilino, [
        {"nome": "uf", "tipo": "text"}, {"nome": "situacao", "tipo": "text"},
        {"nome": "altura", "tipo": "double precision"}, {"nome": "classe", "tipo": "integer"},
    ])
    yield c
    c.apagar()


@pytest.fixture
def dominios(sessao):
    """Fábrica de domínios com limpeza no fim (desliga o que estiver ligado antes de apagar)."""
    criados = []

    def criar(**corpo):
        corpo.setdefault("nome", "zt dominio " + secrets.token_hex(4))
        r = sessao.post("/api/dominios", json=corpo)
        assert r.status_code == 201, r.text
        criados.append(r.json()["id"])
        return r.json()

    yield criar
    for did in reversed(criados):
        u = sessao.get(f"/api/dominios/{did}/uso")
        if u.status_code == 200:
            for c in u.json()["camadas"]:
                sessao.delete(f"/api/camadas/{c['item_id']}/dominios/{c['ligacao_id']}")
        sessao.delete(f"/api/dominios/{did}")


COMANDO = ("set -a; source /home/dev/plataforma/laco/var/trilha/t210a.env; set +a; "
           "PLAT_GRAVAR_MEDIDAS=1 venv/bin/pytest tests/api/test_dominios_subtipos.py -q")


@pytest.fixture
def anotar(medida):
    """medida() do conftest raiz, já amarrada a este item e ao comando que a gerou."""
    gravar = medida(ITEM)

    def registrar(nome: str, valor, unidade: str = "") -> None:
        gravar(nome, valor, unidade, COMANDO)

    return registrar


def codificado(n=5):
    return [{"codigo": f"C{i}", "descricao": f"Descrição {i}", "ordem": i} for i in range(n)]


# ------------------------------------------------------------------ cláusula 1: codificado, 5 valores, gatilho
def test_dominio_codificado_5_valores_recusa_codigo_invalido_na_tabela(camada, dominios, sessao, anotar):
    d = dominios(tipo="codificado", tipo_campo="text",
                 valores=[{"codigo": "SP", "descricao": "São Paulo"}, {"codigo": "RJ", "descricao": "Rio de Janeiro"},
                          {"codigo": "MG", "descricao": "Minas Gerais"}, {"codigo": "BA", "descricao": "Bahia"},
                          {"codigo": "RS", "descricao": "Rio Grande do Sul"}])
    assert len(d["valores"]) == 5
    r = sessao.post(f"/api/camadas/{camada.item_id}/dominios", json={"campo": "uf", "dominio_id": d["id"]})
    assert r.status_code == 201, r.text

    fid = camada.inserir(uf="SP")           # código válido entra
    assert fid > 0
    with pytest.raises(psycopg2.errors.RaiseException) as e:
        camada.inserir(uf="ZZ")             # inválido, direto na tabela como plat_app
    diag = e.value.diag
    assert diag.message_primary == "valor_fora_do_dominio"
    assert diag.column_name == "uf", diag.column_name
    assert 'campo "uf"' in diag.message_detail and "'ZZ'" in diag.message_detail
    camada.con.rollback()
    anotar("codificado_mensagem_do_gatilho", diag.message_detail)
    anotar("codificado_coluna_no_erro", diag.column_name)



def test_dominio_intervalo_recusa_fora_do_minimo_e_do_maximo(camada, dominios, sessao, anotar):
    d = dominios(tipo="intervalo", tipo_campo="double precision", valores={"min": 0, "max": 10})
    r = sessao.post(f"/api/camadas/{camada.item_id}/dominios", json={"campo": "altura", "dominio_id": d["id"]})
    assert r.status_code == 201, r.text
    assert camada.inserir(altura=5.5) > 0
    for fora in (-0.1, 10.1):
        with pytest.raises(psycopg2.errors.RaiseException) as e:
            camada.inserir(altura=fora)
        assert e.value.diag.message_primary == "valor_fora_do_dominio"
        assert e.value.diag.column_name == "altura"
        assert "intervalo 0.0 a 10.0" in e.value.diag.message_detail
        camada.con.rollback()
    anotar("intervalo_recusa_abaixo_e_acima", True)



def test_subtipo_troca_o_dominio_do_mesmo_campo(camada, dominios, sessao, anotar):
    """Dois subtipos, o MESMO campo `situacao`, domínios diferentes: o que vale depende do valor de `classe`."""
    padrao = dominios(tipo="codificado", tipo_campo="text",
                      valores=[{"codigo": "generico", "descricao": "Genérico"}])
    urbano = dominios(tipo="codificado", tipo_campo="text",
                      valores=[{"codigo": "asfalto", "descricao": "Asfalto"},
                               {"codigo": "paralelo", "descricao": "Paralelepípedo"}])
    rural = dominios(tipo="codificado", tipo_campo="text",
                     valores=[{"codigo": "terra", "descricao": "Terra"},
                              {"codigo": "cascalho", "descricao": "Cascalho"}])
    r = sessao.put(f"/api/camadas/{camada.item_id}/subtipos", json={
        "campo": "classe",
        "valores": [{"codigo": 1, "nome": "Urbano", "padroes": {"situacao": "asfalto"}},
                    {"codigo": 2, "nome": "Rural", "padroes": {"situacao": "terra"}}],
    })
    assert r.status_code == 200, r.text
    for corpo in ({"campo": "situacao", "dominio_id": padrao["id"]},
                  {"campo": "situacao", "dominio_id": urbano["id"], "subtipo_codigo": 1},
                  {"campo": "situacao", "dominio_id": rural["id"], "subtipo_codigo": 2}):
        assert sessao.post(f"/api/camadas/{camada.item_id}/dominios", json=corpo).status_code == 201

    assert camada.inserir(classe=1, situacao="asfalto") > 0
    assert camada.inserir(classe=2, situacao="terra") > 0
    with pytest.raises(psycopg2.errors.RaiseException) as e:   # válido no subtipo 2, não no 1
        camada.inserir(classe=1, situacao="terra")
    assert "asfalto" not in e.value.diag.message_detail
    assert e.value.diag.column_name == "situacao"
    camada.con.rollback()
    with pytest.raises(psycopg2.errors.RaiseException):        # válido no subtipo 1, não no 2
        camada.inserir(classe=2, situacao="asfalto")
    camada.con.rollback()
    assert camada.inserir(classe=None, situacao="generico") > 0  # sem subtipo vale o domínio da camada
    with pytest.raises(psycopg2.errors.RaiseException):
        camada.inserir(classe=9, situacao="generico")            # subtipo fora da lista
    camada.con.rollback()
    anotar("subtipos_no_mesmo_campo", 2)
    anotar("dominios_distintos_ligados_ao_campo_situacao", 3)



def test_remover_valor_em_uso_devolve_409_com_a_contagem(camada, dominios, sessao, anotar):
    d = dominios(tipo="codificado", tipo_campo="text", valores=codificado(3))
    assert sessao.post(f"/api/camadas/{camada.item_id}/dominios",
                         json={"campo": "uf", "dominio_id": d["id"]}).status_code == 201
    for _ in range(4):
        camada.inserir(uf="C1")
    camada.con.commit()
    corpo = {"nome": d["nome"], "tipo": "codificado", "tipo_campo": "text",
             "valores": [v for v in codificado(3) if v["codigo"] != "C1"]}
    r = sessao.put(f"/api/dominios/{d['id']}", json=corpo)
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "valor_em_uso"
    assert r.json()["detalhe"] == {"codigo": "C1", "usos": 4}
    uso = sessao.get(f"/api/dominios/{d['id']}/uso").json()
    assert {v["codigo"]: v["usos"] for v in uso["valores"]}["C1"] == 4
    assert uso["camadas"][0]["item_id"] == camada.item_id and uso["camadas"][0]["campo"] == "uf"
    # valor NÃO usado sai sem drama
    corpo["valores"] = [v for v in codificado(3) if v["codigo"] != "C2"]
    assert sessao.put(f"/api/dominios/{d['id']}", json=corpo).status_code == 200
    anotar("remocao_de_valor_em_uso_status", 409)
    anotar("remocao_de_valor_em_uso_contagem", 4, "feições")



def test_featureserver_mostra_domains_e_types_iguais_ao_banco(camada, dominios, sessao, anotar):
    uf = dominios(tipo="codificado", tipo_campo="text",
                  valores=[{"codigo": "SP", "descricao": "São Paulo"}, {"codigo": "RJ", "descricao": "Rio"}])
    alt = dominios(tipo="intervalo", tipo_campo="double precision", valores={"min": -5, "max": 900})
    urbano = dominios(tipo="codificado", tipo_campo="text",
                      valores=[{"codigo": "asfalto", "descricao": "Asfalto"}])
    sessao.post(f"/api/camadas/{camada.item_id}/dominios", json={"campo": "uf", "dominio_id": uf["id"]})
    sessao.post(f"/api/camadas/{camada.item_id}/dominios", json={"campo": "altura", "dominio_id": alt["id"]})
    sessao.put(f"/api/camadas/{camada.item_id}/subtipos", json={
        "campo": "classe", "valores": [{"codigo": 1, "nome": "Urbano", "padroes": {"situacao": "asfalto"}}]})
    sessao.post(f"/api/camadas/{camada.item_id}/dominios",
                  json={"campo": "situacao", "dominio_id": urbano["id"], "subtipo_codigo": 1})

    r = sessao.get(f"/rest/services/{camada.item_id}/FeatureServer/0")
    assert r.status_code == 200, r.text
    fs = r.json()
    campos = {c["name"]: c for c in fs["fields"]}
    assert campos["uf"]["domain"]["type"] == "codedValue"
    assert campos["uf"]["domain"]["name"] == uf["nome"]
    assert campos["uf"]["domain"]["codedValues"] == [{"name": "São Paulo", "code": "SP"},
                                                     {"name": "Rio", "code": "RJ"}]
    assert campos["altura"]["domain"] == {
        "type": "range", "name": alt["nome"], "description": "", "range": [-5.0, 900.0],
        "mergePolicy": "esriMPTDefaultValue", "splitPolicy": "esriSPTDuplicate"}
    assert campos["situacao"]["domain"] is None      # domínio de situação só existe dentro do subtipo
    assert campos["classe"]["type"] == "esriFieldTypeInteger"
    assert fs["typeIdField"] == "classe"
    assert [t["id"] for t in fs["types"]] == [1]
    assert fs["types"][0]["domains"]["situacao"]["codedValues"] == [{"name": "Asfalto", "code": "asfalto"}]
    assert fs["types"][0]["templates"][0]["prototype"]["attributes"] == {"situacao": "asfalto", "classe": 1}

    # "iguais ao banco": o mesmo conteúdo lido de plat.dominio, não uma segunda fonte
    lig = sessao.get(f"/api/camadas/{camada.item_id}/dominios").json()
    do_banco = {li["campo"]: li for li in lig["ligacoes"] if li["subtipo_codigo"] is None}
    codigos_do_banco = [v["codigo"] for v in do_banco["uf"]["valores"]]
    assert codigos_do_banco == [c["code"] for c in campos["uf"]["domain"]["codedValues"]]
    assert do_banco["altura"]["valores"] == {"min": -5, "max": 900}
    assert sessao.get(f"/rest/services/{camada.item_id}/FeatureServer/1").status_code == 404
    anotar("featureserver_campos_com_domain", sum(1 for c in fs["fields"] if c["domain"]))
    anotar("featureserver_types", len(fs["types"]))



def test_custo_do_gatilho_em_10_mil_insercoes(con, inquilino, sessao, dominios, anotar):
    """10 mil inserções com e sem gatilho, na MESMA tabela e na mesma sessão, alternando a ordem para o
    cache de página não favorecer a primeira rodada. O portão pede <= 1,5x."""
    camada = Camada(con, inquilino, [{"nome": "uf", "tipo": "text"}, {"nome": "altura", "tipo": "double precision"}])
    try:
        d = dominios(tipo="codificado", tipo_campo="text", valores=codificado(50))
        di = dominios(tipo="intervalo", tipo_campo="double precision", valores={"min": 0, "max": 1000})
        assert sessao.post(f"/api/camadas/{camada.item_id}/dominios",
                             json={"campo": "uf", "dominio_id": d["id"]}).status_code == 201
        assert sessao.post(f"/api/camadas/{camada.item_id}/dominios",
                             json={"campo": "altura", "dominio_id": di["id"]}).status_code == 201

        def rodada(n=10000):
            camada.contexto()
            t0 = time.perf_counter()
            with con.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO {camada.esquema}.{camada.tabela} (geom, uf, altura) "
                    f"VALUES (ST_SetSRID(ST_MakePoint(-46.5, -23.5), 4326), %s, %s)",
                    [(f"C{i % 50}", float(i % 1000)) for i in range(n)],
                )
            con.commit()
            return time.perf_counter() - t0

        def limpar():
            camada.contexto()
            with con.cursor() as cur:
                cur.execute(f"TRUNCATE {camada.esquema}.{camada.tabela}")
            con.commit()

        def gatilho(ligado: bool):
            camada.contexto()
            with con.cursor() as cur:
                cur.execute(
                    f"ALTER TABLE {camada.esquema}.{camada.tabela} "
                    f"{'ENABLE' if ligado else 'DISABLE'} TRIGGER tg_dominio"
                )
            con.commit()

        com, sem = [], []
        for volta in range(2):
            for ligado in ((True, False) if volta == 0 else (False, True)):
                gatilho(ligado)
                limpar()
                (com if ligado else sem).append(rodada())
        gatilho(True)
        limpar()
        t_com, t_sem = min(com), min(sem)
        razao = t_com / t_sem
        anotar("insercoes_medidas", 10000, "linhas")
        anotar("segundos_sem_gatilho", round(t_sem, 3), "s")
        anotar("segundos_com_gatilho", round(t_com, 3), "s")
        anotar("razao_com_sobre_sem", round(razao, 3), "x")
        anotar("teto_do_portao", 1.5, "x")

        assert razao <= 1.5, f"gatilho custou {razao:.2f}x (com {t_com:.2f}s, sem {t_sem:.2f}s)"
    finally:
        camada.apagar()


# ------------------------------------------------------------------ refutação exigida no item
def test_dominio_de_outro_inquilino_da_404(camada, sessao_b, sessao):
    """O adversário liga domínio do inquilino B a campo de camada do inquilino A: 404 nos dois sentidos."""
    r = sessao_b.post("/api/dominios", json={"nome": "zt dominio B " + secrets.token_hex(3),
                                             "tipo": "codificado", "tipo_campo": "text",
                                             "valores": codificado(2)})
    assert r.status_code == 201, r.text
    do_b = r.json()["id"]
    try:
        r = sessao.post(f"/api/camadas/{camada.item_id}/dominios", json={"campo": "uf", "dominio_id": do_b})
        assert r.status_code == 404 and r.json()["erro"] == "dominio_inexistente", r.text
        # e a camada de A vista de B também some
        assert sessao_b.get(f"/api/camadas/{camada.item_id}/dominios").status_code == 404
        assert sessao_b.get(f"/rest/services/{camada.item_id}/FeatureServer/0").status_code == 404
    finally:
        sessao_b.delete(f"/api/dominios/{do_b}")


def test_dominio_com_50_mil_codigos_recusado(sessao):
    r = sessao.post("/api/dominios", json={
        "nome": "zt dominio gigante " + secrets.token_hex(3), "tipo": "codificado", "tipo_campo": "text",
        "valores": [{"codigo": str(i), "descricao": str(i)} for i in range(50000)]})
    assert r.status_code == 422, r.status_code
    assert "2000" in json.dumps(r.json(), ensure_ascii=False)


def test_codigo_duplicado_recusado_na_api_e_no_banco(inquilino, sessao, con, env):
    corpo = {"nome": "zt dominio dup " + secrets.token_hex(3), "tipo": "codificado", "tipo_campo": "text",
             "valores": [{"codigo": "A", "descricao": "um"}, {"codigo": "A", "descricao": "outro"}]}
    r = sessao.post("/api/dominios", json=corpo)
    assert r.status_code == 422, r.text
    # e por fora da API, escrevendo direto como plat_app
    contexto(con, inquilino.id, usuario_id=inquilino.admin_id, login="admin")
    with pytest.raises(psycopg2.errors.RaiseException) as e:
        with con.cursor() as cur:
            cur.execute(
                "INSERT INTO plat.dominio (tenant_id, nome, tipo, tipo_campo, valores) "
                "VALUES (plat.tenant_atual(), %s, 'codificado', 'text', %s::jsonb)",
                (corpo["nome"], json.dumps(corpo["valores"])),
            )
    assert e.value.diag.message_primary == "dominio_codigo_duplicado"
    con.rollback()


def test_trocar_tipo_de_campo_com_dominio_ligado_recusado(camada, dominios, sessao):
    d = dominios(tipo="codificado", tipo_campo="text", valores=codificado(2))
    assert sessao.post(f"/api/camadas/{camada.item_id}/dominios",
                         json={"campo": "uf", "dominio_id": d["id"]}).status_code == 201
    r = sessao.put(f"/api/dominios/{d['id']}", json={
        "nome": d["nome"], "tipo": "codificado", "tipo_campo": "integer",
        "valores": [{"codigo": "1", "descricao": "um"}]})
    assert r.status_code == 409 and r.json()["erro"] == "dominio_tipo_em_uso", r.text
    assert r.json()["detalhe"]["campo"] == "uf" and r.json()["detalhe"]["tipo_do_campo"] == "text"


def test_apagar_dominio_ligado_recusado(camada, dominios, sessao):
    d = dominios(tipo="codificado", tipo_campo="text", valores=codificado(2))
    assert sessao.post(f"/api/camadas/{camada.item_id}/dominios",
                         json={"campo": "uf", "dominio_id": d["id"]}).status_code == 201
    r = sessao.delete(f"/api/dominios/{d['id']}")
    assert r.status_code == 409 and r.json()["erro"] == "dominio_ligado", r.text


def test_campo_inexistente_e_tipo_incompativel(camada, dominios, sessao):
    d = dominios(tipo="codificado", tipo_campo="text", valores=codificado(2))
    r = sessao.post(f"/api/camadas/{camada.item_id}/dominios", json={"campo": "nao_existe",
                                                                      "dominio_id": d["id"]})
    assert r.status_code == 404 and r.json()["erro"] == "campo_inexistente", r.text
    r = sessao.post(f"/api/camadas/{camada.item_id}/dominios", json={"campo": "altura", "dominio_id": d["id"]})
    assert r.status_code == 422 and r.json()["erro"] == "tipo_incompativel", r.text


def test_desligar_remove_o_gatilho_e_o_valor_volta_a_passar(camada, dominios, sessao):
    d = dominios(tipo="codificado", tipo_campo="text", valores=codificado(2))
    r = sessao.post(f"/api/camadas/{camada.item_id}/dominios", json={"campo": "uf", "dominio_id": d["id"]})
    ligacao = r.json()["id"]
    with pytest.raises(psycopg2.errors.RaiseException):
        camada.inserir(uf="XX")
    camada.con.rollback()
    assert sessao.delete(f"/api/camadas/{camada.item_id}/dominios/{ligacao}").status_code == 204
    assert camada.inserir(uf="XX") > 0      # sem ligação, sem gatilho
    camada.con.rollback()


def test_update_tambem_e_validado(camada, dominios, sessao):
    d = dominios(tipo="codificado", tipo_campo="text", valores=codificado(2))
    sessao.post(f"/api/camadas/{camada.item_id}/dominios", json={"campo": "uf", "dominio_id": d["id"]})
    fid = camada.inserir(uf="C0")
    with pytest.raises(psycopg2.errors.RaiseException) as e:
        camada.atualizar(fid, uf="C9")
    assert e.value.diag.message_primary == "valor_fora_do_dominio"
    camada.con.rollback()


# ------------------------------------------------------------------ CSV e importação
def test_csv_exporta_e_reimporta_em_massa(sessao, dominios):
    d = dominios(tipo="codificado", tipo_campo="text", valores=codificado(3))
    r = sessao.get("/api/dominios.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    texto = r.text.lstrip("﻿")
    assert texto.splitlines()[0].startswith("dominio;tipo;tipo_campo")
    linhas = [li for li in texto.splitlines() if li.startswith(d["nome"] + ";")]
    assert len(linhas) == 3
    editado = texto.replace("Descrição 0", "Descrição zero editada")
    r = sessao.post("/api/dominios/csv", json={"csv": editado})
    assert r.status_code == 200, r.text
    assert any(x["id"] == d["id"] for x in r.json()["atualizados"])
    novo = sessao.get(f"/api/dominios/{d['id']}").json()
    assert novo["valores"][0]["descricao"] == "Descrição zero editada"


def test_importar_de_featureserver_cria_liga_e_reaproveita(camada, sessao):
    payload = {
        "prefixo": "zt imp " + secrets.token_hex(3),
        "item_id": camada.item_id,
        "fields": [
            {"name": "uf", "type": "esriFieldTypeString",
             "domain": {"type": "codedValue", "name": "UFs",
                        "codedValues": [{"name": "São Paulo", "code": "SP"}, {"name": "Bahia", "code": "BA"}]}},
            {"name": "altura", "type": "esriFieldTypeDouble",
             "domain": {"type": "range", "name": "Altura", "range": [0, 100]}},
            {"name": "sem_dominio", "type": "esriFieldTypeString"},
        ],
        "types": [
            {"id": 1, "name": "Urbano", "campo_subtipo": "classe",
             "domains": {"situacao": {"type": "codedValue", "name": "Pavimento",
                                      "codedValues": [{"name": "Asfalto", "code": "asfalto"}]}},
             "templates": [{"name": "Urbano", "prototype": {"attributes": {"situacao": "asfalto"}}}]},
            {"id": 2, "name": "Rural", "domains": {"situacao": {"type": "inherited"}}, "templates": []},
        ],
    }
    r = sessao.post("/api/dominios/importar", json=payload)
    assert r.status_code == 200, r.text
    saida = r.json()
    try:
        assert [c["nome"] for c in saida["criados"]] == [f"{payload['prefixo']} UFs",
                                                         f"{payload['prefixo']} Altura",
                                                         f"{payload['prefixo']} Pavimento"]
        assert saida["subtipos"]["campo"] == "classe"
        assert [v["codigo"] for v in saida["subtipos"]["valores"]] == [1, 2]
        assert {(li["campo"], li["subtipo_codigo"]) for li in saida["ligados"]} == {
            ("uf", None), ("altura", None), ("situacao", 1)}
        # a regra do gatilho já vale sobre o que a importação criou
        with pytest.raises(psycopg2.errors.RaiseException):
            camada.inserir(uf="ZZ")
        camada.con.rollback()
        assert camada.inserir(uf="SP", classe=1, situacao="asfalto") > 0
        camada.con.rollback()
        # segunda importação do mesmo payload reaproveita e não duplica
        r2 = sessao.post("/api/dominios/importar", json=payload)
        assert r2.status_code == 200 and r2.json()["criados"] == []
        assert len(r2.json()["reaproveitados"]) == 3
    finally:
        lig = sessao.get(f"/api/camadas/{camada.item_id}/dominios").json()
        for li in lig["ligacoes"]:
            sessao.delete(f"/api/camadas/{camada.item_id}/dominios/{li['id']}")
        sessao.delete(f"/api/camadas/{camada.item_id}/subtipos")
        for c in saida["criados"]:
            sessao.delete(f"/api/dominios/{c['id']}")


def test_banco_regenera_o_gatilho_sem_a_api(camada, dominios, sessao, con, inquilino):
    """O adversário liga um domínio escrevendo direto em plat.dominio_campo, sem passar pela API: o gatilho da
    tabela tem de aparecer do mesmo jeito (é o gatilho AFTER da migração 20260906T1620 que regenera). O mesmo
    vale ao desligar."""
    d = dominios(tipo="codificado", tipo_campo="text", valores=codificado(2))
    camada.contexto()
    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO plat.dominio_campo (tenant_id, item_id, campo, dominio_id) "
            "VALUES (plat.tenant_atual(), %s::uuid, 'uf', %s::uuid)",
            (camada.item_id, d["id"]),
        )
    with pytest.raises(psycopg2.errors.RaiseException) as e:
        camada.inserir(uf="XX")
    assert e.value.diag.message_primary == "valor_fora_do_dominio"
    con.rollback()

    camada.contexto()
    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO plat.dominio_campo (tenant_id, item_id, campo, dominio_id) "
            "VALUES (plat.tenant_atual(), %s::uuid, 'uf', %s::uuid)",
            (camada.item_id, d["id"]),
        )
        cur.execute("SELECT count(*) AS n FROM pg_trigger tg JOIN pg_class c ON c.oid = tg.tgrelid "
                    "WHERE c.relname = %s AND tg.tgname = 'tg_dominio'", (camada.tabela,))
        assert cur.fetchone()["n"] == 1
        cur.execute("DELETE FROM plat.dominio_campo WHERE item_id = %s::uuid", (camada.item_id,))
        cur.execute("SELECT count(*) AS n FROM pg_trigger tg JOIN pg_class c ON c.oid = tg.tgrelid "
                    "WHERE c.relname = %s AND tg.tgname = 'tg_dominio'", (camada.tabela,))
        assert cur.fetchone()["n"] == 0        # sem ligação, sem gatilho: camada limpa não paga nada
    assert camada.inserir(uf="XX") > 0
    con.rollback()


# ------------------------------------------------------------------ CONSERTO: injeção pelo nome do domínio
# Achado do adversário (handoffs/T3/ataque-L2-hoje-ADVERSARIO.md, worktree wt/advl2): o gerador de
# plat.camada_dominios_aplicar embutia o NOME do domínio, texto do usuário, dentro do corpo delimitado por
# um dollar-tag FIXO ($corpo_gerado$...$corpo_gerado$). Um nome contendo essa string fechava o corpo no meio
# e o resto virava SQL solto, executado como postgres. O CHECK do banco só limitava comprimento; só a API
# barrava "$" — e a migração 20260906T1620 já dizia que a API não é a guarda. Conserto (migração
# 20260906T1829): (1) o nome nunca mais entra como texto no corpo gerado — a mensagem de erro busca o nome
# em tempo de execução pelo uuid do domínio; (2) CHECK + gatilho BEFORE em plat.dominio.nome, mesmo padrão
# da API (NOME_PADRAO), recusam por psql também. Nenhum teste aqui conecta como postgres: tudo é feito com a
# role da aplicação, exatamente como o adversário fez.
def test_injecao_dollar_tag_no_nome_recusada_pelo_banco(camada, dominios, sessao, con, anotar):
    """Reproduz o vetor do adversário pelo gatilho: UPDATE direto em plat.dominio como plat_app, com o nome
    contendo o dollar-tag do gerador. Antes do conserto isso regenerava a função da camada com sintaxe
    quebrada (SyntaxError no INSERT seguinte); agora o BEFORE trigger recusa a própria escrita, em
    português, e a camada continua íntegra e validando."""
    d = dominios(tipo="codificado", tipo_campo="text",
                 valores=[{"codigo": "SP", "descricao": "x"}, {"codigo": "RJ", "descricao": "y"}])
    assert sessao.post(f"/api/camadas/{camada.item_id}/dominios",
                        json={"campo": "uf", "dominio_id": d["id"]}).status_code == 201
    assert camada.inserir(uf="SP") > 0
    con.rollback()

    camada.contexto()
    with con.cursor() as cur:
        with pytest.raises(psycopg2.errors.RaiseException) as e:
            cur.execute("UPDATE plat.dominio SET nome = %s WHERE id = %s::uuid",
                        ("regiao $corpo_gerado$ x", d["id"]))
        assert e.value.diag.message_primary == "dominio_nome_invalido"
    con.rollback()

    # a camada continua íntegra: o nome do domínio não mudou e o gatilho ainda valida certo e errado
    assert camada.inserir(uf="SP") > 0
    con.rollback()
    with pytest.raises(psycopg2.errors.RaiseException) as e:
        camada.inserir(uf="ZZ")
    assert e.value.diag.message_primary == "valor_fora_do_dominio"
    con.rollback()
    anotar("injecao_dollar_tag_no_nome_recusada", True)


HOSTIS = (
    # dollar-tags: o vetor original e variações
    "regiao $corpo_gerado$ x", "$corpo_gerado$", "x$corpo_gerado$y", "$$", "a$$b", "$tag$drop table$tag$",
    "$" * 20, "$corpo_gerado$$corpo_gerado$", "pre$corpo_ger" "ado$pos",
    # aspas e escape de string
    "O'Brien", "a''b", "a\"b", "a\\b", "a\\'b", "'; DROP TABLE plat.dominio; --",
    # comentário e ponto e vírgula
    "a; DROP TABLE plat.dominio_valor; --", "--comentario", "/*bloco*/", "a/*b*/c", "a;b;c", ";;;",
    # identificador/format() do postgres
    "%I", "%L", "%1$I", "%s", "a%%b", '"aspas duplas"',
    # controle e whitespace
    "a\nb", "a\tb", "a\rb", "\x01\x02\x03", "\x1b[31m", "a\x0bb", "\x7f",
    # unicode hostil (RTL override, zero-width, combinação, emoji, look-alike de $ e aspas)
    "a​b", "‮drop", "é", "\U0001f4a5", "＄corpo_gerado＄", "＇; --", "café com açúcar",
    # limites de tamanho e vazio-como-espaço
    "x" * 121, "x" * 500, " ", "",
    # NUL — psycopg2 recusa no cliente, antes de qualquer round-trip ao servidor
    "a\x00b", "\x00",
)


def _tentativa_nome(con, inquilino, nome: str):
    """Tenta criar um domínio com o nome hostil direto no banco, como plat_app (nunca como postgres).
    Devolve ('recusado', mensagem) | ('recusado_cliente', motivo) | ('aceito', id)."""
    con.rollback()
    contexto(con, inquilino.id, usuario_id=inquilino.admin_id, login="admin")
    try:
        with con.cursor() as cur:
            cur.execute(
                "INSERT INTO plat.dominio (tenant_id, nome, tipo, tipo_campo, valores) "
                "VALUES (plat.tenant_atual(), %s, 'codificado', 'text', %s::jsonb) RETURNING id",
                (nome, json.dumps([{"codigo": "A", "descricao": "a"}])),
            )
            row = cur.fetchone()
        con.commit()
        return ("aceito", row["id"] if row else None)
    except ValueError as e:
        con.rollback()
        return ("recusado_cliente", str(e))          # ex.: NUL byte — psycopg2 recusa antes de ir ao servidor
    except psycopg2.Error as e:
        con.rollback()
        return ("recusado", getattr(e.diag, "message_primary", str(e)))


SEGURO = re.compile(r"^[A-Za-z_][A-Za-z0-9_ .\-]{0,119}$")  # mesma regra da API (NOME_PADRAO) e do CHECK


def test_200_nomes_hostis_nunca_quebram_a_sintaxe_do_gerador(inquilino, sessao, con, camada, dominios, anotar):
    """Bateria de pelo menos 200 nomes (aspas, dollar-tags de várias formas, ponto e vírgula, comentário SQL,
    especificador de format(), controle, unicode e NUL — 51 padrões-base × 5 variações de prefixo/sufixo/
    repetição). A propriedade provada não é "todo nome é recusado": alguns dos padrões-base (ex. hífen
    duplo, espaços) usam só caracteres do alfabeto seguro (NOME_PADRAO da API) e são nomes LEGÍTIMOS — o
    hífen sozinho não abre SQL solto quando o nome nunca é escrito cru fora de aspas/parâmetro. A
    propriedade é: (1) todo nome com caractere FORA do alfabeto seguro é recusado, sempre pela mesma regra
    nomeada, nunca por um erro de sintaxe do Postgres vazando pro cliente; (2) todo nome DENTRO do alfabeto
    é aceito e, ligado a um campo real, o gatilho gerado continua compilando e validando certo."""
    base = list(HOSTIS)
    variacoes = []
    for h in base:
        variacoes.append(h)
        variacoes.append(f"prefixo {h}")
        variacoes.append(f"{h} sufixo")
        variacoes.append(f"{h}{h}")
        variacoes.append(f"zt {h} zt")
    assert len(variacoes) >= 200, len(variacoes)

    recusados = aceitos = 0
    mensagens_recusa = set()
    for nome in variacoes:
        deveria_passar = bool(SEGURO.match(nome))
        resultado, detalhe = _tentativa_nome(con, inquilino, nome)
        if deveria_passar:
            assert resultado == "aceito", f"nome seguro recusado: {nome!r} -> {resultado}/{detalhe}"
            aceitos += 1
            # prova de verdade: ligar a um campo real e o gatilho gerado tem de compilar e validar certo,
            # nunca um erro de sintaxe do Postgres.
            r = sessao.post(f"/api/camadas/{camada.item_id}/dominios",
                             json={"campo": "situacao", "dominio_id": detalhe})
            assert r.status_code in (201, 409, 422), r.text
            if r.status_code == 201:
                lig_id = r.json()["id"]
                assert camada.inserir(situacao="A") > 0
                con.rollback()
                with pytest.raises(psycopg2.errors.RaiseException) as e:
                    camada.inserir(situacao="ZZ")
                assert e.value.diag.message_primary == "valor_fora_do_dominio"
                con.rollback()
                camada.contexto()
                sessao.delete(f"/api/camadas/{camada.item_id}/dominios/{lig_id}")
        else:
            assert resultado in ("recusado", "recusado_cliente"), \
                f"nome hostil foi aceito: {nome!r} -> {detalhe}"
            recusados += 1
            if resultado == "recusado":
                mensagens_recusa.add(detalhe)

    con.rollback()
    assert recusados + aceitos == len(variacoes)
    # a recusa é sempre a mesma regra nomeada — nunca "syntax error at or near" do Postgres vazando pro
    # cliente, que era exatamente o sintoma do achado do adversário.
    assert mensagens_recusa <= {"dominio_nome_invalido"}, mensagens_recusa
    anotar("nomes_hostis_testados", len(variacoes), "nomes")
    anotar("nomes_hostis_recusados", recusados, "nomes")
    anotar("nomes_hostis_seguros_aceitos_e_validados", aceitos, "nomes")

    # sanidade final: a camada segue válida e o gatilho gerado continua vivo e correto depois da bateria
    d = dominios(tipo="codificado", tipo_campo="text", valores=codificado(2))
    assert sessao.post(f"/api/camadas/{camada.item_id}/dominios",
                        json={"campo": "uf", "dominio_id": d["id"]}).status_code == 201
    assert camada.inserir(uf="C0") > 0
    con.rollback()
    with pytest.raises(psycopg2.errors.RaiseException):
        camada.inserir(uf="ZZ")
    con.rollback()
