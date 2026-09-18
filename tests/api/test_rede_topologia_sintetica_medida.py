"""Medição SINTÉTICA em escala real do item L4-01-b-topologia-derivada (marcador `lento`).

Complemento de `test_rede_topologia_medida.py` (que mede contra o ativo BDGD real e exige
`PLAT_REDE_REFERENCIA_ESQUEMA`): este aqui prova que o CONSTRUTOR ATUAL, no código deste checkout, monta a
topologia na MESMA escala do portão — 44.268 trechos de MT + 29.244 de BT + 26.581 ramais + 5.481 trafos +
60.549 postes, padrão de `tests/dados/gerar_rede.py` (semente fixa, nenhum dado de cliente) — e grava o
resumo correto em `plat.rede_topo_resumo`. Nasceu na trilha remota l401bto1187 (18/09/2026): o ativo real
não existe neste servidor (ausente de todo banco local, conferido no catálogo), e o construtor recebeu 2
commits depois da medição real de 07/09 — sem esta prova, a cláusula de escala ficaria apoiada só numa
medição de código anterior.

Contagens esperadas saem da CONSTRUÇÃO do gerador (determinística), não do construtor de topologia:
  - arestas == trechos MT + BT + ramais + degenerados = 100.103 (cada linha vira UMA aresta);
  - arestas_sem_no == 10 (os degenerados, origem == destino);
  - nós órfãos == 50 (25 transformadores órfãos × 2 terminais, deslocados 1,0 m de qualquer vértice);
  - 60.549 postes (`sem_terminal`) -> ZERO nós de papel terminal do tipo ponto_notavel.

Tempo: registrado só quando a máquina está sem disputa (carga_1min <= 8, mesmo critério do brief de
`test_rede_direcao_medida.py`); as contagens são determinísticas e valem sob qualquer carga.

Escreve `tests/medidas/L4-01-b-topologia-derivada-sintetica.json` (arquivo PRÓPRIO — nunca toca no JSON da
medição real, que é o registro vivo da cláusula contra o arquivo BDGD).
"""

import json
import subprocess
import time
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.test_rede_topologia import _criar_rede, _importar_eletrica
from tests.api.test_rede_tracado_medida import _carga_da_maquina
from tests.api.test_rls import ids_por_slug
from tests.dados import gerar_rede

MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / "L4-01-b-topologia-derivada-sintetica.json"

ESPERADO_CARGA = {
    "trechos_mt": 44_268,
    "trechos_bt": 29_244,
    "ramais": 26_581,
    "trafos": 5_481,
    "trafos_orfaos": 25,
    "postes": 60_549,
    "trechos_degenerados": 10,
}
ESPERADO_ARESTAS = 44_268 + 29_244 + 26_581 + 10  # 100.103


@pytest.fixture
def limpar_redes(sessao_a, sessao_b):
    criadas = []
    yield criadas
    for sessao, rid in criadas:
        sessao.delete(f"/api/rede/{rid}", timeout=600)


@pytest.mark.lento
def test_medida_topologia_sintetica_escala_real(sessao_a, limpar_redes, env):
    carga_1min, ram_livre_gb = _carga_da_maquina()
    medida = {"rede_sintetica_escala_real": {"carga_1min": carga_1min, "ram_livre_gb": ram_livre_gb}}

    rid = _criar_rede(sessao_a, "medida-topo-sintetica", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    medida["rede_sintetica_escala_real"]["rede_id"] = rid

    eu = sessao_a.get("/api/eu").json()
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
        with con.cursor() as cur:
            cur.execute(
                "SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
                "set_config('plat.login', %s, false)",
                (str(ids["demo"]), str(eu["id"]), "medida-l401b-sintetica"),
            )
            t0 = time.perf_counter()
            contagem = gerar_rede.gerar(cur, ids["demo"], rid)  # tamanhos PADRÃO = escala do portão
            carga_segundos = time.perf_counter() - t0
        con.commit()
    finally:
        con.close()
    assert contagem == ESPERADO_CARGA, contagem

    # A CLÁUSULA, no código atual: habilitar pela API, tempo medido no servidor (perf_counter no construtor)
    t0 = time.perf_counter()
    r = sessao_a.post(f"/api/rede/{rid}/topologia/habilitar", timeout=3600)
    http_segundos = time.perf_counter() - t0
    assert r.status_code == 201, r.text[:2000]
    resumo = r.json()

    assert resumo["arestas"] == ESPERADO_ARESTAS, resumo
    assert resumo["arestas_sem_no"] == 10, resumo
    assert resumo["nos_orfaos"] == 50, resumo  # 25 trafos órfãos × 2 terminais

    # 60.549 postes (sem_terminal) -> ZERO nós; e o resumo GRAVADO é exatamente o que a API devolveu
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
                "set_config('plat.login', %s, false)",
                (str(ids["demo"]), str(eu["id"]), "medida-l401b-sintetica"),
            )
            cur.execute(
                "SELECT count(*) AS n FROM plat.rede_topo_no n WHERE n.rede_id = %s::uuid "
                "AND n.papel = 'terminal' AND n.tipo_id = (SELECT tp.id FROM plat.rede_tipo tp "
                "JOIN plat.rede_grupo g ON g.id = tp.grupo_id WHERE tp.rede_id = %s::uuid "
                "AND g.codigo = 'ponto_notavel' AND tp.codigo = 1)",
                (rid, rid),
            )
            nos_poste = cur.fetchone()["n"]
            cur.execute(
                "SELECT nos, arestas, nos_orfaos, arestas_sem_no, duracao_ms, tolerancia_m "
                "FROM plat.rede_topo_resumo WHERE rede_id = %s::uuid",
                (rid,),
            )
            gravado = cur.fetchone()
    finally:
        con.close()
    assert nos_poste == 0, nos_poste
    assert gravado["nos"] == resumo["nos"] and gravado["arestas"] == resumo["arestas"]
    assert gravado["nos_orfaos"] == resumo["nos_orfaos"]
    assert gravado["arestas_sem_no"] == resumo["arestas_sem_no"]
    assert gravado["duracao_ms"] == resumo["duracao_ms"]

    medida["rede_sintetica_escala_real"].update(
        {
            "contagem_gerador": contagem,
            "carga_segundos": round(carga_segundos, 3),
            "resumo": resumo,
            "habilitar_http_segundos": round(http_segundos, 3),
            "tempo_medido_sem_disputa": carga_1min <= 8,
            "motivo_tempo": None if carga_1min <= 8 else "carga acima de 8: o brief proíbe medir tempo sob disputa",
            "postes_zero_no": nos_poste,
            "ok": True,
        }
    )
    anteriores = json.loads(MEDIDAS.read_text(encoding="utf-8")) if MEDIDAS.exists() else {}
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    anteriores.update(
        {
            "item": "L4-01-b-topologia-derivada",
            "git_sha": sha,
            "tipo": "rede SINTÉTICA determinística (gerar_rede.py, semente fixa) na escala exata do portão — "
            "complemento da medição contra o ativo real, que exige PLAT_REDE_REFERENCIA_ESQUEMA",
            "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "comando": "venv/bin/pytest tests/api/test_rede_topologia_sintetica_medida.py -m lento -q",
            **medida,
        }
    )
    MEDIDAS.write_text(json.dumps(anteriores, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
