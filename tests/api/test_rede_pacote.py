"""Rotas da rede de utilidades (item L4-01-a-pacote-de-ativos): `/api/rede`, importação e exportação do pacote
de ativos.

Cláusulas do portão provadas aqui: "POST /api/rede/{rede_id}/pacote importa um pacote JSON e GET .../pacote
devolve o mesmo JSON byte a byte (round-trip testado)"; "DDL plat.rede_* de catálogo em migração idempotente
com RLS". Refutação do item: pacote com tier apontando domínio inexistente e com dois tipos de mesmo código são
recusados com a linha; exportar de um inquilino e reimportar em outro não vaza nada do primeiro."""

import copy
import hashlib
import json

import psycopg2
import pytest

from app.rede_utilidades import instalados
from app.rede_utilidades import pacote as pacote_mod
from app.schema_ambiente import CursorSchemaAmbiente  # honra PLAT_SCHEMA (base própria por trilha)
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug

TABELAS = ("rede", "rede_dominio", "rede_tier", "rede_categoria", "rede_terminal_config", "rede_grupo",
           "rede_tipo", "rede_tipo_categoria", "rede_atributo", "rede_regra")


@pytest.fixture
def limpar_redes(sessao_a, sessao_b):
    criadas = []
    yield criadas
    for sessao, rid in criadas:
        sessao.delete(f"/api/rede/{rid}")


def _criar(sessao, sufixo, disciplina="eletrica"):
    return sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-rede-{sufixo}", "disciplina": disciplina})


def _importar(sessao, rid, bruto: bytes):
    return sessao.post(f"/api/rede/{rid}/pacote", content=bruto, headers={"Content-Type": "application/json"})


def _rede_com_pacote(sessao, limpar, sufixo, codigo="agua-epanet", disciplina="agua"):
    r = _criar(sessao, sufixo, disciplina)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append((sessao, rid))
    bruto = instalados.bruto(codigo)
    assert _importar(sessao, rid, bruto).status_code == 201
    return rid, bruto


# --- ida e volta -------------------------------------------------------------------------------------

@pytest.mark.parametrize("codigo,disciplina", [("eletrica-br", "eletrica"), ("agua-epanet", "agua")])
def test_importa_e_exporta_byte_a_byte(sessao_a, limpar_redes, codigo, disciplina):
    rid, bruto = _rede_com_pacote(sessao_a, limpar_redes, f"ida-volta-{codigo}", codigo, disciplina)
    r = sessao_a.get(f"/api/rede/{rid}/pacote")
    assert r.status_code == 200
    assert r.content == bruto, "a exportação não bate byte a byte com o arquivo importado"
    assert r.headers["ETag"].strip('"') == hashlib.sha256(bruto).hexdigest()


def test_a_exportacao_vem_das_tabelas_e_nao_do_arquivo_recebido(sessao_a, limpar_redes, env):
    """Prova de que o pacote foi mesmo carregado: mexendo numa linha do banco, a exportação muda junto."""
    rid, bruto = _rede_com_pacote(sessao_a, limpar_redes, "vem-das-tabelas")
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
        contexto(con, ids["demo"])
        with con.cursor() as cur:
            cur.execute("UPDATE plat.rede_grupo SET nome = %s WHERE rede_id = %s::uuid AND codigo = 'bomba'",
                        ("Bomba renomeada dentro do banco", rid))
            assert cur.rowcount == 1
        con.commit()
    finally:
        con.close()
    r = sessao_a.get(f"/api/rede/{rid}/pacote")
    assert r.status_code == 200 and r.content != bruto
    grupo = next(g for g in json.loads(r.content)["grupos"] if g["codigo"] == "bomba")
    assert grupo["nome"] == "Bomba renomeada dentro do banco"


