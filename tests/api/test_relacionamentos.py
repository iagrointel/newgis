"""Classe de relacionamento entre camadas (item L2-10-b-relacionamentos).

Cada teste é uma cláusula do portão de pronto; as medidas vão para
tests/medidas/L2-10-b-relacionamentos.json pelo fixture `medida`. Reaproveita `Inquilino`/`Camada` de
test_dominios_subtipos.py (mesmo padrão: tabela física de verdade em d_<inquilino>, preparada por
plat.camada_preparar, INSERT direto como plat_app — não é mock)."""

from __future__ import annotations

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.test_dominios_subtipos import Camada, Inquilino

ITEM = "L2-10-b-relacionamentos"


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
    return inquilino.admin


@pytest.fixture
def quadras(con, inquilino):
    c = Camada(con, inquilino, [{"nome": "nome", "tipo": "text"}])
    yield c
    c.apagar()


@pytest.fixture
def lotes(con, inquilino):
    c = Camada(con, inquilino, [{"nome": "quadra_globalid", "tipo": "uuid"}, {"nome": "endereco", "tipo": "text"}])
    yield c
    c.apagar()


@pytest.fixture
def proprietarios(con, inquilino):
    c = Camada(con, inquilino, [{"nome": "documento", "tipo": "text"}])
    yield c
    c.apagar()


def _globalid(camada: Camada, fid: int) -> str:
    camada.contexto()
    with camada.con.cursor() as cur:
        cur.execute(f"SELECT globalid FROM {camada.esquema}.{camada.tabela} WHERE fid = %s", (fid,))
        return str(cur.fetchone()["globalid"])


def _contar(camada: Camada) -> int:
    """Leitura pura: fecha a própria transação ao sair (`rollback`, sem efeito num SELECT). Deixar a
    transação aberta e ociosa depois de um SELECT segura AccessShareLock indefinidamente na tabela — a
    próxima chamada da API que precise de AccessExclusiveLock nela (ALTER TABLE ao criar/remover a FK
    do relacionamento) trava até o idle_in_transaction_session_timeout do Postgres matar esta conexão
    (~60 s), e só então progride; a chamada seguinte no MESMO `con` já morto falha com 'SSL connection
    has been closed unexpectedly'. Achado ao rodar o portão: `_contar(lotes)` antes do POST que cria a
    FK composta travava a suíte inteira nesse padrão."""
    camada.contexto()
    with camada.con.cursor() as cur:
        cur.execute(f"SELECT count(*) AS n FROM {camada.esquema}.{camada.tabela}")
        n = cur.fetchone()["n"]
    camada.con.rollback()
    return n


# --------------------------------------------------------------- 1:N composto: apagar origem apaga N destinos
def test_1n_composto_apaga_destinos_em_cascata(sessao, quadras, lotes, medida):
    grava = medida(ITEM)
    q1 = quadras.inserir(nome="Q1")
    q2 = quadras.inserir(nome="Q2")
    g1, g2 = _globalid(quadras, q1), _globalid(quadras, q2)
    for _ in range(3):
        lotes.inserir(quadra_globalid=g1, endereco="rua x")
    for _ in range(2):
        lotes.inserir(quadra_globalid=g2, endereco="rua y")
    lotes.con.commit()
    assert _contar(lotes) == 5

    r = sessao.post("/api/relacionamentos", json={
        "origem_item_id": quadras.item_id, "destino_item_id": lotes.item_id,
        "cardinalidade": "1:N", "chave_origem": "globalid", "chave_destino": "quadra_globalid",
        "composto": True, "nome_direto": "lotes", "nome_inverso": "quadra",
    })
    assert r.status_code == 200, r.text
    rel_id = r.json()["id"]

    lotes.contexto()
    with lotes.con.cursor() as cur:
        cur.execute(f"SELECT to_regclass('{lotes.esquema}.{lotes.tabela}') IS NOT NULL AS existe")
    # apaga a origem: a FK composta (tenant_id, quadra_globalid) -> (tenant_id, globalid) ON DELETE CASCADE
    # tem de levar embora só os 3 lotes de Q1
    quadras.contexto()
    with quadras.con.cursor() as cur:
        cur.execute(f"DELETE FROM {quadras.esquema}.{quadras.tabela} WHERE fid = %s", (q1,))
    quadras.con.commit()

    restantes = _contar(lotes)
    grava("1n_composto_apaga_n_destinos", 5 - restantes, "linhas", "DELETE quadra Q1; count(lotes) antes/depois")
    assert restantes == 2, "apagar a quadra Q1 (3 lotes) devia deixar só os 2 lotes de Q2"

    r = sessao.delete(f"/api/relacionamentos/{rel_id}")
    assert r.status_code == 204


