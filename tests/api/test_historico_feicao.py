"""Portão do item L2-03-d-historico-restauracao, medido sobre o código que JÁ está no tronco
(`app/edicao/historico.py`, tabela `plat.feicao_historico` + gatilho `tg_historico` da migração
20260907T1025).

Este arquivo mede as cláusulas do portão que `tests/api/test_edicao_historico_anexos.py` (portão do
item-pai L2-03-edicao) não mede:

  * "editar, listar versões, restaurar a anterior" fechando o ciclo pela API, com GEOMETRIA (o teste
    vizinho restaura só atributo) e conferindo a feição pelo `GET .../feicoes/{globalid}`;
  * "edição em lote de 1.000 feições gera 1.000 linhas de histórico via gatilho (contagem)";
  * "o gatilho não deixa a edição de 1.000 feições passar de 2x o tempo sem histórico" — medido com o
    MESMO lote nas duas condições (gatilho ligado e `ALTER TABLE ... DISABLE TRIGGER tg_historico`
    numa camada gêmea), não contra um número de memória;
  * refutação: `plat_app` só pode ler e inserir no histórico (UPDATE/DELETE direto têm de falhar), com
    o PAR POSITIVO na mesma conexão (o SELECT legítimo devolve as linhas) — senão um GRANT que negasse
    tudo passaria igual;
  * refutação: histórico de A invisível para B também NO BANCO (RLS), não só pela rota;
  * teto da listagem (`HISTORICO_LISTA_MAX`) aplicado de fato;
  * paginação obrigatória (refutação do adversário): 100 mil versões percorridas INTEIRAS por chaveset
    (`cursor`/`limite` no contrato OpenAPI), sem duplicar nem perder entrada, cursor inválido = 400;
  * "como era a camada em <data>" (o historicMoment do FeatureServer): contagem e geometria conferidas
    com o próprio histórico, com a feição apagada sumindo do retrato;
  * o diff campo a campo e da geometria (área/comprimento antes/depois, em metros via geography) que a
    tela consome com `dif=1` — medido numa camada de SRID geográfico (4674), onde o ST_Transform importa.

Reusa as fixtures de `tests/api/test_edicao_transacional.py` (mesma `FabricaCamada`), como o arquivo
vizinho de histórico/anexos já faz — nenhuma estrutura nova.
"""

from __future__ import annotations

import time

import pytest

from app.edicao import historico as mod_historico
from tests.api.test_edicao_transacional import (  # noqa: F401 — fixtures reaproveitadas
    _admin_usuario_id,
    _ponto,
    camada_a,
    camada_a_poligono,
    camada_b,
    fabrica,
)
from tests.api.test_rls import contexto, ids_por_slug


def _criar(sessao, camada_id, nome="um", lon=-46.1):
    r = sessao.post(
        f"/api/camadas/{camada_id}/edicoes",
        json={"adicionar": [{"atributos": {"nome": nome, "categoria": "A"}, "geometria": _ponto(lon)}]},
    )
    assert r.status_code == 200, r.text
    return r.json()["adicionar"][0]


def _contar_historico(con, tenant_id, usuario_id, schema, tabela) -> int:
    contexto(con, tenant_id, usuario_id=usuario_id, login="admin")
    with con.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM plat.feicao_historico WHERE schema_dado = %s AND tabela_dado = %s",
            (schema, tabela),
        )
        return cur.fetchone()["n"]


