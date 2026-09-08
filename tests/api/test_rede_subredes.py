"""Atualizar e exportar subrede (item L4-04-b-atualizar-e-exportar-subrede).

Cláusulas do portão provadas aqui (as duas de ESCALA — tempo da cooperativa inteira e concordância ≥ 99 %
entre o nome da subrede e o CTMT do arquivo — estão em `test_rede_subredes_medida.py`, marcador `lento`;
o e2e do botão em `tests/e2e/test_rede_subredes.py`):

* atualizar grava o nome da subrede em cada elemento, propaga os atributos declarados no tier e gera a linha
  agregada (SubnetLine) — `test_atualizar_grava_nome_propaga_e_gera_a_linha`;
* incremental por área suja: mover uma chave de fronteira entre dois alimentadores suja SÓ as 2 subredes
  tocadas, e o lote atualiza só essas — `test_mover_chave_de_fronteira_suja_so_as_duas_subredes`;
* `GET .../subrede/{nome}/exportar` devolve JSON validado pelo esquema e com Σ elementos igual ao traçado de
  subrede, elemento a elemento — `test_exportar_valida_no_esquema_e_bate_com_o_tracado`;
* a atualização em lote é JOB — `test_atualizar_em_lote_enfileira_job`;
* conferência do nome contra o atributo do arquivo — `test_conferencia_contra_o_ctmt_do_arquivo`.

Refutação (papel adversário), provada aqui:
* `test_exportar_subrede_nunca_atualizada_e_recusado`: exportar sem atualização não devolve um JSON vazio
  fingindo subrede — recusa com 409;
* `test_exportar_nome_repetido_em_dois_tiers_e_ambiguo`: nome de subrede é único no tier, não na rede;
* `test_propagador_fora_do_pacote_e_recusado`: propagar atributo que o pacote não declara é recusado;
* `test_atualizar_desfaz_a_associacao_antiga`: elemento que saiu da subrede perde a associação (não fica
  membro de duas subredes ao mesmo tempo)."""

import pytest
from jsonschema import Draft202012Validator

from app.rede_utilidades.esquema_exportacao import ESQUEMA
from tests.api.conftest import PREFIXO_TESTE

ITEM = "L4-04-b-atualizar-e-exportar-subrede"

CTMT_A = "1_SUB_1"
CTMT_B = "2_SUB_1"
CTMT_C = "3_SUB_1"
SUB = "SUB"
DISJUNTOR = 4  # tipo `disjuntor` do grupo chave_de_media_tensao (pacote eletrica-br)


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _criar_rede(sessao, sufixo, limpar):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-sub-{sufixo}", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append(rid)
    from app.rede_utilidades import instalados

    r = sessao.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    return rid