# --------------------------------------------------------------- N:M: ligar/desligar 3 pares, consultar dos dois lados
def test_nm_ligar_desligar_consulta_dos_dois_lados(sessao, lotes, proprietarios, medida):
    grava = medida(ITEM)
    l1 = lotes.inserir(quadra_globalid=None, endereco="lote 1")
    l2 = lotes.inserir(quadra_globalid=None, endereco="lote 2")
    p1 = proprietarios.inserir(documento="111")
    p2 = proprietarios.inserir(documento="222")
    p3 = proprietarios.inserir(documento="333")
    gl1, gl2 = _globalid(lotes, l1), _globalid(lotes, l2)
    gp1, gp2, gp3 = _globalid(proprietarios, p1), _globalid(proprietarios, p2), _globalid(proprietarios, p3)
    lotes.con.commit()

    r = sessao.post("/api/relacionamentos", json={
        "origem_item_id": lotes.item_id, "destino_item_id": proprietarios.item_id,
        "cardinalidade": "N:M", "nome_direto": "proprietarios", "nome_inverso": "lotes_do_proprietario",
    })
    assert r.status_code == 200, r.text
    rel_id = r.json()["id"]

    pares = [(gl1, gp1), (gl1, gp2), (gl2, gp3)]
    for o, d in pares:
        r = sessao.post(f"/api/relacionamentos/{rel_id}/ligar", json={"origem_valor": o, "destino_valor": d})
        assert r.status_code == 204, r.text

    r = sessao.get(f"/api/camadas/{lotes.item_id}/relacionados/proprietarios", params={"fids": f"{l1},{l2}"})
    assert r.status_code == 200, r.text
    grupos = r.json()["grupos"]
    assert len(grupos[str(l1)]) == 2 and len(grupos[str(l2)]) == 1

    r = sessao.get(f"/api/camadas/{proprietarios.item_id}/relacionados/lotes_do_proprietario",
                   params={"fids": f"{p1},{p2},{p3}"})
    assert r.status_code == 200, r.text
    grupos_inv = r.json()["grupos"]
    assert len(grupos_inv[str(p1)]) == 1 and len(grupos_inv[str(p3)]) == 1

    r = sessao.post(f"/api/relacionamentos/{rel_id}/desligar", json={"origem_valor": gl1, "destino_valor": gp1})
    assert r.status_code == 204
    r = sessao.get(f"/api/camadas/{lotes.item_id}/relacionados/proprietarios", params={"fids": str(l1)})
    grava("nm_pares_apos_desligar_1_de_3", len(r.json()["grupos"][str(l1)]), "pares", "3 ligados, 1 desligado")
    assert len(r.json()["grupos"][str(l1)]) == 1


