"""API do popup em tempo de execução (item L2-01-d-popup-runtime): `GET /api/camadas/{id}/feicoes/
{fid}/popup`. Depende da bancada `scripts/mapa_demo_popup.py criar`; sem ela SALTA (nunca passa por
omissão, mesmo padrão de `tests/api/test_mapa_api.py`)."""

import datetime
import os
import time

import pytest


def _ram_livre_gb() -> float:
    """MemAvailable de /proc/meminfo, sem dependência nova (psutil não está no venv)."""
    with open("/proc/meminfo", encoding="ascii") as f:
        for linha in f:
            if linha.startswith("MemAvailable:"):
                return round(int(linha.split()[1]) / 1024 / 1024, 2)
    return -1.0

BANCADA = "(L2-01-d"


def _camadas(sessao):
    r = sessao.get("/api/mapa/camadas")
    assert r.status_code == 200, r.text
    return r.json()["camadas"]


@pytest.fixture(scope="module")
def bancada(sessao_a):
    camadas = [c for c in _camadas(sessao_a) if BANCADA in c["titulo"]]
    if not camadas:
        pytest.skip("bancada do item ausente: rode scripts/mapa_demo_popup.py criar")
    return camadas


@pytest.fixture(scope="module")
def camada_pontos(bancada):
    return next(c for c in bancada if c["titulo"].startswith("mapa-popup ("))


@pytest.fixture(scope="module")
def camada_area(bancada):
    return next(c for c in bancada if "area" in c["titulo"])


def test_ficha_da_camada_traz_popup_normalizado(camada_pontos):
    p = camada_pontos["popup"]
    nomes = {c["nome"] for c in p["campos"]}
    assert {"nome", "valor_numero", "data_evento_ms", "preco", "site", "foto", "nota_servidor"} <= nomes
    servidor = [c for c in p["campos"] if c["nome"] == "nota_servidor"][0]
    assert servidor["servidor"] is True
    assert p["tem_servidor"] is True


def test_campo_servidor_vem_da_tabela_companheira_nao_do_tile(sessao_a, camada_pontos):
    r = sessao_a.get(f"/api/camadas/{camada_pontos['id']}/feicoes/1/popup")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["campos_servidor"]["nota_servidor"]["bruto"] == "nota do servidor para o fid 1"
    # fid > 5 nunca ganhou linha na tabela companheira (scripts/mapa_demo_popup.py só grava fid<=5)
    r2 = sessao_a.get(f"/api/camadas/{camada_pontos['id']}/feicoes/10/popup")
    assert r2.status_code == 200, r2.text
    assert r2.json()["campos_servidor"]["nota_servidor"]["bruto"] is None


def test_expressao_de_area_bate_com_st_area_geografica(sessao_a, conexao_plat_app, camada_area):
    """5 feições: a expressão `$area_m2 / 10000` do popup contra ST_Area(geography(geom))/10000 medido
    direto no banco (mesma fórmula que a rota usa) — tolerância 0,1% (a cláusula literal do portão)."""
    with conexao_plat_app.cursor() as cur:
        # plat.auth_login é SECURITY DEFINER (mesma função que o login usa) — não exige contexto de
        # inquilino antes de rodar, o que uma SELECT direta em plat.item (RLS) exigiria.
        cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()
        cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(adm["tenant_id"]),))
        cur.execute("SELECT set_config('plat.usuario_id', %s, false)", (str(adm["usuario_id"]),))
        cur.execute("SELECT dados->>'schema' AS esquema, dados->>'tabela' AS tabela FROM plat.item "
                    "WHERE id = %s::uuid", (camada_area["id"],))
        linha = cur.fetchone()
        assert linha, "camada da bancada não apareceu para o contexto do inquilino demo"
        cur.execute(f'SELECT fid, ST_Area(geography(geom)) / 10000.0 AS ha '
                    f'FROM "{linha["esquema"]}"."{linha["tabela"]}" ORDER BY fid LIMIT 5')
        esperado = {r["fid"]: r["ha"] for r in cur.fetchall()}
    assert len(esperado) == 5
    for fid, ha_esperado in esperado.items():
        r = sessao_a.get(f"/api/camadas/{camada_area['id']}/feicoes/{fid}/popup")
        assert r.status_code == 200, r.text
        ha_obtido = r.json()["expressoes"]["area_ha"]["bruto"]
        erro_relativo = abs(ha_obtido - ha_esperado) / ha_esperado
        assert erro_relativo < 0.001, (fid, ha_obtido, ha_esperado, erro_relativo)


def test_camada_de_outro_inquilino_e_404(sessao_b, camada_pontos):
    r = sessao_b.get(f"/api/camadas/{camada_pontos['id']}/feicoes/1/popup")
    assert r.status_code == 404, r.text


def test_feicao_inexistente_e_404(sessao_a, camada_pontos):
    r = sessao_a.get(f"/api/camadas/{camada_pontos['id']}/feicoes/999999/popup")
    assert r.status_code == 404, r.text


def test_fuso_por_query_muda_a_data_formatada_sem_mexer_no_inquilino(sessao_a, camada_pontos):
    r_utc = sessao_a.get(f"/api/camadas/{camada_pontos['id']}/feicoes/1/popup?fuso=UTC")
    r_sp = sessao_a.get(f"/api/camadas/{camada_pontos['id']}/feicoes/1/popup?fuso=America/Sao_Paulo")
    assert r_utc.status_code == 200 and r_sp.status_code == 200
    assert r_utc.json()["fuso"] == "UTC"
    assert r_sp.json()["fuso"] == "America/Sao_Paulo"


def test_p95_da_consulta_ao_servidor(sessao_a, camada_pontos, medida):
    """cláusula de desempenho do portão: p95 <= 100 ms. Medida só grava com PLAT_GRAVAR_MEDIDAS=1
    (regra do brief comum) e só quando a máquina está calma o bastante para o número dizer algo
    sobre o PRODUTO, não sobre a disputa da máquina (regra de 07/09)."""
    carga_1min = os.getloadavg()[0]
    if carga_1min > 8:
        pytest.skip(f"carga_1min={carga_1min:.1f} > 8: não medir desempenho sob disputa (regra do brief)")
    tempos = []
    for _ in range(50):
        t0 = time.perf_counter()
        r = sessao_a.get(f"/api/camadas/{camada_pontos['id']}/feicoes/1/popup")
        tempos.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200
    tempos.sort()
    p95 = tempos[int(len(tempos) * 0.95) - 1]
    valor = {
        "p95_ms": round(p95, 2),
        "carga_1min": round(carga_1min, 2),
        "ram_livre_gb": _ram_livre_gb(),
        "medido_em": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    medida("L2-01-d-popup-runtime")(
        "p95_consulta_servidor", valor, "ms (+ carga/ram ao lado, regra do brief comum)",
        "pytest tests/api/test_mapa_popup_api.py::test_p95_da_consulta_ao_servidor -q")
    assert p95 <= 100, (p95, tempos)
