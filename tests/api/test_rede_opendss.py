"""Exportação de subrede para OpenDSS (item L4-05-a-exportar-opendss).

Cláusulas do portão provadas aqui:

* `GET .../subrede/{nome}/exportar?formato=dss` devolve a pasta `.dss` (zip com Master, Linhas,
  Transformadores, Cargas, Curvas, resumo.json e NAO_FAZ.md) — `test_exportar_dss_devolve_a_pasta`;
* o circuito exportado COMPILA no OpenDSS e o número de barras e de linhas do circuito compilado bate com
  os nós e os trechos da subrede, conferidos por consulta independente ao banco —
  `test_circuito_compila_e_conta_barras_e_linhas`;
* com `jusante=true` o alimentador sai inteiro: transformador com kVA e perdas, carga com a curva de 864
  pontos e geração distribuída como carga negativa — `test_alimentador_inteiro_com_trafo_carga_e_geracao`;
* o relatório do que o conversor não faz sai junto — conferido nos dois testes acima.

Refutação (papel adversário), provada aqui:
* `test_trafo_sem_potencia_falha_alto`: transformador sem POT_NOM faz a exportação PARAR com 422, em vez de
  escrever 0 kVA num modelo que compila e mente;
* `test_tensao_nominal_ausente_ou_fora_do_dominio_falha_alto`: sem TEN_NOM (ou com código fora do domínio
  TTEN) não há tensão de base, e o conversor recusa em vez de arbitrar uma;
* `test_formato_desconhecido_e_recusado` e `test_exportar_dss_de_subrede_nunca_atualizada_e_recusado`.
"""

import io
import json
import os
import subprocess
import time
import zipfile
from pathlib import Path

import pytest

from app.rede_utilidades import opendss
from tests.api.conftest import PREFIXO_TESTE

ITEM = "L4-05-a-exportar-opendss"
MEDIDAS = Path(__file__).resolve().parents[1] / "medidas" / f"{ITEM}.json"

CTMT = "ZT-DSS-1"
SUB = "SUB"
DISJUNTOR = 4  # tipo `disjuntor` do grupo chave_de_media_tensao (pacote eletrica-br)
TEN_NOM = "63"  # 23,1 kV — o código que faltava no dicionário do conversor da casa
TEN_LIN_SE = "15"  # 0,38 kV no secundário


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _criar_rede(sessao, sufixo, limpar):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-dss-{sufixo}", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append(rid)
    from app.rede_utilidades import instalados

    r = sessao.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    return rid