def test_importar_de_novo_substitui_o_catalogo_inteiro(sessao_a, limpar_redes):
    rid, _ = _rede_com_pacote(sessao_a, limpar_redes, "substitui")
    r = _importar(sessao_a, rid, instalados.bruto("eletrica-br"))
    assert r.status_code == 201, r.text
    assert r.json()["contagens"]["atributos"] == 214
    assert sessao_a.get(f"/api/rede/{rid}/pacote").content == instalados.bruto("eletrica-br")
    ficha = sessao_a.get(f"/api/rede/{rid}").json()
    assert ficha["pacote"]["codigo"] == "eletrica-br" and ficha["contagens"]["grupos"] == 14


def test_rede_sem_pacote_responde_404_na_exportacao(sessao_a, limpar_redes):
    r = _criar(sessao_a, "vazia")
    limpar_redes.append((sessao_a, r.json()["id"]))
    assert sessao_a.get(f"/api/rede/{r.json()['id']}/pacote").status_code == 404


def test_pacotes_instalados_sao_servidos_iguais_ao_disco(sessao_a):
    lista = sessao_a.get("/api/rede/pacotes")
    assert lista.status_code == 200
    codigos = {i["codigo"] for i in lista.json()["itens"]}
    assert {"eletrica-br", "agua-epanet"} <= codigos
    for codigo in codigos:
        r = sessao_a.get(f"/api/rede/pacotes/{codigo}")
        assert r.status_code == 200 and r.content == instalados.bruto(codigo)
    assert sessao_a.get("/api/rede/pacotes/nao-existe").status_code == 404


# --- refutação do item -------------------------------------------------------------------------------

