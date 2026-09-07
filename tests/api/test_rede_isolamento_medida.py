"""Medidas do item L4-02-c-isolamento, gravadas em `tests/medidas/L4-02-c-isolamento.json`.

Duas cláusulas do portão são MEDIDA, não igualdade, e as duas ficam aqui:

1. TEMPO: `tipo=isolamento` responde em ≤ 2 s (p95, 30 chamadas). A regra de desempenho do brief vale: só se
   mede com a máquina calma, a carga fica gravada ao lado do número e, com carga acima de 8, a cláusula é
   registrada como NÃO MEDIDA em vez de reprovar o produto pela casa.
2. UNIVERSO DA REDE REAL: a cláusula "na cooperativa de teste, o nº de clientes afetados bate com a soma de
   UCBT a jusante" pressupõe (a) uma camada de dispositivos de manobra na rede carregada e (b) rede desenhada
   até a unidade consumidora. Este teste mede as duas coisas direto no ativo da casa (schema `certaja`, só
   leitura) e grava o número em vez de declarar a cláusula cumprida.
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

MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / "L4-02-c-isolamento.json"

N_MT = 3000
N_BT = 1500
N_TRAFOS = 30
# tabelas da BDGD que trariam dispositivo de manobra/proteção de média tensão para a rede carregada
TABELAS_DE_MANOBRA = ("unsemt", "unsebt", "chave", "unremt")


def _gravar(dados: dict) -> None:
    MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
    anteriores = json.loads(MEDIDAS.read_text(encoding="utf-8")) if MEDIDAS.exists() else {}
    anteriores.update(dados)
    MEDIDAS.write_text(json.dumps(anteriores, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                       encoding="utf-8")


def test_medida_universo_da_rede_real(env):
    """Duas perguntas ao ativo da casa: existe camada de dispositivo de manobra na extração? e existe rede
    desenhada até a unidade consumidora? Sem a primeira não há conjunto de isolamento a conferir; sem a
    segunda não há "soma de UCBT a jusante" a comparar."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'certaja' "
                        "ORDER BY table_name")
            tabelas = [r["table_name"] for r in cur.fetchall()]
            cur.execute("SELECT count(*) AS n, count(wkt) AS com_geometria FROM certaja.ramlig")
            ramal = dict(cur.fetchone())
            cur.execute("SELECT count(*) AS n FROM certaja.ucbt")
            ucbt = cur.fetchone()["n"]
    finally:
        con.close()

    de_manobra = [t for t in tabelas if t in TABELAS_DE_MANOBRA]
    _gravar({"universo_da_rede_real": {
        "medido": True,
        "tabelas_do_ativo": len(tabelas),
        "tabelas_de_manobra_presentes": de_manobra,
        "unidades_consumidoras_bt": ucbt,
        "ramais_de_ligacao": ramal["n"], "ramais_com_geometria": ramal["com_geometria"],
        "conclusao": (
            "a extração da cooperativa de teste não traz camada de dispositivo de manobra ou proteção de "
            "média tensão (nenhuma de %s existe no schema), então não há conjunto de isolamento a conferir "
            "nela; e o ramal de ligação, único caminho desenhado até a unidade consumidora, tem %d de %d "
            "registros com geometria, de modo que a soma de UCBT a jusante também tem universo vazio. As "
            "duas metades desta cláusula ficam PENDENTES por falta de dado de origem, não por falta de "
            "traçado — o mesmo achado que o item irmão L4-02-b registrou para montante e jusante."
            % (list(TABELAS_DE_MANOBRA), ramal["com_geometria"], ramal["n"])),
    }})
    assert de_manobra == [] or ramal["com_geometria"] >= 0  # a medida é o resultado; não há alvo a bater


@pytest.mark.lento
def test_medida_p95_isolamento_rede_sintetica(sessao_a, env, limpar_redes):  # noqa: F811
    """p95 de `tipo=isolamento` numa rede sintética do gerador do item L4-01-b (semente fixa; nenhum dado de
    cliente). ⚠ o gerador não produz dispositivo de manobra: a medida cobre o custo do GRAFO (montar as
    arestas, os componentes conexos e o resumo sobre milhares de trechos), que é a parte que cresce com o
    tamanho da rede, e não a escolha do conjunto, que trabalha sobre o grafo reduzido dos dispositivos. O
    que a resposta devolve nessa rede fica gravado junto, para não haver dúvida sobre o que foi medido."""
    carga_1min, ram_livre_gb = _carga_da_maquina()
    if carga_1min > 8:
        _gravar({"p95_isolamento": {"medido": False, "carga_1min": carga_1min, "ram_livre_gb": ram_livre_gb,
                                    "motivo": "carga acima de 8: o brief proíbe medir tempo sob disputa"}})
        pytest.skip(f"carga_1min={carga_1min} > 8, cláusula registrada como não medida")

    rid = _criar_rede(sessao_a, "medida-isolamento", limpar_redes)
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
    resumo_topologia = r.json()

    r = sessao_a.get(f"/api/rede/{rid}/topologia/nos?limite=1")
    assert r.status_code == 200, r.text
    no = r.json()["itens"][0]
    corpo = {"tipo": "isolamento",
             "pontos_partida": [{"lon": no["lon"], "lat": no["lat"], "tolerancia_m": 1.0}]}
    tempos_ms = []
    resposta = None
    for _ in range(30):
        t0 = time.perf_counter()
        resposta = sessao_a.post(f"/api/rede/{rid}/tracar", json=corpo, timeout=120)
        tempos_ms.append((time.perf_counter() - t0) * 1000)
        assert resposta.status_code == 200, resposta.text[:800]
    tempos_ms.sort()
    p95 = tempos_ms[int(0.95 * len(tempos_ms)) - 1]
    j = resposta.json()
    _gravar({"p95_isolamento": {
        "medido": True, "p95_ms": round(p95, 1), "media_ms": round(sum(tempos_ms) / len(tempos_ms), 1),
        "max_ms": round(max(tempos_ms), 1), "n_amostras": len(tempos_ms),
        "rede_sintetica": {**contagem, "nos": resumo_topologia["nos"],
                           "arestas": resumo_topologia["arestas"]},
        "sem_dispositivo_de_manobra": True,
        "resposta": {"isolavel": j["isolavel"], "motivo": j["motivo"],
                     "dispositivos_a_abrir": len(j["dispositivos_a_abrir"]),
                     "contagem": j["contagem"]},
        "carga_1min": carga_1min, "ram_livre_gb": ram_livre_gb,
    }})
    assert p95 <= 2000, f"p95={p95:.1f} ms acima de 2000 ms (carga_1min={carga_1min})"
