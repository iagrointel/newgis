"""Portão do item L2-10-d-regras-de-atributo, contra a API real da trilha:
  1. regra de cálculo dispara na edição e preenche o campo (valor igual ao esperado);
  2. regra de restrição recusa com a mensagem e o código configurados;
  3. validação de 100 mil feições como job produz N erros conferidos com SQL;
  4. campo virtual aparece na leitura de feições (o "FeatureServer/popup" da casa hoje) com o valor certo;
  5. regra desabilitada não dispara;  6. ordem de duas regras encadeadas respeitada;
  7. tempo de 1.000 edições com 3 regras <= 2x sem regras (medido);
Refutação: regra que muda o próprio campo gatilho (ciclo, 422 na configuração); custo em 1 mi de feições (medido
por extrapolação linear do lote de 100 mil, declarado); edição pelo WFS Transaction — NÃO EXISTE WFS-T em master
(pulado com a razão), a regra vale para todo caminho porque todo caminho passa por app/edicao/servico.

A camada de teste é criada direto no banco pela mesma `FabricaCamada` de test_edicao_transacional.py."""

from __future__ import annotations

import fcntl
import time
from contextlib import nullcontext
from pathlib import Path

import psycopg2.errors
import pytest

from tests.api.jobs.conftest import WorkerExtra, esperar
from tests.api.test_edicao_transacional import FabricaCamada, _admin_usuario_id, _ponto
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L2-10-d-regras-de-atributo"
CAMPOS = [{"nome": "nome", "tipo": "text"}, {"nome": "largura", "tipo": "double precision"},
          {"nome": "altura", "tipo": "double precision"}, {"nome": "area", "tipo": "double precision"},
          {"nome": "classe", "tipo": "text"}]
REGRAS = [
    {"id": "area", "tipo": "calculo", "campo": "area", "expressao": "$largura * $altura",
     "gatilhos": ["largura", "altura"], "ordem": 1, "nome": "área = largura x altura"},
    {"id": "classe", "tipo": "calculo", "campo": "classe", "expressao": "Se($area > 100, 'grande', 'pequena')",
     "gatilhos": ["area"], "ordem": 2},
    {"id": "positivo", "tipo": "restricao", "expressao": "$largura > 0 && $altura > 0", "codigo": "medida_invalida",
     "mensagem": "largura e altura precisam ser maiores que zero"},
    {"id": "nome_ok", "tipo": "validacao", "expressao": "!EhNulo($nome) && Contagem($nome) >= 3",
     "codigo": "nome_curto", "mensagem": "nome com menos de 3 caracteres"},
]
VIRTUAIS = [{"nome": "area_m2", "expressao": "$area * 10000", "alias": "área em m²"}]


@pytest.fixture
def fabrica(conexao_plat_app):
    f = FabricaCamada(conexao_plat_app)
    yield f
    # a camada de erros (tabela e_ + item) que o job cria fica fora da lista da fábrica: limpa aqui
    con = conexao_plat_app
    for schema, _tabela, item_id in list(f.criadas):
        with con.cursor() as cur:
            cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (item_id,))
            r = cur.fetchone()
            val = ((r or {}).get("dados") or {}).get("validacao") or {}
            if val.get("tabela_erros"):
                cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{val["tabela_erros"]}" CASCADE')
            if val.get("item_erros_id"):
                cur.execute("DELETE FROM plat.item WHERE id = %s::uuid", (val["item_erros_id"],))
    con.commit()
    f.limpar()