# ---------------------------------------------------------------- ciclo: editar, listar, restaurar
def test_editar_listar_versoes_e_restaurar_a_anterior_com_geometria(sessao_a, camada_a):  # noqa: F811
    """Cláusula "restaurar a versão 1 cria versão 4 igual à 1 (geometria E atributos)"."""
    f = _criar(sessao_a, camada_a["id"], nome="original", lon=-46.1)
    gid, versao = f["id"], f["versao"]

    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"atualizar": [{"id": gid, "versao": versao,
                             "atributos": {"nome": "mudado"}, "geometria": _ponto(-45.0)}]},
    )
    assert r.status_code == 200, r.text

    atual = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}").json()
    assert atual["atributos"]["nome"] == "mudado"
    assert atual["geometria"]["coordinates"][0] == pytest.approx(-45.0, abs=1e-6)

    versoes = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()["entradas"]
    assert [h["operacao"] for h in versoes] == ["atualizar", "inserir"], versoes
    insercao = versoes[-1]
    assert insercao["atributos_depois"]["nome"] == "original"
    assert insercao["geometria_depois"]["coordinates"][0] == pytest.approx(-46.1, abs=1e-6)

    r = sessao_a.post(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico/{insercao['id']}/restaurar")
    assert r.status_code == 200, r.text
    assert r.json()["recriada"] is False

    voltou = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}").json()
    assert voltou["atributos"]["nome"] == "original", voltou
    assert voltou["geometria"]["coordinates"][0] == pytest.approx(-46.1, abs=1e-6), voltou
    assert voltou["versao"] > atual["versao"], "restaurar é edição nova, nunca reescrita da versão anterior"

    # o histórico só CRESCE: as entradas antigas continuam lá, com o mesmo id
    depois = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()["entradas"]
    assert len(depois) == len(versoes) + 2  # 'atualizar' do gatilho + marcador 'restaurar'
    assert {h["id"] for h in versoes} <= {h["id"] for h in depois}


# ---------------------------------------------------------------- cláusula: lote de 1.000 pelo gatilho
def test_lote_de_mil_feicoes_gera_mil_linhas_de_historico_e_nao_dobra_o_tempo(
    sessao_a, camada_a, fabrica, conexao_plat_app, medida  # noqa: F811
):
    """Duas cláusulas numa medida só: (a) 1.000 feições em lote geram 1.000 linhas de histórico, contadas
    no banco; (b) o gatilho não faz o mesmo lote passar de 2x o tempo sem histórico. O "sem histórico" é
    medido de verdade, numa camada gêmea com `tg_historico` desligado — não é número de memória."""
    schema = camada_a["dados"]["schema"]
    tabela = camada_a["dados"]["tabela"]
    lote = {"adicionar": [{"atributos": {"nome": f"f{i}", "categoria": "A"},
                           "geometria": _ponto(-46.0 - i / 10000.0)} for i in range(1000)]}

    antes = _contar_historico(conexao_plat_app, camada_a["tenant_id"], camada_a["admin_id"], schema, tabela)
    t0 = time.monotonic()
    r = sessao_a.post(f"/api/camadas/{camada_a['id']}/edicoes", json=lote)
    com_gatilho = time.monotonic() - t0
    assert r.status_code == 200, r.text[:500]
    assert len(r.json()["adicionar"]) == 1000
    depois = _contar_historico(conexao_plat_app, camada_a["tenant_id"], camada_a["admin_id"], schema, tabela)
    assert depois - antes == 1000, f"gatilho gravou {depois - antes} linhas para 1.000 feições"

    # camada gêmea com o gatilho desligado (o dono da tabela é o mesmo papel da suíte)
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, dados = fabrica.criar(
        "demo", ids["demo"], admin_id,
        campos=[{"nome": "nome", "tipo": "text"}, {"nome": "categoria", "tipo": "text"}],
        geometria="Point",
    )
    contexto(conexao_plat_app, ids["demo"], usuario_id=admin_id, login="admin")
    with conexao_plat_app.cursor() as cur:
        try:
            cur.execute(f'ALTER TABLE "{dados["schema"]}"."{dados["tabela"]}" DISABLE TRIGGER tg_historico')
        except Exception as e:  # noqa: BLE001 — a mensagem real vale mais que o teste "passar"
            conexao_plat_app.rollback()
            pytest.skip(f"não foi possível desligar tg_historico para o par de comparação: {e}")
    conexao_plat_app.commit()

    t0 = time.monotonic()
    r2 = sessao_a.post(f"/api/camadas/{item_id}/edicoes", json=lote)
    sem_gatilho = time.monotonic() - t0
    assert r2.status_code == 200, r2.text[:500]
    assert _contar_historico(conexao_plat_app, ids["demo"], admin_id,
                             dados["schema"], dados["tabela"]) == 0

    gravar = medida("L2-03-d-historico-restauracao")
    gravar("lote_1000_com_historico_s", round(com_gatilho, 3), "s",
           "pytest tests/api/test_historico_feicao.py::"
           "test_lote_de_mil_feicoes_gera_mil_linhas_de_historico_e_nao_dobra_o_tempo")
    gravar("lote_1000_sem_historico_s", round(sem_gatilho, 3), "s", "mesma rodada, tg_historico desligado")
    gravar("razao_com_sem_historico", round(com_gatilho / sem_gatilho, 2), "x", "mesma rodada")
    assert com_gatilho < 2 * sem_gatilho, (
        f"gatilho custou {com_gatilho:.3f}s contra {sem_gatilho:.3f}s sem histórico "
        f"({com_gatilho / sem_gatilho:.2f}x, teto do portão: 2x)"
    )


