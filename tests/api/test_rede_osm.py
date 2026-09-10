"""Conector OpenStreetMap power=* da rede de utilidades (item L4-05-g-osm-power).

Cláusulas do portão provadas aqui: "importar power=* de 1 município a partir do .pbf existente
(...) -> rede com topologia" (`test_importa_um_municipio_e_confere_a_topologia`); "ficha mostra
ODbL e 'cadastro comunitário, não oficial'" (`test_ficha_mostra_licenca_e_aviso`); "contagem de
linhas/torres = contagem do extrato" (a mesma prova de topologia, campo `conferido`); "teste
automatizado" (este arquivo). Refutação do item: `test_nunca_liga_no_de_outra_fonte_por_coincidencia`
mistura um nó de outra fonte no mesmo inquilino, coincidente em geometria com um nó OSM, e confere
que a importação não cria associação nenhuma com ele.

O extrato de teste é `tests/dados/taquari_power.osm` (gerado por `gerar_osm_power.py`, sem baixar
nada da internet): duas vias (`line`/`minor_line`) cortadas por nó tipado, torre e poste fixados no
trecho sem cortar, um ativo avulso sem via, um trecho com ponta fora do recorte (torre nessa ponta
fica de fora, contada em `fora_do_limite`), uma área de subestação com junção dentro e uma relação
power=* (só contada, não importada nesta passagem)."""

import json
import os
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest

from app.rede_utilidades import instalados
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug

RAIZ = Path(__file__).resolve().parents[2]
EXTRATO = str(RAIZ / "tests" / "dados" / "taquari_power.osm")
MUNICIPIO = json.loads((RAIZ / "tests" / "dados" / "taquari_limite.geojson").read_text())


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _rede_com_eletrica(sessao, limpar, sufixo):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-rede-osm-{sufixo}", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append(rid)
    bruto = instalados.bruto("eletrica-br")
    r = sessao.post(f"/api/rede/{rid}/pacote", content=bruto, headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    return rid


def _importar(sessao, rid):
    corpo = {"caminho": EXTRATO, "municipio": MUNICIPIO, "nome_municipio": "Taquari"}
    return sessao.post(f"/api/rede/{rid}/importar-osm", json=corpo)


# --- cláusula: importar power=* de 1 município -> rede com topologia, contagem conferida --------------------

def test_importa_um_municipio_e_confere_a_topologia(sessao_a, limpar_redes):
    rid = _rede_com_eletrica(sessao_a, limpar_redes, "topologia")
    r = _importar(sessao_a, rid)
    assert r.status_code == 201, r.text
    corpo = r.json()

    assert corpo["conferido"] is True, corpo["contagens"]
    contagens = corpo["contagens"]
    # a régua pública: o que o extrato tinha dentro do recorte == o que entrou, por etiqueta.
    assert contagens["line"] == {"arquivo": 2, "inserido": 2}
    assert contagens["minor_line"] == {"arquivo": 1, "inserido": 1}
    assert contagens["tower"] == {"arquivo": 1, "inserido": 1}
    assert contagens["pole"] == {"arquivo": 1, "inserido": 1}
    assert contagens["transformer"] == {"arquivo": 2, "inserido": 2}
    assert contagens["substation"] == {"arquivo": 1, "inserido": 1}
    assert contagens["substation_area"] == {"arquivo": 1, "inserido": 1}

    # topologia: via A (4 vértices, corta em 1 nó tipado) produz 2 trechos; via B (3 vértices,
    # corta só na ponta) produz 1; via C (fora->dentro) produz 1. 4 trechos ao todo.
    assert corpo["trechos_gerados"] == 4
    # torre sobre a via A e poste sobre a via B: as duas têm regra de fixação no pacote eletrica-br.
    assert corpo["fixacoes"] == 2

    # torre n9, na ponta da via C que fica fora do recorte, não vira ativo tipado.
    assert corpo["fora_do_limite"] == {"tower": 1}
    # ativo avulso (n7, transformador sem via de rede tocando) e a relação power=* (não importada
    # nesta passagem) aparecem como desvio explicado, nunca em silêncio.
    assert corpo["desvios"]["ativo_sem_via_de_rede"]["quantidade"] == 1
    assert corpo["desvios"]["relacao_nao_importada"]["quantidade"] == 1
    assert "fixacao_sem_regra_no_pacote" not in corpo["desvios"]

    # a topologia realmente existe nas tabelas (não só no resultado devolvido pela rota).
    con = psycopg2.connect(os.environ["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
        contexto(con, ids["demo"])
        with con.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM plat.rede_no WHERE rede_id = %s::uuid AND atributos->>'fonte' = 'OSM'",
                (rid,),
            )
            assert cur.fetchone()["n"] >= 1
            cur.execute(
                "SELECT count(*) AS n FROM plat.rede_aresta WHERE rede_id = %s::uuid "
                "AND atributos->>'fonte' = 'OSM'",
                (rid,),
            )
            assert cur.fetchone()["n"] == 4
            cur.execute(
                "SELECT count(*) AS n FROM plat.rede_associacao WHERE rede_id = %s::uuid AND tipo = 'fixacao'",
                (rid,),
            )
            assert cur.fetchone()["n"] == 2
    finally:
        con.close()


def test_ficha_mostra_licenca_e_aviso(sessao_a, limpar_redes):
    rid = _rede_com_eletrica(sessao_a, limpar_redes, "ficha")
    r = _importar(sessao_a, rid)
    assert r.status_code == 201, r.text

    ficha = sessao_a.get(f"/api/rede/{rid}/importacoes")
    assert ficha.status_code == 200, ficha.text
    itens = ficha.json()["itens"]
    assert len(itens) == 1
    item = itens[0]
    assert item["fonte"] == "osm"
    assert item["estado"] == "concluida"
    assert item["municipio"] == "Taquari"
    assert "ODbL" in item["licenca"]
    assert item["aviso"] == "cadastro comunitário, não oficial"
    assert len(item["sha256"]) == 64


def test_sem_pacote_recusa_com_a_lista_dos_tipos_que_faltam(sessao_a, limpar_redes):
    r = sessao_a.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-rede-osm-sem-pacote", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar_redes.append(rid)
    r = _importar(sessao_a, rid)
    assert r.status_code == 422, r.text
    assert "eletrica-br" in r.json()["mensagem"] or "pacote" in r.json()["mensagem"]


def test_extrato_inexistente_e_erro_explicado_nao_excecao_crua(sessao_a, limpar_redes):
    rid = _rede_com_eletrica(sessao_a, limpar_redes, "sem-arquivo")
    corpo = {"caminho": "/nao/existe/em/lugar/nenhum.osm", "municipio": MUNICIPIO, "nome_municipio": "Taquari"}
    r = sessao_a.post(f"/api/rede/{rid}/importar-osm", json=corpo)
    assert r.status_code == 422, r.text
    assert "não encontrado" in r.json()["mensagem"]


# --- refutação do item: OSM nunca se liga a um nó de outra fonte sem associação explícita --------------------

def test_nunca_liga_no_de_outra_fonte_por_coincidencia(sessao_a, limpar_redes):
    """Insere direto no banco um nó de outra fonte (fonte='bdgd'), NA MESMA COORDENADA do nó de
    subestação que o extrato OSM corta (n3, -51.830/-29.742) -- coincidência geométrica de propósito.
    Depois de importar o OSM por cima, nenhuma associação da importação pode referenciar esse nó:
    o conector nunca liga elementos de fontes diferentes por estarem no mesmo lugar, só por
    referência explícita do próprio extrato (o que o OSM nunca declara para um nó alheio)."""
    rid = _rede_com_eletrica(sessao_a, limpar_redes, "isolamento")

    con = psycopg2.connect(os.environ["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
        tenant_id = ids["demo"]
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
            usuario_id = cur.fetchone()["usuario_id"]
        contexto(con, tenant_id, usuario_id)
        with con.cursor() as cur:
            cur.execute(
                "SELECT t.id FROM plat.rede_tipo t JOIN plat.rede_grupo g ON g.id = t.grupo_id "
                "WHERE t.rede_id = %s::uuid AND g.codigo = 'subestacao' AND t.codigo = 1",
                (rid,),
            )
            tipo_subestacao_id = cur.fetchone()["id"]
            cur.execute(
                "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id, codigo_externo, geom, atributos) "
                "VALUES (%s, %s::uuid, 'fonte', %s::uuid, 'bdgd-coincidente', "
                "ST_SetSRID(ST_MakePoint(-51.830, -29.742), 4326), %s) RETURNING id",
                (tenant_id, rid, tipo_subestacao_id, psycopg2.extras.Json({"fonte": "bdgd"})),
            )
            no_bdgd_id = cur.fetchone()["id"]
        con.commit()
    finally:
        con.close()

    r = _importar(sessao_a, rid)
    assert r.status_code == 201, r.text

    con = psycopg2.connect(os.environ["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        contexto(con, tenant_id)
        with con.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM plat.rede_associacao WHERE rede_id = %s::uuid "
                "AND (de_no_id = %s::uuid OR para_no_id = %s::uuid)",
                (rid, no_bdgd_id, no_bdgd_id),
            )
            assert cur.fetchone()["n"] == 0, "o conector OSM ligou algo ao nó de outra fonte por coincidência"
            # o nó de outra fonte continua exatamente como foi inserido, intacto.
            cur.execute("SELECT atributos->>'fonte' AS fonte FROM plat.rede_no WHERE id = %s::uuid", (no_bdgd_id,))
            assert cur.fetchone()["fonte"] == "bdgd"
    finally:
        con.close()


# --- teto de leitura declarado (regra dura: nunca extração de OSM em memória sem limite) ---------------------

def test_extrato_acima_do_teto_e_recusado_sem_estourar_memoria(monkeypatch, sessao_a, limpar_redes):
    from app.rede_utilidades import osm_power

    monkeypatch.setattr(osm_power, "MAX_ELEMENTOS", 3)
    rid = _rede_com_eletrica(sessao_a, limpar_redes, "teto")
    r = _importar(sessao_a, rid)
    assert r.status_code == 422, r.text
    assert "teto" in r.json()["mensagem"] or "300" in r.json()["mensagem"] or "3" in r.json()["mensagem"]
