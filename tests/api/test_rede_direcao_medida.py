"""Medidas do item L4-02-b-montante-jusante, gravadas em `tests/medidas/L4-02-b-montante-jusante.json`.

Duas cláusulas do portão são MEDIDA, não teste de igualdade:

1. TEMPO: `POST /api/rede/{id}/tracar` com `tipo=jusante` responde em ≤ 2 s (p95, 30 chamadas) numa rede
   sintética de milhares de trechos com controlador de subrede marcado. Regra de desempenho do brief: só se
   mede com a máquina calma, e a carga fica gravada ao lado do número; com carga acima de 8 a cláusula é
   registrada como NÃO MEDIDA em vez de reprovar o produto pela casa.
2. UNIVERSO DA COOPERATIVA DE TESTE: a cláusula "jusante de cada transformador devolve exatamente as
   unidades consumidoras que o arquivo liga a ele (UNI_TR_MT) em ≥ 99 % dos transformadores COM REDE
   DESENHADA ATÉ A UC" pressupõe que exista rede desenhada até a UC. Este teste mede esse universo direto no
   ativo da casa (schema `certaja`, só leitura) e grava o número: a unidade consumidora se prende à rede pelo
   poste `PN_CON` através do ramal de ligação, e o ramal do arquivo NÃO TEM GEOMETRIA (`wkt` nulo em todos os
   registros). Sem geometria não há trecho, sem trecho não há nó de topologia, e o universo da cláusula é
   VAZIO. Fica medido e nomeado, com o motivo por transformador, em vez de ser declarado cumprido.
"""

import json
import time
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rede_tracado import _criar_rede, _importar_eletrica, limpar_redes  # noqa: F401
from tests.api.test_rede_tracado_medida import _carga_da_maquina
from tests.dados import gerar_rede

MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / "L4-02-b-montante-jusante.json"

N_MT = 3000
N_BT = 1500
N_TRAFOS = 30


def _gravar(dados: dict) -> None:
    MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
    anteriores = json.loads(MEDIDAS.read_text(encoding="utf-8")) if MEDIDAS.exists() else {}
    anteriores.update(dados)
    MEDIDAS.write_text(json.dumps(anteriores, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                       encoding="utf-8")


def test_medida_universo_da_cooperativa_de_teste(env):
    """Quantos transformadores da cooperativa de teste têm rede desenhada até a unidade consumidora — o
    universo da cláusula de 99 %. Lê só o ativo da casa; não carrega nada na plataforma."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT count(*) AS n, count(pn_con) AS com_pn_con, "
                        "count(DISTINCT uni_tr_mt) AS trafos_citados FROM certaja.ucbt")
            uc = dict(cur.fetchone())
            cur.execute("SELECT count(*) AS n, count(wkt) AS com_geometria, "
                        "count(DISTINCT uni_tr_mt) AS trafos_citados FROM certaja.ramlig")
            ramal = dict(cur.fetchone())
            cur.execute("SELECT count(*) AS n FROM certaja.trafo")
            trafos = cur.fetchone()["n"]
    finally:
        con.close()

    universo = ramal["com_geometria"]  # sem ramal com geometria não há caminho desenhado até a UC
    _gravar({"universo_cooperativa": {
        "medido": True,
        "unidades_consumidoras": uc["n"], "uc_com_pn_con": uc["com_pn_con"],
        "transformadores": trafos, "transformadores_citados_pelas_uc": uc["trafos_citados"],
        "ramais_de_ligacao": ramal["n"], "ramais_com_geometria": ramal["com_geometria"],
        "transformadores_com_rede_desenhada_ate_a_uc": universo,
        "motivo_dos_que_nao_fecham": (
            "ramal sem geometria: o ramal de ligação existe como registro no arquivo (%d), com o "
            "transformador em UNI_TR_MT e o poste em PN_CON, mas nenhum traz `wkt`. Sem geometria o ramal "
            "não vira trecho, não vira aresta de topologia e a unidade consumidora não tem caminho "
            "desenhado até o transformador — o universo da cláusula de 99%% é vazio, e nenhum "
            "transformador é contado como fechado nem como falha." % ramal["n"]),
    }})
    assert universo == 0 or universo == ramal["n"], (
        "medida inconsistente: ramais com geometria fora de {0, total}")


@pytest.mark.lento
def test_medida_p95_jusante_rede_sintetica(sessao_a, env, limpar_redes):  # noqa: F811
    """p95 de `tipo=jusante` numa rede sintética com controlador de subrede (semente fixa do gerador do item
    L4-01-b; nenhum dado de cliente)."""
    carga_1min, ram_livre_gb = _carga_da_maquina()
    if carga_1min > 8:
        _gravar({"p95_jusante": {"medido": False, "carga_1min": carga_1min, "ram_livre_gb": ram_livre_gb,
                                 "motivo": "carga acima de 8: o brief proíbe medir tempo sob disputa"}})
        pytest.skip(f"carga_1min={carga_1min} > 8, cláusula registrada como não medida")

    rid = _criar_rede(sessao_a, "medida-direcao", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT set_config('plat.tenant_id', '1', false), "
                        "set_config('plat.usuario_id', '1', false), "
                        "set_config('plat.login', %s, false)", (PREFIXO_TESTE + "-medida",))
            contagem = gerar_rede.gerar(cur, 1, rid, n_mt=N_MT, n_bt=N_BT, n_ramais=0, n_trafos=N_TRAFOS,
                                        n_postes=0, n_trafos_orfaos=0, n_trechos_degenerados=0)
        con.commit()
    finally:
        con.close()

    r = sessao_a.post(f"/api/rede/{rid}/topologia/habilitar", timeout=600)
    assert r.status_code == 201, r.text
    resumo = r.json()

    r = sessao_a.get(f"/api/rede/{rid}/feicoes/pontos?limite=1")
    assert r.status_code == 200, r.text
    trafo = r.json()["itens"][0]
    r = sessao_a.post(f"/api/rede/{rid}/controlador",
                      json={"feicao_id": trafo["id"], "terminal": 1, "subrede": "zt-medida",
                            "tier": "media_tensao", "papel": "fonte", "nome": "zt-medida"})
    assert r.status_code == 201, r.text

    corpo = {"tipo": "jusante", "pontos_partida": [{"feicao_id": trafo["id"], "terminal": 2}]}
    tempos_ms = []
    resposta = None
    for _ in range(30):
        t0 = time.perf_counter()
        resposta = sessao_a.post(f"/api/rede/{rid}/tracar", json=corpo, timeout=120)
        tempos_ms.append((time.perf_counter() - t0) * 1000)
        assert resposta.status_code == 200, resposta.text[:800]
    tempos_ms.sort()
    p95 = tempos_ms[int(0.95 * len(tempos_ms)) - 1]
    corpo_json = resposta.json()
    _gravar({"p95_jusante": {
        "medido": True, "p95_ms": round(p95, 1), "media_ms": round(sum(tempos_ms) / len(tempos_ms), 1),
        "max_ms": round(max(tempos_ms), 1), "n_amostras": len(tempos_ms),
        "rede_sintetica": {**contagem, "nos": resumo["nos"], "arestas": resumo["arestas"]},
        "direcao": corpo_json["direcao"], "origem_direcao": corpo_json["origem_direcao"],
        "contagem": corpo_json["contagem"], "nos_alcancados": corpo_json["nos_alcancados"],
        "carga_1min": carga_1min, "ram_livre_gb": ram_livre_gb,
    }})
    assert p95 <= 2000, f"p95={p95:.1f} ms acima de 2000 ms (carga_1min={carga_1min})"
