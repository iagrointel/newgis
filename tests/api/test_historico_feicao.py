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
  * teto da listagem (`HISTORICO_LISTA_MAX`) aplicado de fato, e a falta de paginação registrada como
    `xfail` (a cláusula "paginação obrigatória" do item NÃO está implementada — a rota não tem cursor
    nem deslocamento; ver `test_paginacao_do_historico_ainda_nao_existe`).

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

    versoes = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()
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
    depois = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()
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

    sem_teto = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()
    assert len(sem_teto) == 6, sem_teto  # par positivo: sem teto baixo, vêm as 6 entradas

    monkeypatch.setattr(mod_historico, "HISTORICO_LISTA_MAX", 3)
    com_teto = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/historico").json()
    assert len(com_teto) == 3, com_teto
    assert com_teto[0]["id"] == sem_teto[0]["id"], "o teto corta as MAIS ANTIGAS, nunca as mais recentes"


@pytest.mark.xfail(
    strict=True,
    reason="cláusula 'paginação obrigatória' do portão L2-03-d NÃO está implementada: "
           "GET /api/camadas/{id}/feicoes/{globalid}/historico não aceita cursor nem deslocamento; "
           "quem tiver mais de HISTORICO_LISTA_MAX versões perde as antigas sem saber que perdeu",
)
def test_paginacao_do_historico_ainda_nao_existe(cliente):
    rota = cliente.app.openapi()["paths"]["/api/camadas/{id}/feicoes/{globalid}/historico"]["get"]
    nomes = {p["name"] for p in rota.get("parameters", [])}
    assert nomes & {"cursor", "pagina", "deslocamento", "offset", "limite"}