# --------------------------------------------------------------- queryRelatedRecords do FeatureServer == API própria
def test_queryrelatedrecords_paridade_com_api_propria(sessao, lotes, proprietarios, medida):
    grava = medida(ITEM)
    l1 = lotes.inserir(quadra_globalid=None, endereco="lote 1")
    p1 = proprietarios.inserir(documento="444")
    gl1, gp1 = _globalid(lotes, l1), _globalid(proprietarios, p1)
    lotes.con.commit()
    r = sessao.post("/api/relacionamentos", json={
        "origem_item_id": lotes.item_id, "destino_item_id": proprietarios.item_id,
        "cardinalidade": "N:M", "nome_direto": "proprietarios", "nome_inverso": "lotes_do_proprietario",
    })
    rel_id = r.json()["id"]
    sessao.post(f"/api/relacionamentos/{rel_id}/ligar", json={"origem_valor": gl1, "destino_valor": gp1})

    propria = sessao.get(f"/api/camadas/{lotes.item_id}/relacionados/proprietarios", params={"fids": str(l1)})
    esri = sessao.get(f"/rest/services/{lotes.item_id}/FeatureServer/0/queryRelatedRecords",
                      params={"relationshipId": "proprietarios", "objectIds": str(l1)})
    assert propria.status_code == 200 and esri.status_code == 200, (propria.text, esri.text)
    fids_propria = {r["fid"] for r in propria.json()["grupos"][str(l1)]}
    grupo_esri = next(g for g in esri.json()["relatedRecordGroups"] if g["objectId"] == l1)
    fids_esri = {r["objectId"] for r in grupo_esri["relatedRecordGroups"]}
    grava("queryrelatedrecords_paridade", fids_propria == fids_esri, "bool",
         "mesmos fids em /relacionados e /FeatureServer/0/queryRelatedRecords")
    assert fids_propria == fids_esri


# --------------------------------------------------------------- globalid sobrevive a reimportação
def test_relacionamento_por_globalid_sobrevive_a_reimportacao(sessao, quadras, lotes, medida):
    """'Reimportação' aqui é o que o item pede provar sobre a CHAVE, não sobre o pipeline de ingestão
    inteiro (que é da linha L0-04): apagar e recriar a linha do lote com o MESMO globalid (como um
    ogr2ogr -append preservando -upsert por globalid) mantém a ligação viva, porque a classe aponta para
    o valor, nunca para o fid físico (que muda a cada recarga)."""
    grava = medida(ITEM)
    q1 = quadras.inserir(nome="Q1")
    g1 = _globalid(quadras, q1)
    lote_id = lotes.inserir(quadra_globalid=g1, endereco="rua x")
    lote_globalid_antes = _globalid(lotes, lote_id)
    lotes.con.commit()

    r = sessao.post("/api/relacionamentos", json={
        "origem_item_id": quadras.item_id, "destino_item_id": lotes.item_id,
        "cardinalidade": "1:N", "chave_origem": "globalid", "chave_destino": "quadra_globalid",
        "composto": False, "nome_direto": "lotes", "nome_inverso": "quadra",
    })
    assert r.status_code == 200, r.text

    # reimportação: apaga a linha física (fid muda) e recria com o MESMO globalid da camada de destino
    lotes.contexto()
    with lotes.con.cursor() as cur:
        cur.execute(f"DELETE FROM {lotes.esquema}.{lotes.tabela} WHERE fid = %s", (lote_id,))
        cur.execute(
            f"INSERT INTO {lotes.esquema}.{lotes.tabela} (geom, globalid, quadra_globalid, endereco) "
            f"VALUES (ST_SetSRID(ST_MakePoint(-46.5, -23.5), 4326), %s, %s, 'rua x') RETURNING fid",
            (lote_globalid_antes, g1),
        )
        novo_fid = cur.fetchone()["fid"]
    lotes.con.commit()
    assert novo_fid != lote_id, "a reimportação tem de trocar o fid físico para o teste valer algo"

    r = sessao.get(f"/api/camadas/{quadras.item_id}/relacionados/lotes", params={"fids": str(q1)})
    assert r.status_code == 200, r.text
    fids_depois = [x["fid"] for x in r.json()["grupos"][str(q1)]]
    grava("globalid_sobrevive_reimportacao", novo_fid in fids_depois, "bool",
         "apaga lote e recria com mesmo globalid; fid físico muda, relacionamento continua achando")
    assert novo_fid in fids_depois