def _linha(sessao, rid, coordenadas, grupo, tipo_codigo=1, atributos=None):
    corpo = {"tipo_codigo": tipo_codigo, "grupo": grupo, "coordenadas": coordenadas}
    if atributos:
        corpo["atributos"] = atributos
    r = sessao.post(f"/api/rede/{rid}/feicoes/linhas", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _ponto(sessao, rid, lon, lat, grupo, tipo_codigo=1, atributos=None):
    corpo = {"tipo_codigo": tipo_codigo, "grupo": grupo, "lon": lon, "lat": lat}
    if atributos:
        corpo["atributos"] = atributos
    r = sessao.post(f"/api/rede/{rid}/feicoes/pontos", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _habilitar(sessao, rid):
    r = sessao.post(f"/api/rede/{rid}/topologia/habilitar")
    assert r.status_code == 201, r.text
    return r.json()


def _subredes(sessao, rid):
    r = sessao.get(f"/api/rede/{rid}/subredes?limite=500")
    assert r.status_code == 200, r.text
    return {s["nome"]: s for s in r.json()["itens"]}


def _rede_tres_alimentadores(sessao, rid, lon0=34.0, lat0=14.0):
    """Três alimentadores de média tensão, cada um com o disjuntor de saída, bem separados entre si, e um
    transformador de distribuição no fim do primeiro (fronteira de subrede: o tier de baixa tensão começa
    ali). Distância entre alimentadores: 0,02 grau ≈ 2,2 km — longe demais para a área suja de um alcançar
    a linha do outro por acidente."""
    d, salto = 0.001, 0.02
    feicoes = {}
    for i, ctmt in enumerate((CTMT_A, CTMT_B, CTMT_C)):
        base_lat = lat0 + i * salto
        a = (lon0, base_lat)
        b = (lon0 + d, base_lat)
        c = (lon0 + 2 * d, base_lat)
        at = {"ctmt": ctmt, "sub": SUB}
        feicoes[f"disjuntor_{ctmt}"] = _ponto(sessao, rid, *a, "chave_de_media_tensao", DISJUNTOR,
                                              atributos={**at, "unsemt_fas_con": "ABC"})
        feicoes[f"mt1_{ctmt}"] = _linha(sessao, rid, [list(a), list(b)], "trecho_de_media_tensao",
                                        atributos={**at, "cod_id": f"MT1-{ctmt}"})
        feicoes[f"mt2_{ctmt}"] = _linha(sessao, rid, [list(b), list(c)], "trecho_de_media_tensao",
                                        atributos={**at, "cod_id": f"MT2-{ctmt}"})
        feicoes[f"meio_{ctmt}"] = b
        feicoes[f"fim_{ctmt}"] = c
    c = feicoes[f"fim_{CTMT_A}"]
    feicoes["trafo"] = _ponto(sessao, rid, *c, "transformador_de_distribuicao", 1,
                              atributos={"cod_id": "TR-SUB"})
    feicoes["bt"] = _linha(sessao, rid, [list(c), [c[0], c[1] + d]], "trecho_de_baixa_tensao",
                           atributos={"cod_id": "BT-SUB"})
    _habilitar(sessao, rid)
    r = sessao.post(f"/api/rede/{rid}/controladores/importar")
    assert r.status_code == 200, r.text
    assert r.json()["alimentadores_por_dispositivo"] == 3, r.text
    return feicoes


# --- cláusula: atualizar grava nome, propaga e gera a linha ---------------------------------------------

def test_atualizar_grava_nome_propaga_e_gera_a_linha(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "atualizar", limpar_redes)
    _rede_tres_alimentadores(sessao_a, rid)

    r = sessao_a.put(f"/api/rede/{rid}/tier/media_tensao/propagadores",
                     json={"propagadores": ["unsemt_fas_con"]})
    assert r.status_code == 200, r.text
    assert r.json()["propagadores"] == ["unsemt_fas_con"]

    alvo = _subredes(sessao_a, rid)[CTMT_A]
    assert alvo["estado"] == "suja"
    r = sessao_a.post(f"/api/rede/{rid}/subredes/{alvo['id']}/atualizar")
    assert r.status_code == 200, r.text
    saida = r.json()
    resumo = saida["resumo"]
    assert saida["estado"] == "limpa"
    assert resumo["trechos"] == 2, "os dois trechos de MT do alimentador A"
    assert resumo["elementos"] == resumo["trechos"] + resumo["terminais"]
    assert resumo["comprimento_m"] > 0 and resumo["partes_da_linha"] >= 1
    assert saida["linha"]["type"] == "MultiLineString"
    assert resumo["propagados"] == {"unsemt_fas_con": "ABC"}, resumo

    depois = _subredes(sessao_a, rid)
    assert depois[CTMT_A]["estado"] == "limpa"
    assert depois[CTMT_B]["estado"] == "suja", "atualizar uma subrede não limpa as outras"

    exportado = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT_A}/exportar")
    assert exportado.status_code == 200, exportado.text
    trechos = [e for e in exportado.json()["elementos"] if e["geometria"] == "linha"]
    assert len(trechos) == 2
    assert all(e["propagados"] == {"unsemt_fas_con": "ABC"} for e in trechos), trechos


def test_propagador_fora_do_pacote_e_recusado(sessao_a, limpar_redes):
    """Refutação: propagar uma chave que o pacote não declara escreveria atributo que ninguém sabe ler."""
    rid = _criar_rede(sessao_a, "propagador-ruim", limpar_redes)
    _rede_tres_alimentadores(sessao_a, rid)
    r = sessao_a.put(f"/api/rede/{rid}/tier/media_tensao/propagadores",
                     json={"propagadores": ["nao_existe_no_pacote"]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "atributo_desconhecido", r.text


# --- cláusula: incremental por área suja ----------------------------------------------------------------

def test_mover_chave_de_fronteira_suja_so_as_duas_subredes(sessao_a, env, limpar_redes):
    """Cláusula central do portão: depois de mover uma chave de fronteira entre dois alimentadores, só as 2
    subredes afetadas ficam sujas — a terceira, longe da edição, continua limpa e não é reatualizada."""
    rid = _criar_rede(sessao_a, "area-suja", limpar_redes)
    feicoes = _rede_tres_alimentadores(sessao_a, rid)

    # todas limpas primeiro (as 3 de média tensão e a de baixa tensão do transformador)
    inicial = _lote(sessao_a, env, rid, todas=True)
    assert inicial["atualizadas"] == 4 and inicial["recusadas"] == [], inicial
    assert all(s["estado"] == "limpa" for s in _subredes(sessao_a, rid).values())

    # a chave de fronteira fica no MEIO do alimentador A (longe do transformador, para que a área suja não
    # toque também a subrede de baixa tensão) e é movida para o meio do alimentador B
    ponta_a = feicoes[f"meio_{CTMT_A}"]
    ponta_b = feicoes[f"meio_{CTMT_B}"]
    chave = _ponto(sessao_a, rid, ponta_a[0], ponta_a[1], "chave_de_media_tensao", 1,
                   atributos={"ctmt": CTMT_A, "cod_id": "CH-FRONTEIRA"})
    r = sessao_a.post(f"/api/rede/{rid}/feicoes/pontos/applyEdits", json={"updates": [
        {"attributes": {"id": chave["id"]},
         "geometry": {"x": ponta_b[0], "y": ponta_b[1]}}]})
    assert r.status_code == 200, r.text
    assert r.json()["updateResults"][0]["success"] is True, r.text

    marcadas = {n: s for n, s in _subredes(sessao_a, rid).items() if s["estado"] == "suja"}
    assert sorted(marcadas) == sorted([CTMT_A, CTMT_B]), marcadas

    # o lote atualiza SÓ as duas sujas; a topologia é reconstruída antes porque a chave nova precisa de nó
    # (reconstruir apaga a área suja: quem guarda a marcação é o estado da subrede, gravado por marcar_sujas)
    _habilitar(sessao_a, rid)
    lote = _lote(sessao_a, env, rid)
    assert lote["candidatas"] == 2, lote
    assert sorted(i["subrede"] for i in lote["itens"]) == sorted([CTMT_A, CTMT_B]), lote
    assert _subredes(sessao_a, rid)[CTMT_C]["estado"] == "limpa"


def _lote(sessao, env, rid, todas=False):
    """Roda a atualização em lote pelo MESMO motor do job, sem depender de um worker rodando na trilha:
    `redes.subredes_atualizar` só transporta a chamada (app/rede_utilidades/tarefas.py)."""
    import psycopg2

    from app import db as banco
    from app.rede_utilidades import subredes
    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.test_rls import ids_por_slug

    eu = sessao.get("/api/eu").json()
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    tenant_id = ids_por_slug(con)[eu["inquilino"]["slug"]]
    con.close()
    contexto = banco.Contexto(tenant_id, int(eu["id"]), "teste-l404b")
    with banco.db(contexto) as cur:
        return subredes.atualizar_todas(cur, tenant_id, rid, todas=todas)


# --- cláusula: exportar ----------------------------------------------------------------------------------

def test_exportar_valida_no_esquema_e_bate_com_o_tracado(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "exportar", limpar_redes)
    _rede_tres_alimentadores(sessao_a, rid)
    alvo = _subredes(sessao_a, rid)[CTMT_A]
    assert sessao_a.post(f"/api/rede/{rid}/subredes/{alvo['id']}/atualizar").status_code == 200

    r = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT_A}/exportar")
    assert r.status_code == 200, r.text
    doc = r.json()
    Draft202012Validator(ESQUEMA).validate(doc)  # o esquema é contrato: reprova aqui também, fora da app
    assert doc["subrede"]["nome"] == CTMT_A and doc["subrede"]["estado"] == "limpa"
    assert doc["controladores"] and doc["controladores"][0]["origem"] == "dispositivo"
    assert doc["conectividade"], "a subrede tem trechos, logo tem conectividade"

    # Σ elementos = traçado de subrede, elemento a elemento (refutação exigida do item)
    controlador = doc["controladores"][0]
    t = sessao_a.post(f"/api/rede/{rid}/tracar", json={
        "tipo": "subrede",
        "pontos_partida": [{"feicao_id": controlador["feicao_id"], "terminal": controlador["terminal"]}]})
    assert t.status_code == 200, t.text
    tracado = t.json()
    assert len(doc["elementos"]) == tracado["contagem"] == doc["resumo"]["elementos"]
    do_tracado = sorted((e["feicao_id"], e["terminal"]) for e in tracado["elementos"])
    do_export = sorted((e["feicao_id"], e["terminal"]) for e in doc["elementos"])
    assert do_export == do_tracado, "exportação e traçado têm de coincidir elemento a elemento"

    nos = {c["de"] for c in doc["conectividade"]} | {c["para"] for c in doc["conectividade"]}
    assert len(nos) >= 2


def test_exportar_subrede_nunca_atualizada_e_recusado(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "exportar-suja", limpar_redes)
    _rede_tres_alimentadores(sessao_a, rid)
    r = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT_B}/exportar")
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "subrede_nunca_atualizada", r.text


def test_exportar_nome_desconhecido_da_404(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "exportar-404", limpar_redes)
    _rede_tres_alimentadores(sessao_a, rid)
    r = sessao_a.get(f"/api/rede/{rid}/subrede/nao-existe/exportar")
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "subrede_inexistente", r.text


def test_exportar_nome_repetido_em_dois_tiers_e_ambiguo(sessao_a, limpar_redes):
    """Refutação: o nome da subrede é único DENTRO do tier. Sem `tier`, nome repetido é ambíguo e recusado
    em vez de devolver um dos dois em silêncio. O caso é real: a cooperativa que batiza a subrede de baixa
    tensão com o nome do alimentador acaba com o mesmo nome em dois tiers.

    O terminal de jusante do transformador já é controlador (veio da importação), então o controlador novo
    fica no terminal de alta (1) — o que interessa aqui é o NOME repetido, não o lado."""
    rid = _criar_rede(sessao_a, "ambigua", limpar_redes)
    feicoes = _rede_tres_alimentadores(sessao_a, rid)
    r = sessao_a.post(f"/api/rede/{rid}/controlador", json={
        "feicao_id": feicoes["trafo"]["id"], "terminal": 1, "subrede": CTMT_A,
        "tier": "baixa_tensao", "nome": f"{CTMT_A}-bt"})
    assert r.status_code == 201, r.text
    subredes = _subredes(sessao_a, rid)
    for s in [s for s in subredes.values() if s["nome"] == CTMT_A]:
        assert sessao_a.post(f"/api/rede/{rid}/subredes/{s['id']}/atualizar").status_code == 200
    r = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT_A}/exportar")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "subrede_ambigua", r.text
    r = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT_A}/exportar?tier=baixa_tensao")
    assert r.status_code == 200, r.text
    assert r.json()["subrede"]["tier"] == "baixa_tensao"