def _ponto(sessao, rid, lon, lat, grupo, tipo_codigo=1, atributos=None):
    corpo = {"tipo_codigo": tipo_codigo, "grupo": grupo, "lon": lon, "lat": lat}
    if atributos:
        corpo["atributos"] = atributos
    r = sessao.post(f"/api/rede/{rid}/feicoes/pontos", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _linha(sessao, rid, coordenadas, grupo, tipo_codigo=1, atributos=None):
    corpo = {"tipo_codigo": tipo_codigo, "grupo": grupo, "coordenadas": coordenadas}
    if atributos:
        corpo["atributos"] = atributos
    r = sessao.post(f"/api/rede/{rid}/feicoes/linhas", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _alimentador(sessao, rid, *, pot_nom=75.0, ten_nom=TEN_NOM):
    """Um alimentador de teste: disjuntor de saída, dois trechos de média tensão, transformador de
    distribuição no fim, um trecho de baixa tensão, uma unidade consumidora e uma geração distribuída."""
    lon0, lat0, d = 34.0, 14.0, 0.001
    a = (lon0, lat0)
    b = (lon0 + d, lat0)
    c = (lon0 + 2 * d, lat0)
    e = (lon0 + 2 * d, lat0 + d)
    f = (lon0 + 2 * d, lat0 + 2 * d)
    g = (lon0 + 3 * d, lat0 + d)
    comum = {"ctmt": CTMT, "sub": SUB}
    feicoes = {"a": a, "b": b, "c": c, "e": e, "f": f, "g": g}
    feicoes["disjuntor"] = _ponto(sessao, rid, *a, "chave_de_media_tensao", DISJUNTOR,
                                  atributos={**comum, "unsemt_fas_con": "ABC", "unsemt_p_n_ope": "F",
                                             "ten_nom": ten_nom, "unsemt_cod_id": "CH-1"})
    feicoes["mt1"] = _linha(sessao, rid, [list(a), list(b)], "trecho_de_media_tensao",
                            atributos={**comum, "cod_id": "MT-1", "tip_cnd": "2-CA"})
    feicoes["mt2"] = _linha(sessao, rid, [list(b), list(c)], "trecho_de_media_tensao",
                            atributos={**comum, "cod_id": "MT-2", "tip_cnd": "2-CA"})
    atributos_trafo = {"cod_id": "TR-1", "ten_lin_se": TEN_LIN_SE, "per_fer": 150.0, "per_tot": 1100.0}
    if pot_nom is not None:
        atributos_trafo["pot_nom"] = pot_nom
    feicoes["trafo"] = _ponto(sessao, rid, *c, "transformador_de_distribuicao", 1, atributos=atributos_trafo)
    feicoes["bt1"] = _linha(sessao, rid, [list(c), list(e)], "trecho_de_baixa_tensao",
                            atributos={"cod_id": "BT-1", "tip_cnd": "M-CA"})
    feicoes["bt2"] = _linha(sessao, rid, [list(e), list(f)], "trecho_de_baixa_tensao",
                            atributos={"cod_id": "BT-2", "tip_cnd": "M-CA"})
    # a unidade consumidora de baixa tensão liga pelo RAMAL DE LIGAÇÃO, nunca direto no trecho: é a regra
    # de par do pacote eletrica-br (`ramal_de_ligacao/1` ↔ `unidade_consumidora/1`), que é como a BDGD
    # modela o ponto de entrega.
    feicoes["ramal"] = _linha(sessao, rid, [list(e), list(g)], "ramal_de_ligacao",
                              atributos={"cod_id": "RL-1", "tip_cnd": "M-CA"})
    feicoes["uc"] = _ponto(sessao, rid, *g, "unidade_consumidora", 1,
                           atributos={"cod_id": "UC-1", "ene_sum": 3.6})
    feicoes["gd"] = _ponto(sessao, rid, *f, "geracao_distribuida", 1,
                           atributos={"cod_id": "GD-1", "ene_sum": 1.2})
    r = sessao.post(f"/api/rede/{rid}/topologia/habilitar")
    assert r.status_code == 201, r.text
    r = sessao.post(f"/api/rede/{rid}/controladores/importar")
    assert r.status_code == 200, r.text
    return feicoes


def _atualizar_tudo(sessao, env, rid):
    """Atualiza todas as subredes pelo mesmo motor do job, sem depender de um worker na trilha."""
    import psycopg2

    from app import db as banco
    from app.rede_utilidades import subredes
    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.test_rls import ids_por_slug

    eu = sessao.get("/api/eu").json()
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    tenant_id = ids_por_slug(con)[eu["inquilino"]["slug"]]
    con.close()
    contexto = banco.Contexto(tenant_id, int(eu["id"]), "teste-l405a")
    with banco.db(contexto) as cur:
        return subredes.atualizar_todas(cur, tenant_id, rid, todas=True)


def _conferencia_independente(env, sessao, rid, com_jusante: bool):
    """Nós e trechos da(s) subrede(s) exportada(s), contados por consulta DIRETA às tabelas — caminho
    independente do que o exportador calcula, que é o ponto da cláusula."""
    import psycopg2

    from app import db as banco
    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.test_rls import ids_por_slug

    eu = sessao.get("/api/eu").json()
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    tenant_id = ids_por_slug(con)[eu["inquilino"]["slug"]]
    con.close()
    with banco.db(banco.Contexto(tenant_id, int(eu["id"]), "teste-l405a")) as cur:
        cur.execute(
            "SELECT s.id, t.ordem FROM plat.rede_subrede s JOIN plat.rede_tier t ON t.id = s.tier_id "
            "WHERE s.rede_id = %s::uuid AND s.nome = %s ORDER BY t.ordem", (rid, CTMT))
        pedida = cur.fetchone()
        ids = [str(pedida["id"])]
        if com_jusante:
            from app.rede_utilidades import opendss

            ids = opendss.subredes_de_jusante(cur, rid, ids, pedida["ordem"])
        cur.execute(
            "SELECT count(*) AS n FROM plat.rede_subrede_elemento e "
            "JOIN plat.rede_topo_aresta a ON a.rede_id = %s::uuid AND a.origem_id = e.feicao_id "
            "WHERE e.subrede_id = ANY(%s::uuid[]) AND e.geometria = 'linha' "
            "AND a.no_origem_id IS NOT NULL AND a.no_destino_id IS NOT NULL", (rid, ids))
        trechos = cur.fetchone()["n"]
        cur.execute(
            "WITH membros AS (SELECT feicao_id, terminal_num, geometria FROM plat.rede_subrede_elemento "
            "                 WHERE subrede_id = ANY(%(ids)s::uuid[])), "
            "     das_linhas AS (SELECT a.no_origem_id AS no FROM plat.rede_topo_aresta a "
            "                    JOIN membros m ON m.feicao_id = a.origem_id AND m.geometria = 'linha' "
            "                    WHERE a.rede_id = %(rede)s::uuid "
            "                    UNION SELECT a.no_destino_id FROM plat.rede_topo_aresta a "
            "                    JOIN membros m ON m.feicao_id = a.origem_id AND m.geometria = 'linha' "
            "                    WHERE a.rede_id = %(rede)s::uuid), "
            "     dos_pontos AS (SELECT n.id AS no FROM plat.rede_topo_no n JOIN membros m "
            "                    ON m.feicao_id = n.origem_id "
            "                       AND m.terminal_num IS NOT DISTINCT FROM n.terminal_num "
            "                    WHERE n.rede_id = %(rede)s::uuid AND m.geometria = 'ponto') "
            "SELECT count(DISTINCT no) AS n FROM (SELECT no FROM das_linhas UNION ALL "
            "                                     SELECT no FROM dos_pontos) x WHERE no IS NOT NULL",
            {"rede": rid, "ids": ids})
        nos = cur.fetchone()["n"]
    return {"trechos": trechos, "nos": nos, "subredes": len(ids)}


def _pasta(resposta) -> dict:
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resposta.content)) as z:
        return {n.split("/", 1)[1]: z.read(n).decode("utf-8") for n in z.namelist()}