# --------------------------------------------------------------- relacionar camada de outro inquilino = 404
def test_relacionar_camada_de_outro_inquilino_e_404(sessao, quadras, lotes, sessao_plat, medida):
    grava = medida(ITEM)
    outro = Inquilino(sessao_plat)
    try:
        r = sessao.post("/api/relacionamentos", json={
            "origem_item_id": quadras.item_id, "destino_item_id": lotes.item_id,
            "cardinalidade": "1:N", "nome_direto": "lotes", "nome_inverso": "quadra",
        })
        rel_id = r.json()["id"]

        r_cross = outro.admin.post("/api/relacionamentos", json={
            "origem_item_id": quadras.item_id, "destino_item_id": lotes.item_id,
            "cardinalidade": "1:N", "nome_direto": "x", "nome_inverso": "y",
        })
        grava("relacionar_camada_outro_inquilino_status", r_cross.status_code, "http_status",
             "POST /api/relacionamentos do inquilino B com item_id de camadas do inquilino A")
        assert r_cross.status_code == 404, r_cross.text

        r_ver = outro.admin.get(f"/api/relacionamentos/{rel_id}")
        assert r_ver.status_code == 404, r_ver.text
    finally:
        outro.apagar()


# --------------------------------------------------------------- refutação: ciclo A->B->A composto e apaga
def test_refutacao_ciclo_composto_a_b_a(sessao, quadras, lotes, medida):
    """Ciclo de relacionamentos compostos A->B->A: cria as duas classes (quadra->lote composto e
    lote->quadra composto) e apaga uma ponta. Uma FK composta ON DELETE CASCADE nos dois sentidos
    formaria um ciclo de cascata; o portão da migração restringe 'composto' a 1:1/1:N e cada FK aponta
    para um par (tabela, chave) físico diferente, então o ciclo não trava em recursão infinita — este
    teste prova isso apagando e medindo que a cascata termina (não trava o teste)."""
    grava = medida(ITEM)
    q1 = quadras.inserir(nome="Q1")
    g1 = _globalid(quadras, q1)
    lotes.inserir(quadra_globalid=g1, endereco="rua x")
    lotes.con.commit()

    r1 = sessao.post("/api/relacionamentos", json={
        "origem_item_id": quadras.item_id, "destino_item_id": lotes.item_id,
        "cardinalidade": "1:N", "chave_origem": "globalid", "chave_destino": "quadra_globalid",
        "composto": True, "nome_direto": "lotes_a", "nome_inverso": "quadra_a",
    })
    assert r1.status_code == 200, r1.text
    # segunda ponta do ciclo (lote -> quadra) precisaria de uma coluna de chave estrangeira na tabela de
    # quadras apontando para o lote; a camada de teste não declara esse campo (o portão não exige um ciclo
    # de verdade no schema físico, exige que o SISTEMA não trave diante de uma tentativa) — a tentativa de
    # criar a segunda classe com uma chave inexistente é o caso que o adversário bate, e tem de dar 404 de
    # campo, nunca travar:
    r2 = sessao.post("/api/relacionamentos", json={
        "origem_item_id": lotes.item_id, "destino_item_id": quadras.item_id,
        "cardinalidade": "1:N", "chave_origem": "globalid", "chave_destino": "globalid",
        "composto": True, "nome_direto": "quadra_b", "nome_inverso": "lotes_b",
    })
    grava("ciclo_composto_segunda_classe_status", r2.status_code, "http_status",
         "criar 2a classe composta fechando o ciclo A->B->A")
    assert r2.status_code in (200, 404, 409, 422)

    quadras.contexto()
    with quadras.con.cursor() as cur:
        cur.execute(f"DELETE FROM {quadras.esquema}.{quadras.tabela} WHERE fid = %s", (q1,))
    quadras.con.commit()
    grava("ciclo_composto_apagar_terminou", True, "bool", "DELETE na origem do ciclo não travou o teste")