@pytest.fixture
def camada(fabrica, conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    # `plat.camada_schema_garantir` faz GRANT em d_demo; trilhas construídas ao mesmo tempo fazem o mesmo GRANT nas
    # migrações e o Postgres responde "tuple concurrently updated". Os construtores serializam pelo trinco
    # laco/var/.trilha_build.lock; a fixture entra no mesmo trinco só para criar a camada (ambiente, não o item).
    trinco = Path("/home/dev/plataforma/laco/.trilha_build.lock")
    for tentativa in range(6):  # trilhas que rodam testes fazem o mesmo GRANT sem o trinco: retentativa por cima
        try:
            with open(trinco, "a+") if trinco.parent.is_dir() else nullcontext() as f:
                if f is not None:
                    fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    item_id, dados = fabrica.criar("demo", ids["demo"], admin_id, campos=CAMPOS, geometria="Point")
                finally:
                    if f is not None:
                        fcntl.flock(f, fcntl.LOCK_UN)
            break
        except psycopg2.errors.InternalError_ as e:
            conexao_plat_app.rollback()
            if "concurrently" not in str(e) or tentativa == 5:
                raise
            time.sleep(2 + tentativa)
    return {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id, "schema": dados["schema"],
            "tabela": dados["tabela"]}


def _definir(sessao, cid, regras=REGRAS, virtuais=VIRTUAIS):
    r = sessao.put(f"/api/camadas/{cid}/regras", json={"regras": regras, "campos_virtuais": virtuais})
    assert r.status_code == 200, r.text
    return r.json()


def _editar(sessao, cid, corpo):
    return sessao.post(f"/api/camadas/{cid}/edicoes", json=corpo)


def _adicionar(largura, altura, nome="ok"):
    return {"atributos": {"nome": nome, "largura": largura, "altura": altura}, "geometria": _ponto()}


# ---------------------------------------------------------------- 1, 6: cálculo dispara, encadeado, na ordem
def test_calculo_dispara_na_edicao_e_encadeia_na_ordem(sessao_a, camada, fabrica, medida):
    saida = _definir(sessao_a, camada["id"])
    assert saida["ordem_de_avaliacao"] == ["positivo", "nome_ok", "area", "classe"]
    r = _editar(sessao_a, camada["id"], {"adicionar": [_adicionar(20, 10), _adicionar(2, 3)]})
    assert r.status_code == 200, r.text
    res = r.json()["adicionar"]
    assert res[0]["atributos"]["area"] == 200 and res[0]["atributos"]["classe"] == "grande"
    assert res[1]["atributos"]["area"] == 6 and res[1]["atributos"]["classe"] == "pequena"
    lidas = fabrica.linhas(camada["schema"], camada["tabela"], camada["tenant_id"], camada["admin_id"])
    linhas = {li["fid"]: li for li in lidas}
    assert linhas[res[0]["fid"]]["area"] == 200 and linhas[res[0]["fid"]]["classe"] == "grande"
    # atualizar só a altura dispara `area` (gatilho) e, em cadeia, `classe` (gatilho no campo calculado)
    r = _editar(sessao_a, camada["id"], {"atualizar": [{"id": res[1]["id"], "versao": res[1]["versao"],
                                                      "atributos": {"altura": 100}}]})
    assert r.status_code == 200, r.text
    upd = r.json()["atualizar"][0]
    assert upd["atributos"] == {"altura": 100, "area": 200, "classe": "grande"}
    # atualizar só o nome não dispara nada: area/classe ficam
    r = _editar(sessao_a, camada["id"], {"atualizar": [{"id": res[1]["id"], "versao": upd["versao"],
                                                      "atributos": {"nome": "renomeado"}}]})
    assert r.status_code == 200 and r.json()["atualizar"][0]["atributos"] == {"nome": "renomeado"}
    medida(ITEM)("ordem_encadeada_respeitada", True, "bool",
                 "area (ordem 1) -> classe (ordem 2), gatilho no campo calculado")


# ---------------------------------------------------------------- 2: restrição recusa com código e mensagem
def test_restricao_recusa_com_codigo_e_mensagem_e_transacao_desfaz(sessao_a, camada, fabrica):
    _definir(sessao_a, camada["id"])
    r = _editar(sessao_a, camada["id"], {"adicionar": [_adicionar(5, 5), _adicionar(-1, 5)]})
    assert r.status_code == 422, r.text
    j = r.json()
    assert j["erro"] == "medida_invalida" and j["mensagem"] == "largura e altura precisam ser maiores que zero"
    assert j["detalhe"]["regra"] == "positivo"
    assert fabrica.linhas(camada["schema"], camada["tabela"], camada["tenant_id"], camada["admin_id"]) == []
    # modo parcial: a feição ruim volta com o código, a boa entra
    r = _editar(sessao_a, camada["id"], {"modo": "parcial", "adicionar": [_adicionar(5, 5), _adicionar(0, 5)]})
    assert r.status_code == 200, r.text
    res = r.json()["adicionar"]
    assert res[0]["sucesso"] is True and res[1]["sucesso"] is False and res[1]["erro"] == "medida_invalida"


# ---------------------------------------------------------------- 5: desabilitada não dispara; exclusão em massa
def test_regra_desabilitada_nao_dispara_e_em_massa_exclui(sessao_a, camada):
    regras = [dict(REGRAS[0], habilitada=False), dict(REGRAS[2], excluir_em_massa=True)]
    _definir(sessao_a, camada["id"], regras=regras, virtuais=[])
    r = _editar(sessao_a, camada["id"], {"adicionar": [_adicionar(20, 10)]})
    assert r.status_code == 200 and "area" not in r.json()["adicionar"][0]["atributos"], r.text
    # restrição vale no lote comum...
    assert _editar(sessao_a, camada["id"], {"adicionar": [_adicionar(-1, 10)]}).status_code == 422
    # ...e é pulada quando o cliente marca importação em massa
    r = _editar(sessao_a, camada["id"], {"em_massa": True, "adicionar": [_adicionar(-1, 10)]})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- 4: campo virtual na leitura
def test_campo_virtual_aparece_na_leitura_com_o_valor_certo(sessao_a, camada):
    _definir(sessao_a, camada["id"])
    r = _editar(sessao_a, camada["id"], {"adicionar": [_adicionar(2.5, 4)]})
    assert r.status_code == 200, r.text
    fid = r.json()["adicionar"][0]["fid"]
    r = sessao_a.get(f"/api/camadas/{camada['id']}/feicoes", params={"fid": fid})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["total"] == 1 and j["campos_virtuais"] == ["area_m2"]
    f = j["itens"][0]
    assert f["atributos"]["area"] == 10 and f["atributos"]["area_m2"] == 100000
    assert f["geometria"]["type"] == "Point"
    # campo virtual nunca é gravado: não existe coluna na tabela nem é aceito na edição
    virtual_como_atributo = {"atributos": {"area_m2": 1, "largura": 1, "altura": 1}, "geometria": _ponto()}
    r = _editar(sessao_a, camada["id"], {"adicionar": [virtual_como_atributo]})
    assert r.status_code == 422 and r.json()["erro"] == "campo_inexistente"


# ---------------------------------------------------------------- refutação: ciclo e configuração inválida
def test_adversario_regra_que_muda_o_proprio_gatilho_e_recusada_na_configuracao(sessao_a, camada):
    ciclo = [{"id": "x", "tipo": "calculo", "campo": "area", "expressao": "$area + 1", "gatilhos": ["area"]}]
    r = sessao_a.put(f"/api/camadas/{camada['id']}/regras", json={"regras": ciclo})
    assert r.status_code == 422 and r.json()["erro"] == "regra_ciclo", r.text
    cadeia = [{"id": "x", "tipo": "calculo", "campo": "area", "expressao": "$largura + 1", "gatilhos": ["largura"]},
              {"id": "y", "tipo": "calculo", "campo": "largura", "expressao": "$area + 1", "gatilhos": ["area"]}]
    r = sessao_a.put(f"/api/camadas/{camada['id']}/regras", json={"regras": cadeia})
    assert r.status_code == 422 and r.json()["erro"] == "regra_ciclo", r.text
    assert r.json()["detalhe"]["ciclo"] == ["x", "y", "x"]
    # nada gravado: GET continua vazio; e o mesmo ciclo por PATCH /api/itens (dados inteiro) também é recusado
    assert sessao_a.get(f"/api/camadas/{camada['id']}/regras").json()["regras"] == []
    dados = {**camada["dados"], "regras": ciclo}
    r = sessao_a.patch(f"/api/itens/{camada['id']}", json={"dados": dados})
    assert r.status_code == 422 and r.json()["erro"] == "regra_ciclo", r.text
    r = sessao_a.put(f"/api/camadas/{camada['id']}/regras",
                     json={"regras": [{"id": "z", "tipo": "restricao", "expressao": "$inexistente > 1"}]})
    assert r.status_code == 422 and r.json()["erro"] == "regra_campo_inexistente"


# ---------------------------------------------------------------- 3: validação de 100 mil como job
def _semear(con, camada, n: int, cada_k_ruim: int):
    """n feições direto no banco (1 em cada `cada_k_ruim` com nome curto -> erro da regra nome_ok)."""
    contexto(con, camada["tenant_id"], usuario_id=camada["admin_id"], login="admin")
    with con.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{camada["schema"]}"."{camada["tabela"]}" (nome, largura, altura, area, geom) '
            f"SELECT CASE WHEN g %% %s = 0 THEN 'ab' ELSE 'nome ' || g END, 1, 1, 1, "
            f"ST_SetSRID(ST_MakePoint(-46.5 + (g %% 1000) * 0.0001, -23.5 + (g / 1000) * 0.0001), 4674) "
            f"FROM generate_series(1, %s) g",
            (cada_k_ruim, n),
        )
    con.commit()