def _compilar(tmp_path, arquivos: dict) -> dict:
    """Compila o circuito exportado no OpenDSS e devolve as contagens do circuito COMPILADO."""
    opendssdirect = pytest.importorskip(
        "opendssdirect", reason="opendssdirect não está na venv desta máquina: a compilação não foi medida")
    for nome, texto in arquivos.items():
        (tmp_path / nome).write_text(texto, encoding="utf-8")
    opendssdirect.Text.Command("Clear")
    opendssdirect.Text.Command(f'Compile "{tmp_path / "Master.dss"}"')
    erro = opendssdirect.Error.Description()
    return {
        "erro": erro,
        "barras": opendssdirect.Circuit.NumBuses(),
        "linhas": len(opendssdirect.Lines.AllNames()) if opendssdirect.Lines.Count() else 0,
        "transformadores": (len(opendssdirect.Transformers.AllNames())
                            if opendssdirect.Transformers.Count() else 0),
        "cargas": len(opendssdirect.Loads.AllNames()) if opendssdirect.Loads.Count() else 0,
    }


# --- cláusula: a rota devolve a pasta -------------------------------------------------------------------

def test_exportar_dss_devolve_a_pasta(sessao_a, env, limpar_redes):
    rid = _criar_rede(sessao_a, "pasta", limpar_redes)
    _alimentador(sessao_a, rid)
    _atualizar_tudo(sessao_a, env, rid)

    arquivos = _pasta(sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/exportar?formato=dss"))
    assert set(arquivos) == {"Master.dss", "Curvas.dss", "Linhas.dss", "Transformadores.dss",
                             "Cargas.dss", "NAO_FAZ.md", "resumo.json"}
    resumo = json.loads(arquivos["resumo.json"])
    assert resumo["subrede"] == CTMT and resumo["tier"] == "media_tensao"
    assert resumo["codigo_tensao_nominal"] == TEN_NOM and resumo["kv_fonte"] == 23.1
    assert resumo["pontos_por_curva"] == 864
    assert resumo["chaves"] and resumo["chaves"][0]["estado"] == "fechada"
    assert "não faz" in arquivos["NAO_FAZ.md"]
    # o formato JSON continua sendo o padrão da mesma rota
    r = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/exportar")
    assert r.status_code == 200 and r.json()["subrede"]["nome"] == CTMT


# --- cláusula: compila e as contagens batem --------------------------------------------------------------

def test_circuito_compila_e_conta_barras_e_linhas(sessao_a, env, limpar_redes, tmp_path):
    rid = _criar_rede(sessao_a, "conta", limpar_redes)
    _alimentador(sessao_a, rid)
    _atualizar_tudo(sessao_a, env, rid)

    arquivos = _pasta(sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/exportar?formato=dss"))
    resumo = json.loads(arquivos["resumo.json"])
    esperado = _conferencia_independente(env, sessao_a, rid, com_jusante=False)
    conferencia = resumo["conferencia"]
    assert conferencia["nos_da_subrede"] == esperado["nos"], (conferencia, esperado)
    assert conferencia["trechos_da_subrede"] == esperado["trechos"], (conferencia, esperado)
    assert conferencia["trechos_sem_no_na_topologia"] == 0

    circuito = _compilar(tmp_path, arquivos)
    assert circuito["erro"] == "", circuito["erro"]
    assert circuito["linhas"] == esperado["trechos"], circuito
    assert circuito["barras"] == esperado["nos"] - conferencia["fusoes_por_chave_fechada"], circuito
    assert conferencia["barras_esperadas"] == circuito["barras"]


# --- cláusula: alimentador inteiro (trafo, carga e geração) ----------------------------------------------

def test_alimentador_inteiro_com_trafo_carga_e_geracao(sessao_a, env, limpar_redes, tmp_path):
    rid = _criar_rede(sessao_a, "inteiro", limpar_redes)
    _alimentador(sessao_a, rid)
    _atualizar_tudo(sessao_a, env, rid)

    arquivos = _pasta(sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/exportar?formato=dss&jusante=true&ano=2024"))
    resumo = json.loads(arquivos["resumo.json"])
    assert resumo["com_jusante"] is True and resumo["subredes_no_circuito"] >= 2, resumo
    conferencia = resumo["conferencia"]
    assert conferencia["transformadores"] == 1, resumo
    assert conferencia["cargas"] == 1 and conferencia["geracao_distribuida"] == 1, resumo

    # transformador: kVA e perdas vêm de POT_NOM, PER_FER e PER_TOT, sem nada inventado
    trafos = arquivos["Transformadores.dss"]
    assert "kvas=[75 75]" in trafos, trafos
    assert "%noloadloss=0.2000" in trafos, trafos          # 100 * 150 / (1000 * 75)
    assert "%r=0.6333" in trafos, trafos                   # 100 * (1100-150) / (1000*75), metade por enrolamento
    assert "kv=0.38000" in trafos, trafos
    assert "xhl" not in trafos, "a reatância não vem do arquivo: fica o padrão do OpenDSS"

    # geração distribuída: carga NEGATIVA de corrente constante
    cargas = arquivos["Cargas.dss"]
    assert "model=5" in cargas and "kw=-" in cargas, cargas
    assert cargas.count("New Load.") == 2, cargas
    assert "npts=864" in arquivos["Curvas.dss"]

    esperado = _conferencia_independente(env, sessao_a, rid, com_jusante=True)
    assert conferencia["nos_da_subrede"] == esperado["nos"], (conferencia, esperado)
    assert conferencia["trechos_da_subrede"] == esperado["trechos"], (conferencia, esperado)

    circuito = _compilar(tmp_path, arquivos)
    assert circuito["erro"] == "", circuito["erro"]
    assert circuito["linhas"] == esperado["trechos"], circuito
    assert circuito["barras"] == esperado["nos"] - conferencia["fusoes_por_chave_fechada"], circuito
    assert circuito["transformadores"] == 1 and circuito["cargas"] == 2, circuito
    _gravar_medidas(resumo, esperado, circuito, arquivos)


def _gravar_medidas(resumo, esperado, circuito, arquivos) -> None:
    """Grava o que foi MEDIDO nesta rodada (nunca copiado do enunciado): as contagens do circuito compilado,
    as da subrede pelo caminho independente e o tamanho do dicionário de tensões."""
    import opendssdirect

    # o `Compile` do OpenDSS TROCA o diretório de trabalho do processo para a pasta do .dss: o git tem de
    # ser chamado com o caminho do repositório explícito.
    raiz = MEDIDAS.resolve().parents[2]
    sha = subprocess.run(["git", "-C", str(raiz), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    MEDIDAS.write_text(json.dumps({
        "item": ITEM,
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": sha,
        "maquina": f"PostgreSQL 16 em iagro_sat, base da trilha ({os.environ.get('PLAT_SCHEMA', '?')}); "
                   f"opendssdirect.py {opendssdirect.__version__}; rede de teste sintética do próprio teste",
        "medidas": {
            "dicionario_tensao": {"codigos": len(opendss.TENSAO_KV),
                                  "dominio_esperado": "0 a 109 (TTEN da BDGD)",
                                  "kv_do_codigo_63": opendss.TENSAO_KV["63"]},
            "curva": {"pontos": opendss.PONTOS_DA_CURVA, "meses": 12, "tipos_de_dia": 3, "horas": 24},
            "arquivos_da_pasta": sorted(arquivos),
            "subrede_por_caminho_independente": esperado,
            "conferencia_do_exportador": resumo["conferencia"],
            "circuito_compilado": circuito,
        },
        "comando": "bash laco/roda_teste.sh tests/api/test_rede_opendss.py tests/unit/test_opendss.py -q",
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# --- refutação -------------------------------------------------------------------------------------------

def test_trafo_sem_potencia_falha_alto(sessao_a, env, limpar_redes):
    """Refutação exigida: sem POT_NOM o conversor PARA. Escrever 0 kVA daria um circuito que compila e diz
    uma coisa falsa sobre a rede."""
    rid = _criar_rede(sessao_a, "sem-kva", limpar_redes)
    _alimentador(sessao_a, rid, pot_nom=None)
    _atualizar_tudo(sessao_a, env, rid)
    r = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/exportar?formato=dss&jusante=true")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "trafo_sem_potencia", r.text


def test_tensao_nominal_ausente_ou_fora_do_dominio_falha_alto(sessao_a, env, limpar_redes):
    rid = _criar_rede(sessao_a, "sem-tensao", limpar_redes)
    _alimentador(sessao_a, rid, ten_nom=None)
    _atualizar_tudo(sessao_a, env, rid)
    r = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/exportar?formato=dss")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "tensao_ausente", r.text

    rid2 = _criar_rede(sessao_a, "tensao-ruim", limpar_redes)
    _alimentador(sessao_a, rid2, ten_nom="999")
    _atualizar_tudo(sessao_a, env, rid2)
    r = sessao_a.get(f"/api/rede/{rid2}/subrede/{CTMT}/exportar?formato=dss")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "tensao_codigo_desconhecido", r.text


def test_formato_desconhecido_e_recusado(sessao_a, env, limpar_redes):
    rid = _criar_rede(sessao_a, "formato", limpar_redes)
    _alimentador(sessao_a, rid)
    _atualizar_tudo(sessao_a, env, rid)
    r = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/exportar?formato=shapefile")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "formato_desconhecido", r.text


def test_exportar_dss_de_subrede_nunca_atualizada_e_recusado(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "nunca", limpar_redes)
    _alimentador(sessao_a, rid)
    r = sessao_a.get(f"/api/rede/{rid}/subrede/{CTMT}/exportar?formato=dss")
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "subrede_nunca_atualizada", r.text
