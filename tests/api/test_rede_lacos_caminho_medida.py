"""Medição em escala REAL do item L4-02-d-lacos-e-caminho-curto (marcador `lento`: fora do pytest do dia a dia).

Cláusulas do portão medidas aqui, na mesma rede real da cooperativa de teste (schema da distribuidora
de referência, ativo da
casa, somente leitura, reusado do item L4-01-b/L4-02-a via `tests/dados/carga_bdgd.py`):

1. laços da cooperativa de teste listados — esperado ≈ 0 numa rede radial de MT (o padrão de distribuição
   é radial por desenho); qualquer laço achado é conferido aqui (contado e citado por par de trechos, não
   apenas "achou algo") e explicado antes de virar cláusula pendente;
2. `POST /api/rede/{id}/tracar` com `tipo=caminho_curto` responde em ≤ 2 s (p95, medido 30 vezes) no maior
   alimentador — mesma régua de desempenho do item irmão L4-02-a.

Regra de desempenho do brief (07/09): medir só com a máquina calma (`uptime`/`free -g` antes) e gravar
`carga_1min`/`ram_livre_gb` ao lado do número — sem carga ao lado o número não vale como prova; com carga
alta, a cláusula fica NÃO MEDIDA, honesta, em vez de reprovar pela casa ou aprovar sem base."""

import json
import subprocess
import time
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import entrar, novo_cliente
from tests.api.test_rls import ids_por_slug
from tests.dados import carga_bdgd
from tests.dados.carga_bdgd import esquema
from tests.dados.carga_bdgd import exigir_esquema as _esq

# Sem o ativo da casa (BDGD real da distribuidora de referência num schema do iagro_sat) não há o que
# medir: o módulo inteiro pula com a razão, em vez de estourar na primeira consulta.
pytestmark = pytest.mark.skipif(
    not esquema(),
    reason="sem PLAT_REDE_REFERENCIA_ESQUEMA: a medida exige a BDGD real da distribuidora de referência",
)

MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / "L4-02-d-lacos-e-caminho-curto.json"


def _carga_da_maquina() -> tuple[float, float]:
    carga_1min = float(Path("/proc/loadavg").read_text().split()[0])
    saida = subprocess.run(["free", "-g"], capture_output=True, text=True, check=True).stdout
    linha_mem = [ln for ln in saida.splitlines() if ln.startswith("Mem:")][0]
    ram_livre_gb = float(linha_mem.split()[6])
    return carga_1min, ram_livre_gb


def _conectar(env, tenant_id, usuario_id):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    with con.cursor() as cur:
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
            "set_config('plat.login', %s, false)",
            (str(tenant_id), str(usuario_id), "medida-l402d"),
        )
    return con