def test_atualizar_desfaz_a_associacao_antiga(sessao_a, limpar_redes):
    """Refutação: um trecho que saiu da subrede perde a associação — a tabela de membros é reescrita, não
    acumulada."""
    rid = _criar_rede(sessao_a, "associacao", limpar_redes)
    feicoes = _rede_tres_alimentadores(sessao_a, rid)
    alvo = _subredes(sessao_a, rid)[CTMT_A]
    assert sessao_a.post(f"/api/rede/{rid}/subredes/{alvo['id']}/atualizar").status_code == 200
    antes = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT_A}/exportar").json()
    assert len([e for e in antes["elementos"] if e["geometria"] == "linha"]) == 2

    apagar = feicoes[f"mt2_{CTMT_A}"]["id"]
    r = sessao_a.post(f"/api/rede/{rid}/feicoes/linhas/applyEdits",
                      json={"deletes": [apagar]})
    assert r.status_code == 200, r.text
    _habilitar(sessao_a, rid)
    assert sessao_a.post(f"/api/rede/{rid}/subredes/{alvo['id']}/atualizar").status_code == 200
    depois = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT_A}/exportar").json()
    linhas = [e for e in depois["elementos"] if e["geometria"] == "linha"]
    assert len(linhas) == 1, depois["elementos"]
    assert apagar not in [e["feicao_id"] for e in depois["elementos"]]