# ---------------------------------------------------------------- refutação: histórico é append-only
def test_plat_app_le_e_insere_no_historico_mas_nunca_atualiza_nem_apaga(sessao_a, camada_a, conexao_plat_app):  # noqa: F811
    """Par completo: o SELECT legítimo TEM de devolver linha (senão um GRANT que negasse tudo passaria
    neste teste), e o UPDATE/DELETE direto como `plat_app` tem de falhar por privilégio — é o que torna
    o histórico append-only para quem edita.

    MEDIDO 17/09 e registrado em tests/medidas/L2-03-d-historico-restauracao.json: numa BASE DE TRILHA
    a segunda metade não é medível, porque `laco/trilha_ambiente.sh` (linha 252) faz
    `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA <schema da trilha>` para o papel de
    aplicação, por cima do `GRANT SELECT, INSERT` da migração 20260907T1025. O teste detecta isso pelo
    catálogo do próprio banco e SALTA dizendo o motivo, em vez de afrouxar a asserção — a garantia vale
    onde o schema nasce só das migrações (produção/homologação)."""
    f = _criar(sessao_a, camada_a["id"])
    schema, tabela = camada_a["dados"]["schema"], camada_a["dados"]["tabela"]
    contexto(conexao_plat_app, camada_a["tenant_id"], usuario_id=camada_a["admin_id"], login="admin")

    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT id FROM plat.feicao_historico WHERE schema_dado = %s AND tabela_dado = %s AND globalid = %s",
            (schema, tabela, f["id"]),
        )
        linhas = cur.fetchall()
    assert linhas, "par positivo: plat_app precisa LER o histórico da própria feição"
    hid = linhas[0]["id"]

    with conexao_plat_app.cursor() as cur:
        # uma linha por privilégio: `array_agg` volta como TEXTO por este cursor, e `set()` de texto
        # vira conjunto de LETRAS — o teste passaria sem nunca comparar privilégio nenhum (achado 17/09)
        cur.execute(
            "SELECT DISTINCT privilege_type AS p FROM information_schema.table_privileges "
            "WHERE table_name = 'feicao_historico' AND grantee = current_user"
        )
        concedidos = {r["p"] for r in cur.fetchall()}
    if {"UPDATE", "DELETE"} & concedidos:
        pytest.skip(
            "esta base concedeu "
            f"{sorted({'UPDATE', 'DELETE'} & concedidos)} em plat.feicao_historico ao papel de aplicação "
            "(GRANT em massa de laco/trilha_ambiente.sh, por cima do GRANT SELECT, INSERT da migração "
            "20260907T1025): o append-only só é medível onde o schema vem só das migrações"
        )

    for sql in (
        "UPDATE plat.feicao_historico SET atributos_depois = '{}'::jsonb WHERE id = %s",
        "DELETE FROM plat.feicao_historico WHERE id = %s",
    ):
        with pytest.raises(Exception) as excinfo:  # noqa: PT011 — a mensagem real é o que se registra
            with conexao_plat_app.cursor() as cur:
                cur.execute(sql, (hid,))
        assert "permission denied" in str(excinfo.value).lower(), str(excinfo.value)
        conexao_plat_app.rollback()
        contexto(conexao_plat_app, camada_a["tenant_id"], usuario_id=camada_a["admin_id"], login="admin")