@pytest.fixture
def worker_extra(env):
    w = WorkerExtra(env, "regras-teste", porta=8931)
    yield w
    w.proc.terminate()
    try:
        w.proc.wait(timeout=10)
    except Exception:  # noqa: BLE001 — encerramento de processo de teste
        w.proc.kill()


def test_validacao_de_100_mil_feicoes_como_job_produz_n_erros_conferidos_com_sql(
    sessao_a, camada, conexao_plat_app, worker_extra, medida
):
    n, cada = 100_000, 7
    _semear(conexao_plat_app, camada, n, cada)
    _definir(sessao_a, camada["id"])
    r = sessao_a.post(f"/api/camadas/{camada['id']}/validar")
    assert r.status_code == 201, r.text
    job_id = r.json()["job_id"]
    t0 = time.perf_counter()
    job = esperar(sessao_a, job_id, timeout=600)
    dt = time.perf_counter() - t0
    assert job["estado"] == "concluido", job
    resumo = job["resultado"]
    esperado = n // cada
    assert resumo["n_feicoes"] == n and resumo["n_erros"] == esperado, resumo
    # conferido com SQL: a tabela e_ tem exatamente as feições de nome curto
    con = conexao_plat_app
    contexto(con, camada["tenant_id"], usuario_id=camada["admin_id"], login="admin")
    with con.cursor() as cur:
        erros_t = f'"{camada["schema"]}"."{resumo["tabela_erros"]}"'
        camada_t = f'"{camada["schema"]}"."{camada["tabela"]}"'
        cur.execute(f"SELECT count(*) AS n, count(DISTINCT feicao_fid) AS f FROM {erros_t}")
        e = cur.fetchone()
        cur.execute(f"SELECT count(*) AS n FROM {camada_t} WHERE length(nome) < 3")
        ruins = cur.fetchone()["n"]
        cur.execute(f"SELECT count(*) AS n FROM {erros_t} e JOIN {camada_t} c ON c.fid = e.feicao_fid "
                    "WHERE length(c.nome) >= 3")
        falsos = cur.fetchone()["n"]
    assert e["n"] == esperado == ruins and e["f"] == esperado and falsos == 0
    # camada de erros visível no catálogo (item camada_vetorial com geometria e a tabela e_)
    r = sessao_a.get(f"/api/itens/{resumo['item_erros_id']}")
    assert r.status_code == 200 and r.json()["tipo"] == "camada_vetorial", r.text
    dados_erros = r.json()["dados"]
    assert dados_erros["tabela"] == resumo["tabela_erros"] and dados_erros["procedencia"]["camada_id"] == camada["id"]
    r = sessao_a.get(f"/api/camadas/{camada['id']}/erros", params={"limite": 5})
    assert r.status_code == 200 and r.json()["total"] == esperado and r.json()["itens"][0]["codigo"] == "nome_curto"
    assert sessao_a.get(f"/api/camadas/{camada['id']}/regras").json()["validacao"]["n_erros"] == esperado
    m = medida(ITEM)
    m("validacao_100k_feicoes_s", round(dt, 2), "s",
      "POST /api/camadas/{id}/validar -> job camadas.validar concluído (1 regra, 100 mil feições)")
    m("validacao_100k_duracao_job_s", resumo["duracao_s"], "s", "resultado.duracao_s do job (só a varredura)")
    m("validacao_100k_erros", resumo["n_erros"], "erros", f"1 a cada {cada} feições com nome curto; conferido por SQL")
    m("custo_extrapolado_1mi_s", round(resumo["duracao_s"] * 10, 1), "s",
      "adversário: 1 mi de feições = 10x o lote de 100 mil (varredura linear por cursor; sem medir 1 mi nesta trilha)")