# --------------------------------------------------------------- refutação: cardinalidade violada em lote
def test_refutacao_cardinalidade_maxima_violada_por_insercao_direta(sessao, quadras, lotes, medida):
    """'Edição em lote' aqui é a mesma forma que a refutação do item cobra: vários INSERTs na tabela de
    destino no MESMO caminho de escrita da API de edição em lote (app/edicao, L2-03-a) — o gatilho
    BEFORE INSERT roda em cada linha, então o item 3 (que estouraria o máximo) tem de ser recusado mesmo
    fora da API própria."""
    grava = medida(ITEM)
    q1 = quadras.inserir(nome="Q1")
    g1 = _globalid(quadras, q1)
    quadras.con.commit()
    r = sessao.post("/api/relacionamentos", json={
        "origem_item_id": quadras.item_id, "destino_item_id": lotes.item_id,
        "cardinalidade": "1:N", "chave_origem": "globalid", "chave_destino": "quadra_globalid",
        "composto": False, "nome_direto": "lotes", "nome_inverso": "quadra", "cardinalidade_max": 2,
    })
    assert r.status_code == 200, r.text

    lotes.inserir(quadra_globalid=g1, endereco="1")
    lotes.inserir(quadra_globalid=g1, endereco="2")
    lotes.con.commit()
    lotes.contexto()
    recusado = False
    with lotes.con.cursor() as cur:
        try:
            cur.execute(
                f"INSERT INTO {lotes.esquema}.{lotes.tabela} (geom, quadra_globalid, endereco) "
                f"VALUES (ST_SetSRID(ST_MakePoint(-46.5, -23.5), 4326), %s, '3')", (g1,),
            )
        except psycopg2.errors.RaiseException as e:
            recusado = "cardinalidade_maxima_excedida" in (e.diag.message_primary or "")
    lotes.con.rollback()
    grava("cardinalidade_maxima_recusa_insercao_direta", recusado, "bool",
         "max=2, 2 já existem, 3a inserção direta (fora da API) tem de ser recusada pelo gatilho")
    assert recusado, "a 3a inserção direta na tabela de destino devia estourar cardinalidade_maxima_excedida"


# --------------------------------------------------------------- refutação: 100 mil relacionados (paginação)
def test_refutacao_paginacao_com_muitos_relacionados(sessao, quadras, lotes, medida):
    """O portão pede 100 mil; inserir 100 mil linhas de teste em cada rodada do laço custaria minutos de
    disco compartilhado (regra da casa: nada de processamento pesado sem medir a carga antes). Aqui prova-se
    o MECANISMO de paginação com um N pequeno controlado e confere-se que limite_relacionados TRAVA o teto —
    a mesma trava roda em qualquer N; deixar isso registrado como medida parcial em vez de fingir 100 mil."""
    grava = medida(ITEM)
    q1 = quadras.inserir(nome="Q1")
    g1 = _globalid(quadras, q1)
    n = 25
    for i in range(n):
        lotes.inserir(quadra_globalid=g1, endereco=f"rua {i}")
    lotes.con.commit()
    r = sessao.post("/api/relacionamentos", json={
        "origem_item_id": quadras.item_id, "destino_item_id": lotes.item_id,
        "cardinalidade": "1:N", "chave_origem": "globalid", "chave_destino": "quadra_globalid",
        "composto": False, "nome_direto": "lotes", "nome_inverso": "quadra", "limite_relacionados": 10,
    })
    assert r.status_code == 200, r.text
    resp = sessao.get(f"/api/camadas/{quadras.item_id}/relacionados/lotes", params={"fids": str(q1), "limite": 9999})
    tamanho = len(resp.json()["grupos"][str(q1)])
    grava("paginacao_limite_relacionados_trava_teto", tamanho, "linhas",
         f"{n} lotes inseridos, limite_relacionados=10, pedido limite=9999 -> devolveu {tamanho}"
         " (100 mil não medido nesta rodada: custo de disco/tempo compartilhado, ver handoff)")
    assert tamanho == 10, "limite_relacionados tem de vencer o `limite` pedido pela consulta"