def test_historico_de_a_invisivel_para_b_no_proprio_banco(sessao_a, camada_a, camada_b, conexao_plat_app):  # noqa: F811
    """A rota já é testada em test_edicao_historico_anexos.py; aqui a RLS da tabela, que é o que vale
    para qualquer outro caminho de leitura (relatório, job, exportação)."""
    f = _criar(sessao_a, camada_a["id"])


    contexto(conexao_plat_app, camada_a["tenant_id"], usuario_id=camada_a["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM plat.feicao_historico WHERE globalid = %s", (f["id"],)
        )
        do_dono = cur.fetchone()["n"]
    assert do_dono >= 1

    contexto(conexao_plat_app, camada_b["tenant_id"], usuario_id=camada_b["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.feicao_historico WHERE globalid = %s", (f["id"],))
        do_vizinho = cur.fetchone()["n"]
    assert do_vizinho == 0, "RLS deixou o inquilino B contar o histórico de uma feição de A"


# ---------------------------------------------------------------- teto da listagem / paginação
def test_tres_edicoes_produzem_tres_linhas_com_antes_depois_corretos(sessao_a, camada_a):  # noqa: F811
    """Cláusula literal do portão: 3 edições numa feição = 3 linhas de histórico, com o antes/depois de
    cada uma fechando a cadeia v0 → v1 → v2 → v3 (o 'depois' de uma é o 'antes' da seguinte)."""
    f = _criar(sessao_a, camada_a["id"], nome="v0")
    gid, versao = f["id"], f["versao"]
    for i in (1, 2, 3):
        r = sessao_a.post(
            f"/api/camadas/{camada_a['id']}/edicoes",
            json={"atualizar": [{"id": gid, "versao": versao, "atributos": {"nome": f"v{i}"}}]},
        )
        assert r.status_code == 200, r.text
        versao = r.json()["atualizar"][0]["versao"]

    hist = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()["entradas"]
    edicoes = [h for h in hist if h["operacao"] == "atualizar"]
    assert len(edicoes) == 3, edicoes
    cadeia = [(h["atributos_antes"]["nome"], h["atributos_depois"]["nome"]) for h in edicoes]
    assert cadeia == [("v2", "v3"), ("v1", "v2"), ("v0", "v1")], cadeia  # mais recente primeiro
    assert [h["versao"] for h in edicoes] == [4, 3, 2]


def test_listagem_respeita_o_teto_declarado(sessao_a, camada_a, monkeypatch):  # noqa: F811
    f = _criar(sessao_a, camada_a["id"], nome="v0")
    gid, versao = f["id"], f["versao"]
    for i in range(1, 6):
        r = sessao_a.post(
            f"/api/camadas/{camada_a['id']}/edicoes",
            json={"atualizar": [{"id": gid, "versao": versao, "atributos": {"nome": f"v{i}"}}]},
        )
        assert r.status_code == 200, r.text
        versao = r.json()["atualizar"][0]["versao"]

    sem_teto = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()["entradas"]
    assert len(sem_teto) == 6, sem_teto  # par positivo: sem teto baixo, vêm as 6 entradas

    monkeypatch.setattr(mod_historico, "HISTORICO_LISTA_MAX", 3)
    com_teto = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()["entradas"]
    assert len(com_teto) == 3, com_teto
    assert com_teto[0]["id"] == sem_teto[0]["id"], "o teto corta as MAIS ANTIGAS, nunca as mais recentes"


def test_paginacao_do_historico_esta_no_contrato(cliente):
    rota = cliente.app.openapi()["paths"]["/api/camadas/{id}/feicoes/{globalid}/historico"]["get"]
    nomes = {p["name"] for p in rota.get("parameters", [])}
    assert {"cursor", "limite"} <= nomes


def test_cursor_invalido_e_400_nunca_primeira_pagina(sessao_a, camada_a):  # noqa: F811
    f = _criar(sessao_a, camada_a["id"])
    r = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{f['id']}/historico?cursor=lixo")
    assert r.status_code == 400
    assert r.json()["erro"] == "cursor_invalido"


# ---------------------------------------------------------------- refutação: 100 mil versões
def test_historico_com_100_mil_versoes_se_percorre_inteiro_paginado(sessao_a, camada_a, conexao_plat_app):  # noqa: F811
    """A refutação do adversário, medida: 100.000 versões de UMA feição (inseridas direto na tabela de
    histórico — o que se prova é a LEITURA paginada, não o gatilho, já medido acima com o lote de 1.000),
    percorridas de ponta a ponta pelo chaveset: 100 páginas de 1.000, nenhuma entrada duplicada ou
    perdida, ordem estritamente da mais recente para a mais antiga, `total` exato em todas as páginas."""
    f = _criar(sessao_a, camada_a["id"])
    schema, tabela = camada_a["dados"]["schema"], camada_a["dados"]["tabela"]
    contexto(conexao_plat_app, camada_a["tenant_id"], usuario_id=camada_a["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "INSERT INTO plat.feicao_historico (tenant_id, schema_dado, tabela_dado, fid, globalid, operacao,"
            " versao, atributos_antes, atributos_depois, momento)"
            " SELECT plat.tenant_atual(), %s, %s, 1, %s, 'atualizar', g,"
            " jsonb_build_object('nome', 'v' || (g - 1)), jsonb_build_object('nome', 'v' || g),"
            " now() - (g || ' seconds')::interval FROM generate_series(1, 100000) g",
            (schema, tabela, f["id"]),
        )
    conexao_plat_app.commit()

    url = f"/api/camadas/{camada_a['id']}/feicoes/{f['id']}/historico"
    params: dict = {"limite": 1000}  # pede 1.000, recebe o teto da casa (HISTORICO_LISTA_MAX): o teto MANDA
    vistos: set[int] = set()
    paginas = 0
    momento_anterior = None
    teto = mod_historico.HISTORICO_LISTA_MAX
    while url:
        corpo = sessao_a.get(url, params=params).json()
        assert corpo.get("total") == 100001, f"total exato (100.000 + o 'inserir' da criação): {corpo}"
        entradas = corpo["entradas"]
        assert entradas, "página vazia no meio do percurso"
        assert len(entradas) <= teto, f"página com {len(entradas)} entradas, acima do teto {teto}"
        for e in entradas:
            assert e["id"] not in vistos, f"entrada {e['id']} apareceu em DUAS páginas"
            vistos.add(e["id"])
            if momento_anterior is not None:
                assert (e["momento"], e["id"]) < momento_anterior, "ordem quebrou na emenda das páginas"
            momento_anterior = (e["momento"], e["id"])
        paginas += 1
        proximo = corpo["proximo_cursor"]
        params = {"limite": 1000, "cursor": proximo} if proximo else None
        url = url if proximo else None
    esperado = -(-100001 // teto)  # páginas de no MÁXIMO `teto`, até a última entrada ficar alcançável
    assert paginas == esperado, paginas
    assert len(vistos) == 100001


# ---------------------------------------------------------------- "como era a camada em <data>"
def _agora(con):
    # clock_timestamp, NUNCA now(): a conexão da suíte fica dentro de UMA transação longa e now() congela
    # no início dela — os dois retratos (t0/t1) sairiam com o MESMO instante e o teste mediria nada.
    with con.cursor() as cur:
        cur.execute("SELECT clock_timestamp() AS agora")
        return cur.fetchone()["agora"]


def test_como_era_em_data_devolve_contagem_e_geometria_conferidas_com_o_historico(  # noqa: F811
    sessao_a, camada_a, conexao_plat_app
):
    fa = _criar(sessao_a, camada_a["id"], nome="a", lon=-46.10)
    fb = _criar(sessao_a, camada_a["id"], nome="b", lon=-46.20)
    fc = _criar(sessao_a, camada_a["id"], nome="c", lon=-46.30)
    t0 = _agora(conexao_plat_app)

    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"atualizar": [{"id": fa["id"], "versao": fa["versao"], "geometria": _ponto(-45.90)}]},
    )
    assert r.status_code == 200, r.text
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"apagar": [{"id": fb["id"], "versao": fb["versao"]}]},
    )
    assert r.status_code == 200, r.text
    t1 = _agora(conexao_plat_app)

    # retrato em t0: as três, com a geometria ORIGINAL de a — conferida com a entrada 'inserir' do histórico
    r0 = sessao_a.get(f"/api/camadas/{camada_a['id']}/como-era", params={"em": t0.isoformat()})
    assert r0.status_code == 200, r0.text
    corpo0 = r0.json()
    assert corpo0["total"] == 3, corpo0
    por_id = {x["id"]: x for x in corpo0["feicoes"]}
    assert set(por_id) == {fa["id"], fb["id"], fc["id"]}
    hist_a = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{fa['id']}/historico").json()["entradas"]
    insercao_a = [h for h in hist_a if h["operacao"] == "inserir"][0]
    assert por_id[fa["id"]]["geometria"] == insercao_a["geometria_depois"]
    assert por_id[fa["id"]]["geometria"]["coordinates"][0] == pytest.approx(-46.10, abs=1e-6)
    assert por_id[fb["id"]]["atributos"]["nome"] == "b"
    # os campos de rastreio (fid, tenant_id, criado_em...) NÃO vazam nos atributos do retrato
    assert "tenant_id" not in por_id[fa["id"]]["atributos"]
    assert "fid" not in por_id[fa["id"]]["atributos"]

    # retrato em t1: b sumiu (apagada), a aparece com a geometria NOVA — conferida com o 'atualizar'
    r1 = sessao_a.get(f"/api/camadas/{camada_a['id']}/como-era", params={"em": t1.isoformat()})
    corpo1 = r1.json()
    assert corpo1["total"] == 2, corpo1
    por_id1 = {x["id"]: x for x in corpo1["feicoes"]}
    assert fb["id"] not in por_id1
    atualizacao_a = [h for h in hist_a if h["operacao"] == "atualizar"][0]
    assert por_id1[fa["id"]]["geometria"] == atualizacao_a["geometria_depois"]
    assert por_id1[fa["id"]]["geometria"]["coordinates"][0] == pytest.approx(-45.90, abs=1e-6)

    # e o percurso paginado do retrato também anda (chaveset por globalid)
    r_pag = sessao_a.get(
        f"/api/camadas/{camada_a['id']}/como-era", params={"em": t0.isoformat(), "limite": 2}
    )
    pag = r_pag.json()
    assert len(pag["feicoes"]) == 2 and pag["total"] == 3 and pag["proximo_cursor"]
    r_pag2 = sessao_a.get(
        f"/api/camadas/{camada_a['id']}/como-era",
        params={"em": t0.isoformat(), "limite": 2, "cursor": pag["proximo_cursor"]},
    )
    pag2 = r_pag2.json()
    assert len(pag2["feicoes"]) == 1 and pag2["proximo_cursor"] is None
    ids = {x["id"] for x in pag["feicoes"]} | {x["id"] for x in pag2["feicoes"]}
    assert ids == {fa["id"], fb["id"], fc["id"]}


def test_como_era_de_camada_de_outro_inquilino_e_404(sessao_b, camada_a):  # noqa: F811
    r = sessao_b.get(f"/api/camadas/{camada_a['id']}/como-era", params={"em": "2026-01-01T00:00:00Z"})
    assert r.status_code == 404


def test_como_era_exige_data_valida(sessao_a, camada_a):  # noqa: F811
    r = sessao_a.get(f"/api/camadas/{camada_a['id']}/como-era", params={"em": "lixo"})
    assert r.status_code == 422


# ---------------------------------------------------------------- diff campo a campo e da geometria (dif=1)
def _anel(cx, cy, lado):
    m = lado / 2
    return [[cx - m, cy - m], [cx + m, cy - m], [cx + m, cy + m], [cx - m, cy + m], [cx - m, cy - m]]


def test_dif_campo_a_campo_e_da_geometria_em_metros(sessao_a, camada_a_poligono):  # noqa: F811
    """O diff que a tela consome: atributo que mudou marcado, atributo intacto não marcado, e a geometria
    com área antes/depois em m² (camada em SRID 4674 — geográfico —, onde ler o grau como metro daria
    erro de ordem de grandeza; o valor tem de ser o da geography, conferido na ordem de magnitude)."""
    r = sessao_a.post(
        f"/api/camadas/{camada_a_poligono['id']}/edicoes",
        json={"adicionar": [{"atributos": {"nome": "antes"},
                             "geometria": {"type": "Polygon", "coordinates": [_anel(-46.0, -23.5, 0.01)]}}]},
    )
    assert r.status_code == 200, r.text
    f = r.json()["adicionar"][0]
    r = sessao_a.post(
        f"/api/camadas/{camada_a_poligono['id']}/edicoes",
        json={"atualizar": [{"id": f["id"], "versao": f["versao"], "atributos": {"nome": "depois"},
                             "geometria": {"type": "Polygon", "coordinates": [_anel(-46.0, -23.5, 0.02)]}}]},
    )
    assert r.status_code == 200, r.text

    corpo = sessao_a.get(
        f"/api/camadas/{camada_a_poligono['id']}/feicoes/{f['id']}/historico?dif=1"
    ).json()
    edicao = [h for h in corpo["entradas"] if h["operacao"] == "atualizar"][0]
    da = edicao["dif"]["atributos"]
    assert da["nome"] == {"antes": "antes", "depois": "depois", "mudou": True}
    # os campos de rastreio (versao, atualizado_em...) mudam em TODA escrita: não entram no diff
    assert "versao" not in da and "atualizado_em" not in da and "tenant_id" not in da

    dg = edicao["dif"]["geometria"]
    assert dg["mudou"] is True
    # quadrado de ~0,01° de lado na latitude -23,5 ≈ 1,1 km²; o de 0,02° ≈ 4x mais
    assert dg["area_antes_m2"] == pytest.approx(1.13e6, rel=0.15), dg
    assert dg["area_depois_m2"] == pytest.approx(4.5e6, rel=0.15), dg
    assert dg["area_depois_m2"] > dg["area_antes_m2"]

    # sem dif=1 a resposta NÃO carrega o custo nem a chave (a listagem comum continua enxuta)
    sem = sessao_a.get(f"/api/camadas/{camada_a_poligono['id']}/feicoes/{f['id']}/historico").json()
    assert all("dif" not in h for h in sem["entradas"])


def test_dif_geometria_intacta_marcada_como_nao_mudou(sessao_a, camada_a):  # noqa: F811
    f = _criar(sessao_a, camada_a["id"], nome="parado", lon=-46.1)
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"atualizar": [{"id": f["id"], "versao": f["versao"], "atributos": {"nome": "andou"}}]},
    )
    assert r.status_code == 200, r.text
    corpo = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{f['id']}/historico?dif=1").json()
    edicao = [h for h in corpo["entradas"] if h["operacao"] == "atualizar"][0]
    assert edicao["dif"]["geometria"]["mudou"] is False
    # ponto: área/comprimento são 0 em qualquer SRID — mas têm de VIR (a tela não trata exceção)
    assert edicao["dif"]["geometria"]["area_antes_m2"] == 0
    assert edicao["dif"]["geometria"]["comprimento_depois_m"] == 0