def _gravar_medidas(dados: dict) -> None:
    MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
    anteriores = {}
    if MEDIDAS.exists():
        anteriores = json.loads(MEDIDAS.read_text(encoding="utf-8"))
    anteriores.update(dados)
    MEDIDAS.write_text(json.dumps(anteriores, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                        encoding="utf-8")


@pytest.mark.lento
def test_medida_lacos_e_p95_caminho_curto_maior_alimentador(cred, env):
    carga_1min, ram_livre_gb = _carga_da_maquina()
    if carga_1min > 8:
        _gravar_medidas({
            "lacos_cooperativa_teste": {
                "medido": False,
                "motivo": f"carga_1min={carga_1min} acima de 8 (regra do brief: não medir sob disputa)",
                "carga_1min": carga_1min, "ram_livre_gb": ram_livre_gb,
            },
            "p95_caminho_curto_maior_alimentador": {
                "medido": False,
                "motivo": f"carga_1min={carga_1min} acima de 8 (regra do brief: não medir sob disputa)",
                "carga_1min": carga_1min, "ram_livre_gb": ram_livre_gb,
            },
        })
        pytest.skip(f"carga_1min={carga_1min} > 8, cláusulas registradas como não medidas")

    cliente = novo_cliente()
    login, senha = cred["demo"]
    r = entrar(cliente, "demo", login, senha)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    eu = cliente.get("/api/eu").json()

    con_ids = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    ids = ids_por_slug(con_ids)
    con_ids.close()
    tenant_id, usuario_id = ids["demo"], eu["id"]

    r = cliente.post("/api/rede", json={"nome": "zt-medida-lacos-real", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    con = None
    try:
        from app.rede_utilidades import instalados

        r = cliente.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                         headers={"Content-Type": "application/json"}, timeout=300)
        assert r.status_code == 201, r.text

        con = _conectar(env, tenant_id, usuario_id)
        with con.cursor() as cur:
            carga_bdgd.carregar(cur, tenant_id, rid)
        con.commit()

        r = cliente.post(f"/api/rede/{rid}/topologia/habilitar", timeout=3600)
        assert r.status_code == 201, r.text
        resumo_topo = r.json()

        # --- cláusula 2: laços da rede real inteira ---------------------------------------------------
        t0 = time.perf_counter()
        r = cliente.post(f"/api/rede/{rid}/tracar", json={"tipo": "lacos"}, timeout=300)
        dur_lacos_ms = (time.perf_counter() - t0) * 1000
        assert r.status_code == 200, r.text[:2000]
        resultado_lacos = r.json()
        lacos_detalhe = [
            {"arestas": lc["arestas"], "contagem": lc["contagem"],
             "feicoes_exemplo": [e["feicao_id"] for e in lc["elementos"][:5]]}
            for lc in resultado_lacos["lacos"]
        ]
        _gravar_medidas({
            "topologia_rede_real": resumo_topo,
            "lacos_cooperativa_teste": {
                "medido": True, "contagem": resultado_lacos["contagem"], "duracao_ms": round(dur_lacos_ms, 1),
                "detalhe": lacos_detalhe,
                "explicacao": (
                    "0 laços: rede radial de MT, conforme esperado pelo desenho de distribuição"
                    if resultado_lacos["contagem"] == 0 else
                    f"{resultado_lacos['contagem']} laço(s) achado(s) na rede real — cada um listado em "
                    "'detalhe' com as feições envolvidas para conferência manual no mapa (item não tem "
                    "front-end ainda, ver cláusula frontend_clique_tabela_e2e); pode ser malha real de MT "
                    "(anel de socorro) ou coincidência geométrica de dois trechos dentro da tolerância da "
                    "rede — cada ocorrência precisa ser olhada, não é erro por definição"
                ),
                "carga_1min": carga_1min, "ram_livre_gb": ram_livre_gb,
            },
        })

        # --- cláusula 5: p95 de tipo=caminho_curto no maior alimentador --------------------------------
        with con.cursor() as cur:
            cur.execute(
                f"SELECT ctmt, count(*) AS n FROM {_esq()}.ssdmt WHERE wkt IS NOT NULL "
                "GROUP BY ctmt ORDER BY n DESC LIMIT 1")
            maior = cur.fetchone()
            cur.execute(
                "SELECT ST_X(ST_StartPoint(ST_GeometryN(wkt::geometry, 1))) AS lon, "
                "ST_Y(ST_StartPoint(ST_GeometryN(wkt::geometry, 1))) AS lat "
                f"FROM {_esq()}.ssdmt WHERE ctmt = %s AND wkt IS NOT NULL LIMIT 1",
                (maior["ctmt"],))
            p_origem = cur.fetchone()
            cur.execute(
                "SELECT ST_X(ST_EndPoint(ST_GeometryN(wkt::geometry, 1))) AS lon, "
                "ST_Y(ST_EndPoint(ST_GeometryN(wkt::geometry, 1))) AS lat "
                f"FROM {_esq()}.ssdmt WHERE ctmt = %s AND wkt IS NOT NULL "
                "ORDER BY ST_Length(wkt::geometry) DESC LIMIT 1 OFFSET 1",
                (maior["ctmt"],))
            p_destino = cur.fetchone() or p_origem

        corpo = {
            "tipo": "caminho_curto",
            "pontos_partida": [{"lon": p_origem["lon"], "lat": p_origem["lat"], "tolerancia_m": 5.0}],
            "destino": {"lon": p_destino["lon"], "lat": p_destino["lat"], "tolerancia_m": 5.0},
        }
        tempos_ms = []
        erros = 0
        for _ in range(30):
            t0 = time.perf_counter()
            r = cliente.post(f"/api/rede/{rid}/tracar", json=corpo, timeout=60)
            tempos_ms.append((time.perf_counter() - t0) * 1000)
            if r.status_code not in (200, 404):  # 404=sem_caminho é resposta válida, ainda mede o tempo
                erros += 1
        assert erros == 0, f"{erros} chamada(s) com erro inesperado (não 200 nem 404 sem_caminho)"
        tempos_ms.sort()
        p95 = tempos_ms[int(0.95 * len(tempos_ms)) - 1]
        medida_p95 = {
            "medido": True, "p95_ms": round(p95, 1), "media_ms": round(sum(tempos_ms) / len(tempos_ms), 1),
            "max_ms": round(max(tempos_ms), 1), "n_amostras": len(tempos_ms),
            "ultima_resposta_status": r.status_code,
            "maior_alimentador": {"ctmt": maior["ctmt"], "trechos_mt": maior["n"]},
            "carga_1min": carga_1min, "ram_livre_gb": ram_livre_gb,
        }
        _gravar_medidas({"p95_caminho_curto_maior_alimentador": medida_p95})
        assert p95 <= 2000, (
            f"p95={p95:.1f} ms acima de 2000 ms (carga_1min={carga_1min}, ram_livre_gb={ram_livre_gb})")
    finally:
        if con is not None:
            con.close()
        cliente.delete(f"/api/rede/{rid}")
