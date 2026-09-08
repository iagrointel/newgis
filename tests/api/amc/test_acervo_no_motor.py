"""Item L6-04-acervo-no-motor: uma camada do acervo assinada é usável como fator no motor L3 SEM CÓPIA (o
extrator lê a view de `plat_acervo`, nunca a tabela de origem), e o resultado guarda fonte_id, sha256 e
contagem na proveniência. Depende de L6-01-b-view-so-leitura (PARCIAL) e L3-01-c-extracao-fator (PARCIAL) —
os módulos que faltavam (`app/amc/*`, `app/acervo/publicacao.py`) foram trazidos para este ramo pelo merge
dos worktrees `wt/amc`, `wt/extrat` e `wt/t601b` (ver handoff do item).

Três camadas REAIS, já ingeridas nesta casa (nunca dado sintético), pequenas o bastante para caber num
teste: `public.icmbio_unidades_conservacao` (UC, 346 polígonos), `public.funai_terras_indigenas` (TI, 655
polígonos) e `public.hidro_nacional_bc250` (hidrografia, 1,6 mi de linhas, com índice GiST — por isso ela e
não `car_hidrografia`, 3,86 mi de linhas SEM índice espacial, teria estourado o relógio do teste). A área de
Santa Catarina em torno do Parque Nacional da Serra do Itajaí, da Floresta Nacional de Ibirama e da Terra
Indígena Águas Claras foi escolhida por medição prévia (bbox -49.5,-27.4,-48.9,-26.9): 2 UC, 1 TI e 1.101
feições de hidrografia — dado real o bastante para o motor produzir número, não zero por falta de dado.

Registro do acervo é SEMPRE por schema de trilha (`plat_til604acervo` aqui via PLAT_SCHEMA), nunca a tabela
`plat.acervo_camada` de produção — mesma regra e mesmo padrão de tests/api/test_acervo_publicacao.py.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from app import db as banco
from app.amc import executor
from app.jobs.registro import FalhaDefinitiva
from tests.api.amc.test_unidades import ContextoDeTeste

ROOT = Path(__file__).resolve().parents[3]
PUBLICAR = ROOT / "scripts" / "acervo_publicar.py"
PREFIXO = "zt-l604"

CAMADA_UC = "icmbio-mma-unidades-de-conservacao-cnuc/public.icmbio_unidades_conservacao"
CAMADA_TI = "funai-terras-indigenas/public.funai_terras_indigenas"
CAMADA_HIDRO = "ibge-bc250-hidrografia-nacional/public.hidro_nacional_bc250"
VIEW_UC, VIEW_TI, VIEW_HIDRO = "public_icmbio_unidades_conservacao", "public_funai_terras_indigenas", \
    "public_hidro_nacional_bc250"

# bbox medido em 07/09/2026 (2 UC + 1 TI + 1.101 feições de hidrografia; ver docstring do módulo)
BBOX_UC = "PARQUE NACIONAL DA SERRA DO ITAJAÍ"
CENTRO_DENTRO_UC = (-49.18, -27.10)
CENTRO_DENTRO_TI = (-48.939, -27.373)
CENTRO_FORA = (-49.28, -27.35)
LADO = 0.01  # ~1,1 km


def _psql(sql: str, timeout: int = 60) -> str:
    cmd = ["sudo", "-u", "postgres", "psql", "-d", os.environ.get("PLAT_BANCO", "iagro_sat"),
           "-X", "-q", "-tA", "-v", "ON_ERROR_STOP=1", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _schema() -> str:
    return os.environ.get("PLAT_SCHEMA", "plat")


def _quadrado(cx: float, cy: float, lado: float = LADO) -> dict:
    m = lado / 2
    return {"type": "Polygon", "coordinates": [[[cx - m, cy - m], [cx + m, cy - m], [cx + m, cy + m],
                                                [cx - m, cy + m], [cx - m, cy - m]]]}


def _feicoes_teste() -> dict:
    """4 unidades: dentro da UC, dentro da TI, e fora das duas — a hidrografia é densa o bastante para não
    precisar de unidade dedicada (toda unidade tem alguma linha próxima dentro da caixa carregada)."""
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "id": "u_uc", "geometry": _quadrado(*CENTRO_DENTRO_UC), "properties": {}},
            {"type": "Feature", "id": "u_ti", "geometry": _quadrado(*CENTRO_DENTRO_TI), "properties": {}},
            {"type": "Feature", "id": "u_fora", "geometry": _quadrado(*CENTRO_FORA), "properties": {}},
        ],
    }


def _registrar_camada(camada_id: str, schema_nome: str, tabela: str, coluna_geom: str, srid: int,
                      colunas: list[str]) -> None:
    s = _schema()
    # COUNT(*) exato, nunca reltuples (regra da casa) — mas hidro_nacional_bc250 tem 1,6 mi de linhas e a
    # máquina desta trilha está sob disputa pesada de outras sessões: timeout maior só para esta consulta.
    exatas = _psql(f"SELECT count(*) FROM {schema_nome}.{tabela}", timeout=240)
    lista = ",".join(f"'{c}'" for c in colunas)
    _psql(
        f"""INSERT INTO {s}.acervo_camada (acervo_camada_id, fonte_id, servidor, banco, schema_nome, tabela,
              coluna_geom, srid, tipo_geom, colunas_expostas, colunas_bloqueadas, linhas_exatas,
              linhas_contadas_em, linhas_estimadas, estado)
            VALUES ('{camada_id}', '{camada_id.split("/")[0]}', 'vultr', 'iagro_sat', '{schema_nome}', '{tabela}',
              '{coluna_geom}', {srid}, 'GEOMETRY', ARRAY[{lista}], ARRAY[]::text[], {exatas}, current_date,
              {exatas}, 'exposta')
            ON CONFLICT (acervo_camada_id) DO UPDATE SET estado = 'exposta',
              colunas_expostas = EXCLUDED.colunas_expostas, linhas_exatas = EXCLUDED.linhas_exatas"""
    )


@pytest.fixture(scope="module")
def camadas_publicadas():
    """Registra as 3 camadas REAIS (schema da trilha) e publica de verdade (scripts/acervo_publicar.py)."""
    if _psql("SELECT to_regclass('public.icmbio_unidades_conservacao') IS NOT NULL") != "t":
        pytest.skip("public.icmbio_unidades_conservacao não existe nesta base")
    _registrar_camada(CAMADA_UC, "public", "icmbio_unidades_conservacao", "geom", 4326,
                      ["ogc_fid", "nomeuc", "siglacateg"])
    _registrar_camada(CAMADA_TI, "public", "funai_terras_indigenas", "geom", 4326,
                      ["ogc_fid", "terrai_nome"])
    _registrar_camada(CAMADA_HIDRO, "public", "hidro_nacional_bc250", "geom", 4326, ["ogc_fid", "nome"])
    r = subprocess.run(
        ["sudo", "-u", "postgres", "python3", str(PUBLICAR), "--schema", _schema(),
         "--banco", os.environ.get("PLAT_BANCO", "iagro_sat")],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr
    yield {"uc": VIEW_UC, "ti": VIEW_TI, "hidro": VIEW_HIDRO}


def _fator(fid: str, camada_id: str, extrator: str, minimo: float, maximo: float, direcao: str, peso: float,
          unidade: str, top_direcao: str) -> dict:
    return {
        "id": fid, "nome": f"fator de teste {fid}", "fonte": f"acervo: {camada_id}", "unidade": unidade,
        "direcao": top_direcao, "base": "engenharia",
        "camada": {"tipo": "acervo", "id": camada_id},
        "extrator": {"tipo": extrator},
        "transformacao": {"tipo": "linear", "minimo": minimo, "maximo": maximo, "direcao": direcao},
        "peso": peso,
    }


def _modelo_3_fatores_acervo() -> dict:
    return {
        "esquema": "amc_modelo.v1",
        "nome": f"{PREFIXO} modelo com 3 fatores do acervo",
        "descricao": "UC, TI e hidrografia lidos direto da view do acervo (item L6-04-acervo-no-motor)",
        "combinador": {"tipo": "soma_ponderada_normalizada"},
        "dado_ausente": "excluir_fator",
        "fatores": [
            _fator("uc", CAMADA_UC, "poligono_fracao_area", 0, 1, "decrescente", 1.0, "fracao", "menor_melhor"),
            _fator("ti", CAMADA_TI, "poligono_fracao_area", 0, 1, "decrescente", 1.0, "fracao", "menor_melhor"),
            _fator("hidro", CAMADA_HIDRO, "linha_distancia_mais_proxima", 0, 2000, "crescente", 1.0, "m",
                  "maior_melhor"),
        ],
    }


@pytest.fixture
def assinaturas_a(camadas_publicadas, sessao_a):
    for v in (VIEW_UC, VIEW_TI, VIEW_HIDRO):
        r = sessao_a.post(f"/api/acervo/camadas/{v}/assinatura")
        assert r.status_code == 201, r.text
    yield
    for v in (VIEW_UC, VIEW_TI, VIEW_HIDRO):
        sessao_a.delete(f"/api/acervo/camadas/{v}/assinatura")


def _tenant_id(slug: str) -> int:
    return int(_psql(f"SELECT id FROM {_schema()}.tenant WHERE slug = '{slug}'"))


def _criar_modelo_e_conjunto(sessao):
    r = sessao.post("/api/amc/modelos", json={"definicao": _modelo_3_fatores_acervo()})
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    r = sessao.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} grade", "tipo": "feicoes",
                                                "feicoes": _feicoes_teste()})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["estado"] == "pronto"  # feições são síncronas
    return mid, cid


# ================================================================ cláusula 1: modelo com 3 fatores do acervo roda


def test_modelo_com_3_fatores_do_acervo_roda_sobre_grade_de_teste(assinaturas_a, sessao_a):
    mid, cid = _criar_modelo_e_conjunto(sessao_a)
    r = sessao_a.post("/api/amc/execucoes", json={"modelo_id": mid, "conjunto_id": cid})
    assert r.status_code == 201, r.text
    execucao = r.json()
    eid = execucao["id"]
    assert execucao["job_id"], "execução com fator do acervo tem de enfileirar o job amc.executar"

    tenant_id = _tenant_id("demo")
    ctx = ContextoDeTeste(tenant_id)
    resultado = executor.executar(ctx, eid)
    assert resultado["estado"] == "concluida"
    assert resultado["fatores_acervo"] == 3
    assert ctx.progressos[-1][0] == 100

    r = sessao_a.get(f"/api/amc/execucoes/{eid}")
    assert r.status_code == 200 and r.json()["estado"] == "concluida"

    r = sessao_a.get(f"/api/amc/execucoes/{eid}/resultados")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["total"] == 3, "as 3 unidades da grade de teste têm de ter resultado"
    por_unidade = {x["unidade_id"]: x for x in corpo["resultados"]}
    for uid in ("u_uc", "u_ti", "u_fora"):
        assert uid in por_unidade
        assert por_unidade[uid]["favorabilidade"] is not None, f"{uid} sem favorabilidade"
        assert 0.0 <= por_unidade[uid]["favorabilidade"] <= 100.0

    # a unidade DENTRO da UC tem fração de UC = 1 (o quadrado de teste está inteiro dentro do parque) e por
    # isso favorabilidade do fator 'uc' pior que a da unidade de fora — provado no fator bruto, não só no
    # combinado (a combinação também mistura hidrografia, que varia por unidade).
    with banco.db(banco.Contexto(tenant_id, 0, "teste")) as cur:
        cur.execute("SELECT unidade_id, fator, valor, cobertura FROM plat.amc_fator_bruto WHERE execucao_id = %s::uuid "
                    "ORDER BY unidade_id, fator", (eid,))
        brutos = {(r_["unidade_id"], r_["fator"]): r_ for r_ in cur.fetchall()}
    assert brutos[("u_uc", "uc")]["valor"] == pytest.approx(1.0, abs=1e-6), \
        "unidade inteira dentro do parque tem de ter fração de UC = 1"
    assert brutos[("u_fora", "uc")]["valor"] == pytest.approx(0.0, abs=1e-6)
    # TI Águas Claras não é um retângulo: o quadrado de teste (centrado dentro do polígono) fica MAJORITARIAMENTE
    # dentro, mas não 100% (a borda real do polígono corta o quadrado) — valor real medido, não o ideal 1,0.
    assert brutos[("u_ti", "ti")]["valor"] > 0.5, \
        f"unidade centrada dentro da TI tem de ter fração de TI majoritária, veio {brutos[('u_ti', 'ti')]['valor']!r}"
    assert brutos[("u_fora", "ti")]["valor"] == pytest.approx(0.0, abs=1e-6)
    for uid in ("u_uc", "u_ti", "u_fora"):
        assert brutos[(uid, "hidro")]["valor"] is not None, f"{uid}: distância à hidrografia sem dado"
        assert brutos[(uid, "hidro")]["valor"] >= 0


# ================================================================ cláusula 2: proveniência mostra fonte_id e contagem


def test_proveniencia_mostra_fonte_id_e_contagem(assinaturas_a, sessao_a):
    mid, cid = _criar_modelo_e_conjunto(sessao_a)
    r = sessao_a.post("/api/amc/execucoes", json={"modelo_id": mid, "conjunto_id": cid})
    assert r.status_code == 201, r.text
    execucao = r.json()
    r2 = sessao_a.get(f"/api/amc/execucoes/{execucao['id']}")
    camadas = r2.json()["camadas"]
    assert len(camadas) == 3
    por_id = {c["id"]: c for c in camadas}
    esperado = {
        CAMADA_UC: "icmbio-mma-unidades-de-conservacao-cnuc",
        CAMADA_TI: "funai-terras-indigenas",
        CAMADA_HIDRO: "ibge-bc250-hidrografia-nacional",
    }
    for camada_id, fonte_id in esperado.items():
        c = por_id[camada_id]
        assert c["fonte_id"] == fonte_id, c
        assert isinstance(c["contagem"], int) and c["contagem"] > 0, c
        assert c["contagem_origem"] == "acervo.linhas_exatas"
        assert c["tipo"] == "acervo"


# ================================================================ cláusula 3: revogar impede execução nova


def test_revogar_assinatura_impede_nova_execucao_mas_nao_apaga_resultado_antigo(assinaturas_a, sessao_a):
    mid, cid = _criar_modelo_e_conjunto(sessao_a)
    r = sessao_a.post("/api/amc/execucoes", json={"modelo_id": mid, "conjunto_id": cid})
    assert r.status_code == 201, r.text
    eid_antiga = r.json()["id"]
    tenant_id = _tenant_id("demo")
    ctx = ContextoDeTeste(tenant_id)
    executor.executar(ctx, eid_antiga)
    with banco.db(banco.Contexto(tenant_id, 0, "teste")) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.amc_resultado WHERE execucao_id = %s::uuid", (eid_antiga,))
        assert cur.fetchone()["n"] == 3, "a execução antiga tem de ter resultado antes de revogar nada"

    r = sessao_a.delete(f"/api/acervo/camadas/{VIEW_UC}/assinatura")
    assert r.status_code == 200, r.text
    try:
        mid2, cid2 = _criar_modelo_e_conjunto(sessao_a)
        r = sessao_a.post("/api/amc/execucoes", json={"modelo_id": mid2, "conjunto_id": cid2})
        assert r.status_code == 422, r.text
        corpo = r.json()
        assert corpo["erro"] == "sem_assinatura", corpo
        assert CAMADA_UC in json.dumps(corpo)
    finally:
        sessao_a.post(f"/api/acervo/camadas/{VIEW_UC}/assinatura")  # devolve para o resto do módulo

    with banco.db(banco.Contexto(tenant_id, 0, "teste")) as cur:
        cur.execute("SELECT count(*) AS n, count(favorabilidade) AS com_valor FROM plat.amc_resultado "
                    "WHERE execucao_id = %s::uuid", (eid_antiga,))
        r_ = cur.fetchone()
        assert r_["n"] == 3 and r_["com_valor"] == 3, \
            "revogar a assinatura de uma camada NÃO apaga o resultado de uma execução já concluída"
        cur.execute("SELECT estado FROM plat.amc_execucao WHERE id = %s::uuid", (eid_antiga,))
        assert cur.fetchone()["estado"] == "concluida"


# ================================================================ refutação: revogar DURANTE o job


def test_refutacao_revogar_assinatura_durante_o_job_falha_com_mensagem_nunca_zeros(assinaturas_a, sessao_a,
                                                                                    monkeypatch):
    """O adversário do item: revoga a assinatura de 'ti' bem no meio da extração de 'uc' (a chamada real a
    vetorial.extrair, não uma simulação de tempo) — quando o laço chega ao fator 'ti', a checagem de novo de
    `plat.acervo_pode_ler` tem de ver a revogação e abortar. Nunca deve sobrar resultado com zero."""
    mid, cid = _criar_modelo_e_conjunto(sessao_a)
    r = sessao_a.post("/api/amc/execucoes", json={"modelo_id": mid, "conjunto_id": cid})
    assert r.status_code == 201, r.text
    eid = r.json()["id"]

    # o executor importa `vetorial` DENTRO da função que extrai vetor (geopandas não está na venv da unidade
    # systemd), então o remendo é no próprio módulo, não num atributo do executor
    from app.amc import vetorial as mod_vetorial

    original = mod_vetorial.extrair
    revogado = {"feito": False}

    def _extrair_e_revogar(unidades, camada, tipo, srid, parametros=None):
        saida = original(unidades, camada, tipo, srid, parametros)
        if tipo == "vetor_fracao_area" and not revogado["feito"]:
            # simula o adversário revogando a assinatura de 'ti' logo depois de 'uc' terminar de extrair —
            # ANTES de o job chegar a conferir a assinatura de 'ti' outra vez.
            r2 = sessao_a.delete(f"/api/acervo/camadas/{VIEW_TI}/assinatura")
            assert r2.status_code == 200, r2.text
            revogado["feito"] = True
        return saida

    monkeypatch.setattr(mod_vetorial, "extrair", _extrair_e_revogar)
    tenant_id = _tenant_id("demo")
    ctx = ContextoDeTeste(tenant_id)
    try:
        with pytest.raises(FalhaDefinitiva) as exc:
            executor.executar(ctx, eid)
        assert "revogad" in str(exc.value), str(exc.value)
        assert VIEW_TI.replace("public_", "").replace("_", "-") or True  # a mensagem cita o id da camada, não a view
        assert CAMADA_TI in str(exc.value), str(exc.value)
    finally:
        monkeypatch.setattr(mod_vetorial, "extrair", original)
        sessao_a.post(f"/api/acervo/camadas/{VIEW_TI}/assinatura")  # devolve para o resto do módulo

    with banco.db(banco.Contexto(tenant_id, 0, "teste")) as cur:
        cur.execute("SELECT estado, erro FROM plat.amc_execucao WHERE id = %s::uuid", (eid,))
        exe = cur.fetchone()
        assert exe["estado"] == "falhou", exe
        assert exe["erro"] and "revogad" in exe["erro"], exe
        cur.execute("SELECT count(*) AS n FROM plat.amc_resultado WHERE execucao_id = %s::uuid", (eid,))
        assert cur.fetchone()["n"] == 0, "o job falhou: NUNCA pode ter gravado resultado, nem zero"
        cur.execute("SELECT count(*) AS n FROM plat.amc_fator_bruto WHERE execucao_id = %s::uuid", (eid,))
        assert cur.fetchone()["n"] == 0, "o job falhou: NUNCA pode ter gravado fator bruto"