def test_tier_com_dominio_inexistente_e_recusado_apontando_a_linha(sessao_a, limpar_redes):
    r = _criar(sessao_a, "adv-dominio")
    limpar_redes.append((sessao_a, r.json()["id"]))
    doc = pacote_mod.ler(instalados.bruto("agua-epanet"))
    doc["tiers"][0]["dominio"] = "dominio-que-nao-existe"
    bruto = (json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    resp = _importar(sessao_a, r.json()["id"], bruto)
    assert resp.status_code == 422 and resp.json()["erro"] == "pacote_invalido"
    problemas = [p for p in resp.json()["detalhe"] if p["erro"] == "dominio_inexistente"]
    assert len(problemas) == 1
    linha = bruto.decode("utf-8").splitlines()[problemas[0]["linha"] - 1]
    assert "dominio-que-nao-existe" in linha
    assert sessao_a.get(f"/api/rede/{r.json()['id']}/pacote").status_code == 404  # nada entrou


def test_dois_tipos_de_mesmo_codigo_sao_recusados_apontando_as_duas_linhas(sessao_a, limpar_redes):
    r = _criar(sessao_a, "adv-repetido")
    limpar_redes.append((sessao_a, r.json()["id"]))
    doc = pacote_mod.ler(instalados.bruto("agua-epanet"))
    gemeo = copy.deepcopy(doc["tipos"][3])
    gemeo["chave"] = "zt-gemeo-do-mesmo-codigo"
    doc["tipos"].insert(4, gemeo)
    bruto = (json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    resp = _importar(sessao_a, r.json()["id"], bruto)
    assert resp.status_code == 422
    problemas = [p for p in resp.json()["detalhe"] if p["erro"] == "codigo_repetido"]
    assert len(problemas) == 1 and problemas[0]["linha"] > problemas[0]["linha_anterior"]


def test_pacote_parcialmente_carregado_nao_fica_no_banco(sessao_a, limpar_redes, env):
    """O pacote inválido é recusado ANTES de qualquer escrita: a rede continua sem catálogo."""
    rid, _ = _rede_com_pacote(sessao_a, limpar_redes, "atomico")
    doc = pacote_mod.ler(instalados.bruto("eletrica-br"))
    doc["tipos"][0]["grupo"] = "nao-existe"
    resp = _importar(sessao_a, rid, json.dumps(doc, ensure_ascii=False).encode("utf-8"))
    assert resp.status_code == 422
    ficha = sessao_a.get(f"/api/rede/{rid}").json()
    assert ficha["pacote"]["codigo"] == "agua-epanet" and ficha["contagens"]["atributos"] == 41


# --- isolamento entre inquilinos ---------------------------------------------------------------------

def test_rede_de_um_inquilino_nao_aparece_no_outro(sessao_a, sessao_b, limpar_redes):
    rid, _ = _rede_com_pacote(sessao_a, limpar_redes, "isolada")
    assert sessao_b.get(f"/api/rede/{rid}").status_code == 404
    assert sessao_b.get(f"/api/rede/{rid}/pacote").status_code == 404
    assert _importar(sessao_b, rid, instalados.bruto("agua-epanet")).status_code == 404
    assert sessao_b.delete(f"/api/rede/{rid}").status_code == 404
    assert rid not in {i["id"] for i in sessao_b.get("/api/rede").json()["itens"]}


def test_exportar_de_um_inquilino_e_reimportar_no_outro_nao_leva_nada_do_primeiro(
    sessao_a, sessao_b, limpar_redes, env
):
    """Refutação do item, segunda metade: o pacote é ESQUEMA, não dado; ao atravessar, nada de A vai junto."""
    rid_a, bruto = _rede_com_pacote(sessao_a, limpar_redes, "origem")
    exportado = sessao_a.get(f"/api/rede/{rid_a}/pacote").content

    r = _criar(sessao_b, "destino", "agua")
    rid_b = r.json()["id"]
    limpar_redes.append((sessao_b, rid_b))
    assert _importar(sessao_b, rid_b, exportado).status_code == 201
    assert sessao_b.get(f"/api/rede/{rid_b}/pacote").content == bruto

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
        contexto(con, ids["demo2"])
        with con.cursor() as cur:
            for tabela in TABELAS:
                coluna = "id" if tabela == "rede" else "rede_id"
                cur.execute(
                    f"SELECT count(*) AS n FROM plat.{tabela} WHERE {coluna} = %s::uuid",  # noqa: S608
                    (rid_a,),
                )
                assert cur.fetchone()["n"] == 0, f"{tabela} de B enxerga linha da rede de A"
                cur.execute(f"SELECT count(*) AS n FROM plat.{tabela} WHERE tenant_id <> %s",  # noqa: S608
                            (ids["demo2"],))
                assert cur.fetchone()["n"] == 0, f"{tabela} deixa B ler linha de outro inquilino"
    finally:
        con.rollback()
        con.close()


def test_toda_tabela_do_catalogo_tem_rls_ligada(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            # o schema vem do próprio to_regclass (a suíte pode rodar contra plat, plat_homolog ou a base de
            # uma trilha; nenhuma dessas conexões faz SET search_path)
            "SELECT c.relname, c.relrowsecurity, count(p.polname) AS politicas FROM pg_class c "
            "LEFT JOIN pg_policy p ON p.polrelid = c.oid "
            "WHERE c.relnamespace = (SELECT relnamespace FROM pg_class WHERE oid = to_regclass('plat.rede')) "
            "AND c.relname = ANY(%s) GROUP BY 1, 2",
            (list(TABELAS),),
        )
        linhas = {r["relname"]: r for r in cur.fetchall()}
    assert set(linhas) == set(TABELAS), f"faltou tabela: {set(TABELAS) - set(linhas)}"
    for nome, r in linhas.items():
        assert r["relrowsecurity"], f"{nome} sem RLS"
        assert r["politicas"] == 4, f"{nome} tem {r['politicas']} políticas, esperado 4"


def test_apagar_a_rede_leva_o_catalogo_junto(sessao_a, env):
    r = _criar(sessao_a, "cascata", "agua")
    rid = r.json()["id"]
    assert _importar(sessao_a, rid, instalados.bruto("agua-epanet")).status_code == 201
    assert sessao_a.delete(f"/api/rede/{rid}").status_code == 204
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        contexto(con, ids_por_slug(con)["demo"])
        with con.cursor() as cur:
            for tabela in TABELAS:
                coluna = "id" if tabela == "rede" else "rede_id"
                cur.execute(f"SELECT count(*) AS n FROM plat.{tabela} WHERE {coluna} = %s::uuid",  # noqa: S608
                            (rid,))
                assert cur.fetchone()["n"] == 0, tabela
    finally:
        con.rollback()
        con.close()