# --- cláusula: o lote é job ------------------------------------------------------------------------------

def test_atualizar_em_lote_enfileira_job(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "job", limpar_redes)
    _rede_tres_alimentadores(sessao_a, rid)
    r = sessao_a.post(f"/api/rede/{rid}/subredes/atualizar")
    assert r.status_code == 202, r.text
    corpo = r.json()
    assert corpo["rede_id"] == rid and corpo["todas"] is False
    j = sessao_a.get(f"/api/jobs/{corpo['job_id']}")
    assert j.status_code == 200, j.text
    assert j.json()["tipo"] == "redes.subredes_atualizar"


def test_lote_atualiza_todas_as_sujas_e_conta(sessao_a, env, limpar_redes):
    rid = _criar_rede(sessao_a, "lote", limpar_redes)
    _rede_tres_alimentadores(sessao_a, rid)
    lote = _lote(sessao_a, env, rid)
    # 3 alimentadores + 1 subrede de baixa tensão (o transformador vira controlador na importação)
    assert lote["candidatas"] == 4, lote
    assert lote["atualizadas"] == 4 and lote["recusadas"] == [], lote
    assert lote["elementos"] > 0
    assert all(s["estado"] == "limpa" for s in _subredes(sessao_a, rid).values())
    de_novo = _lote(sessao_a, env, rid)
    assert de_novo["candidatas"] == 0, "nada sujo, nada a refazer (incremental)"


# --- cláusula: conferência contra o arquivo --------------------------------------------------------------

def test_conferencia_contra_o_ctmt_do_arquivo(sessao_a, env, limpar_redes):
    rid = _criar_rede(sessao_a, "conferencia", limpar_redes)
    _rede_tres_alimentadores(sessao_a, rid)
    _lote(sessao_a, env, rid)
    r = sessao_a.get(f"/api/rede/{rid}/subredes/conferencia?atributo=ctmt&tier=media_tensao")
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["total"] == 6, "seis trechos de média tensão (dois por alimentador)"
    assert c["comparaveis"] == 6 and c["sem_atributo"] == 0
    assert c["iguais"] == 6 and c["diferentes"] == 0 and c["diferencas"] == []
    assert c["concordancia"] == 1.0