# ---------------------------------------------------------------- 7: 1.000 edições com 3 regras <= 2x sem regras
def test_tempo_de_mil_edicoes_com_tres_regras(sessao_a, camada, medida):
    lote = [_adicionar(3, 4, nome=f"n{i}") for i in range(500)]

    def rodar():
        t0 = time.perf_counter()
        for _ in range(2):
            r = _editar(sessao_a, camada["id"], {"adicionar": lote})
            assert r.status_code == 200, r.text[:300]
        return time.perf_counter() - t0

    sem = min(rodar() for _ in range(2))
    _definir(sessao_a, camada["id"], regras=REGRAS[:3], virtuais=[])
    com = min(rodar() for _ in range(2))
    razao = com / sem
    m = medida(ITEM)
    m("mil_edicoes_sem_regras_s", round(sem, 3), "s", "2 x POST /edicoes com 500 feições, melhor de 2")
    m("mil_edicoes_com_3_regras_s", round(com, 3), "s", "idem com 2 cálculos encadeados + 1 restrição")
    m("razao_com_sobre_sem", round(razao, 3), "x", "portão: <= 2")
    assert razao <= 2.0, (sem, com, razao)


def test_regras_valem_por_qualquer_caminho_wfs_t_pendente():
    pytest.skip("não existe WFS Transaction em master (L2-04); toda escrita passa por app/edicao/servico, onde a regra "
                "roda — quando o WFS-T entrar, chamará aplicar_edicoes e herdará as regras sem código novo")