# -------------------------------- append-only no ARTEFATO que é entregue (as migrações), sem depender da base
def test_as_migracoes_nunca_dao_update_nem_delete_do_historico_ao_papel_de_aplicacao(medida):
    """Complemento de `test_plat_app_le_e_insere_no_historico_mas_nunca_atualiza_nem_apaga`, que SALTA nas
    bases de trilha (o `GRANT` em massa de `laco/trilha_ambiente.sh` dá UPDATE/DELETE por cima do da
    migração). Aqui a mesma cláusula é medida onde ela é decidida para uma instalação de verdade: o texto
    das migrações, que é o que roda no cliente.

    Par positivo obrigatório: a mesma varredura TEM de achar o `GRANT SELECT, INSERT` — sem isso, uma
    varredura quebrada (regex errada, diretório errado) não acharia nada e o teste passaria por engano."""
    import re
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2] / "db" / "migracoes"
    grants = []
    for arquivo in sorted(raiz.glob("*.sql")):
        texto = arquivo.read_text(encoding="utf-8")
        for m in re.finditer(r"GRANT\s+([A-Z,\s]+?)\s+ON\s+(?:TABLE\s+)?plat\.feicao_historico\s+TO\s+(\w+)",
                             texto, re.IGNORECASE):
            privilegios = {p.strip().upper() for p in m.group(1).split(",")}
            grants.append((arquivo.name, privilegios, m.group(2)))

    assert grants, f"nenhum GRANT sobre plat.feicao_historico achado em {raiz}: a varredura é que está errada"
    para_app = [g for g in grants if g[2].lower() == "plat_app"]
    assert para_app, [g[2] for g in grants]
    for nome, privilegios, _ in para_app:
        assert privilegios == {"SELECT", "INSERT"}, (nome, sorted(privilegios))
        assert not ({"UPDATE", "DELETE", "TRUNCATE", "ALL"} & privilegios), (nome, sorted(privilegios))

    medida("L2-03-d-historico-restauracao")(
        "grants_do_historico_nas_migracoes",
        sorted({f"{g[2]}:{'+'.join(sorted(g[1]))}" for g in grants}),
        "papel:privilégios concedidos sobre plat.feicao_historico em db/migracoes",
        "pytest tests/api/test_historico_feicao.py::"
        "test_as_migracoes_nunca_dao_update_nem_delete_do_historico_ao_papel_de_aplicacao")
