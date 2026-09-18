"""Item L4-01-c-importador-bdgd — o importador como JOB, com contrato de dado, contagem conferida
contra o arquivo, unidade do COMP detectada pela razão geodésica e os três órfãos contados e
listados. Provas cláusula por cláusula do portão:

1. contagens da cooperativa de teste iguais ao arquivo (COUNT(*) × GetFeatureCount): a régua é
   `inspecionar()` lido do MESMO GDB, e o número de cabeça do portão (20 CTMT, 5.481 UNTRMT,
   44.268 SSDMT, 29.244 SSDBT, 27.587 UCBT, 60.549 PONNOT) é conferido contra o arquivo, nunca
   contra a carga — se o arquivo mudar, é o portão que está velho, não o teste;
2. km de MT = Σ COMP convertido ± 0,1 % (por isso `comprimento_m` passou a ser o COMP convertido);
3. relatório do contrato com ≥ 30 expectativas AVALIADAS gravado com a importação;
4. UC sem trafo, trafo sem CTMT e PAC sem trecho contados e listados;
5. refutação: trocar a unidade do COMP (× 1000) num GDB de teste e o importador detecta pela razão.

A distribuidora INTEIRA (cláusula 1 em escala) é `lento`: roda fora da suíte rápida, com a medida
gravada em tests/medidas/L4-01-c-importador-bdgd.json (carga da máquina ao lado do número).
"""

# ruff: noqa: F811  (fixtures `rede_eletrica`/`extrato_real` importadas do módulo irmão: padrão do pytest)
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path

import pyogrio
import pytest

from app.rede_utilidades import contrato
from app.rede_utilidades.bdgd import importar, inspecionar
from tests.api.test_rede_modelo import extrato_real, rede_eletrica  # noqa: F401  (fixtures reusadas)
from tests.api.test_rls import contexto
from tests.dados.gerar_bdgd_extrato import fonte, obter_extrato

MEDIDAS = Path("tests/medidas/L4-01-c-importador-bdgd.json")

# números do portão de pronto, conferidos contra o ARQUIVO (não contra a carga)
# CTMT fica fora desta régua de propósito: o arquivo tem 21 linhas e o portão diz 20 — o 21º é o
# alimentador que referencia uma subestação de OUTRO arquivo (interligação real, desvio nomeado
# `alimentador_sem_subestacao` pelo item irmão). O portão contou "alimentadores com subestação".
# Medido em 07/09 com carga 7,98: o teste acusou 21 ≠ 20 e o portão é que estava impreciso.
PORTAO_ARQUIVO = {"UNTRMT": 5481, "SSDMT": 44268, "SSDBT": 29244, "UCBT_tab": 27587, "PONNOT": 60549}
CTMT_ARQUIVO, CTMT_COM_SUBESTACAO = 21, 20


def _carga_maquina() -> dict:
    l1 = os.getloadavg()[0]
    livre = None
    try:
        with open("/proc/meminfo") as f:
            for linha in f:
                if linha.startswith("MemAvailable"):
                    livre = round(int(linha.split()[1]) / 1024 / 1024, 2)
    except OSError:
        pass
    return {"carga_1min": round(l1, 2), "ram_livre_gb": livre, "medido_em": time.strftime("%Y-%m-%dT%H:%M:%S")}


# ---------------------------------------------------------------- cláusula 1 (mecânica) + 2 + 4


def test_comp_em_metros_e_km_de_mt_igual_soma_comp(rede_eletrica, extrato_real):
    """Cláusula 2: Σ comprimento_m das arestas SSDMT = Σ COMP convertido ± 0,1 %. A unidade vem da
    razão Σ COMP / Σ geodésico, medida pelo importador (não configurada)."""
    con, tenant_id, usuario_id, rede_id = rede_eletrica
    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id)
        resultado = importar(cur, tenant_id, rede_id, extrato_real)
        comp = resultado["comp"]["SSDMT"]
        assert comp["unidade"] == "metros", comp
        assert 0.9 <= comp["razao_comp_sobre_geodesico"] <= 1.2, comp  # medido na casa: ≈ 1,024
        cur.execute(
            "SELECT sum(a.comprimento_m) AS km FROM plat.rede_aresta a JOIN plat.rede_tipo t ON t.id = a.tipo_id "
            "WHERE a.rede_id = %s::uuid AND t.codigo = 1 AND t.grupo_id = (SELECT id FROM plat.rede_grupo "
            "WHERE rede_id = %s::uuid AND codigo = 'trecho_de_media_tensao')",
            (rede_id, rede_id),
        )
        soma_arestas = float(cur.fetchone()["km"] or 0)
    # só os trechos que viraram aresta contam dos dois lados: Σ COMP dos inseridos (a régua) vem do arquivo
    df = pyogrio.read_dataframe(extrato_real, layer="SSDMT", read_geometry=False)
    inseridos = resultado["contagens"]["SSDMT"]["inserido"]
    assert inseridos == resultado["contagens"]["SSDMT"]["arquivo"], "todos os SSDMT do extrato entram"
    soma_comp = float(df["COMP"].fillna(0).clip(lower=0).sum()) * comp["fator"]
    assert abs(soma_arestas - soma_comp) / soma_comp <= 0.001, (soma_arestas, soma_comp)


def test_orfaos_contados_e_listados(rede_eletrica, extrato_real):
    """Cláusula 4: os três órfãos vêm com quantidade, exemplos e explicação, e a quantidade é a
    mesma que uma recontagem independente por SQL sobre o que foi gravado."""
    con, tenant_id, usuario_id, rede_id = rede_eletrica
    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id)
        resultado = importar(cur, tenant_id, rede_id, extrato_real)
        orf = resultado["orfaos"]
        for chave in ("uc_sem_trafo", "trafo_sem_ctmt", "pac_sem_trecho"):
            assert set(orf[chave]) >= {"quantidade", "exemplos", "explicacao"}, chave
            assert orf[chave]["quantidade"] >= 0
            assert len(orf[chave]["exemplos"]) <= orf[chave]["quantidade"]
        # recontagem independente do PAC sem trecho
        cur.execute(
            "SELECT count(*) AS n FROM plat.rede_no j LEFT JOIN plat.rede_aresta a "
            "ON a.rede_id = j.rede_id AND (a.no_origem_id = j.id OR a.no_destino_id = j.id) "
            "WHERE j.rede_id = %s::uuid AND j.papel = 'juncao' AND a.id IS NULL",
            (rede_id,),
        )
        assert int(cur.fetchone()["n"]) == orf["pac_sem_trecho"]["quantidade"]
        # auditoria carrega comp e órfãos
        cur.execute("SELECT comp, orfaos FROM plat.rede_importacao WHERE id = %s::uuid", (resultado["importacao_id"],))
        aud = cur.fetchone()
        assert aud["comp"]["SSDMT"]["unidade"] == "metros"
        assert aud["orfaos"]["pac_sem_trecho"]["quantidade"] == orf["pac_sem_trecho"]["quantidade"]


# ---------------------------------------------------------------- cláusula 3: contrato


def test_contrato_avalia_pelo_menos_30_expectativas(extrato_real):
    camadas = {}
    for nome in contrato.CAMADAS_DO_CONTRATO:
        try:
            camadas[nome] = pyogrio.read_dataframe(extrato_real, layer=nome, read_geometry=(nome == "PONNOT"))
        except Exception:
            continue
    rel = contrato.avaliar_contrato(camadas, safra_ano=2024)
    assert rel["total"] == 61, "o YAML da casa tem 61 expectativas"
    assert rel["avaliadas"] >= 30, {
        i["id"]: i["detalhe"] for i in rel["expectativas"] if i["resultado"] == "nao_avaliada"
    }
    # toda expectativa avaliada tem medida; toda não avaliada tem motivo escrito
    for e in rel["expectativas"]:
        if e["resultado"] == "nao_avaliada":
            assert e["detalhe"], e["id"]
        else:
            assert e["medido"] is not None, e["id"]
    # 'informa' nunca falha
    assert all(e["resultado"] != "falha" for e in rel["expectativas"] if e["severidade"] == "informa")
    # o relatório é JSON-seguro (vai para jsonb)
    json.dumps(rel)


def test_contrato_recusa_coluna_faltando_e_cod_id_duplicado():
    import pandas as pd

    untrmt = pd.DataFrame(
        {
            "COD_ID": ["a", "a", "b"],
            "POT_NOM": [45, 45, 0],
            "TIP_TRAFO": ["T", "T", "T"],
            "TIP_UNID": [1, 1, 1],
            "CTMT": ["c1", "c1", "c9"],
            "SIT_ATIV": ["AT"] * 3,
            "X": [-51.0, -51.0, -51.1],
            "Y": [-29.8, -29.8, -29.9],
        }
    )
    ctmt = pd.DataFrame({"COD_ID": ["c1"]})
    rel = contrato.avaliar_contrato({"UNTRMT": untrmt, "CTMT": ctmt}, safra_ano=2024)
    por_id = {e["id"]: e for e in rel["expectativas"]}
    assert por_id["UNTRMT-02"]["resultado"] == "falha" and por_id["UNTRMT-02"]["medido"]["duplicados"] == 2
    assert por_id["UNTRMT-03"]["resultado"] == "falha" and por_id["UNTRMT-03"]["medido"]["sem_placa_ou_zero"] == 1
    assert por_id["UNTRMT-06"]["resultado"] == "falha" and por_id["UNTRMT-06"]["medido"]["sem_alvo"] == 1
    assert por_id["CTMT-01"]["resultado"] == "falha"  # CTMT sem as colunas obrigatórias
    assert rel["bloqueia_falhas"] >= 4


# ---------------------------------------------------------------- cláusula 5: refutação da unidade


def _gdb_com_comp_em_km(origem: str, destino: Path) -> str:
    """Cópia do extrato com COMP dividido por 1000 (o arquivo passa a declarar km): o importador
    tem de detectar pela razão geodésica, sem configuração nenhuma."""
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(origem, destino)
    df = pyogrio.read_dataframe(str(destino), layer="SSDMT")
    df["COMP"] = df["COMP"] / 1000.0
    # o GDB não é regravável em lugar por pyogrio; grava a camada alterada num GPKG ao lado e
    # aponta o importador para ele (o importador lê por camada, o driver é indiferente)
    gpkg = destino.with_suffix(".gpkg")
    if gpkg.exists():
        gpkg.unlink()
    # camadas sem geometria (as *_tab) saem como DataFrame puro: pyogrio grava as duas formas
    for camada in ("SUB", "CTMT", "UNTRMT", "SSDBT", "UCBT_tab", "RAMLIG", "UNSEMT", "UCMT_tab", "PONNOT"):
        try:
            g = pyogrio.read_dataframe(str(origem), layer=camada)
        except Exception:
            continue
        pyogrio.write_dataframe(g, str(gpkg), layer=camada, driver="GPKG", append=gpkg.exists())
    pyogrio.write_dataframe(df, str(gpkg), layer="SSDMT", driver="GPKG", append=True)
    return str(gpkg)


def test_refutacao_comp_em_quilometros_detectado_pela_razao(rede_eletrica, extrato_real, tmp_path):
    con, tenant_id, usuario_id, rede_id = rede_eletrica
    alterado = _gdb_com_comp_em_km(extrato_real, tmp_path / "km.gdb")
    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id)
        resultado = importar(cur, tenant_id, rede_id, alterado, registrar=False)
    comp = resultado["comp"]["SSDMT"]
    assert comp["unidade"] == "quilometros" and comp["fator"] == 1000.0, comp
    assert 0.0009 <= comp["razao_comp_sobre_geodesico"] <= 0.0012, comp
    # e o comprimento gravado continua em METROS (convertido), não em km
    assert comp["soma_comp_convertida_m"] > comp["soma_comp_declarada"] * 100


# ---------------------------------------------------------------- cláusula 1 em ESCALA (lento)


@pytest.mark.lento
def test_cooperativa_inteira_contagens_e_tempo(rede_eletrica):
    """A cooperativa de teste inteira: contagem 1:1 com o arquivo nas camadas do portão e tempo
    medido com a carga da máquina ao lado. Antes do lote em `_gravar_dispositivos` a mesma carga
    passou de 13 min sob disputa (item irmão); a medida aqui é a régua nova."""
    origem = fonte()
    if origem is None or not origem.exists():
        pytest.skip("sem PLAT_REDE_REFERENCIA_GDB apontando o pacote da distribuidora de referência")
    carga = _carga_maquina()
    if carga["carga_1min"] > 8:
        pytest.skip(f"carga {carga['carga_1min']} > 8: medida de tempo não é confiável; rode com a máquina calma")
    gdb = obter_extrato()
    arquivo = inspecionar(gdb)
    for camada, esperado in PORTAO_ARQUIVO.items():
        assert arquivo[camada] == esperado, f"o portão diz {esperado} para {camada}; o arquivo tem {arquivo[camada]}"
    con, tenant_id, usuario_id, rede_id = rede_eletrica
    t0 = time.monotonic()
    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id)
        resultado = importar(cur, tenant_id, rede_id, gdb)
    duracao = time.monotonic() - t0
    for camada in ("SUB", "SSDMT", "UNTRMT", "SSDBT", "UCBT_tab", "UNSEMT", "UCMT_tab"):
        assert resultado["contagens"][camada]["arquivo"] == resultado["contagens"][camada]["inserido"], (
            camada,
            resultado["contagens"][camada],
        )
    ctmt = resultado["contagens"]["CTMT"]
    assert arquivo["CTMT"] == CTMT_ARQUIVO and ctmt["inserido"] == CTMT_COM_SUBESTACAO, (arquivo["CTMT"], ctmt)
    assert ctmt["arquivo"] - ctmt["inserido"] == resultado["desvios"]["alimentador_sem_subestacao"]["quantidade"] == 1
    MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
    MEDIDAS.write_text(
        json.dumps(
            {
                "item": "L4-01-c-importador-bdgd",
                # o NOME do pacote não entra na medida (traz o nome do parceiro); o sha256 identifica
                # o arquivo sem revelá-lo.
                "sha256_zip": hashlib.sha256(origem.read_bytes()).hexdigest()[:16],
                "contagens": resultado["contagens"],
                "comp": resultado["comp"],
                "orfaos": {k: v["quantidade"] for k, v in resultado["orfaos"].items()},
                "duracao_s": round(duracao, 1),
                **carga,
                "referencia_anterior": "item irmão L4-01: > 780 s sob carga ~20, associação por linha",
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    assert duracao < 600, f"{duracao:.0f} s: a cooperativa inteira tem de caber em 10 min"


# ---------------------------------------------------------------- cláusula: a importação é JOB, com barra


@pytest.fixture
def rede_propria(sessao_a):
    """Rede do inquilino demo com o pacote eletrica-br instalado, COMMITADA e com nome único.

    Diferente da fixture `rede_eletrica` (que deixa tudo numa transação aberta da conexão
    compartilhada da suíte): o job roda em conexão PRÓPRIA (ContextoJob.db, como no worker), então a
    rede tem de estar commitada — e o commit não pode ser na conexão compartilhada, que arrastaria
    o trabalho pendente dos outros testes do módulo (achado desta trilha: um `con.commit()` ali
    vazou a rede 'zt-modelo-bdgd' de um teste pulado e derrubou a fixture seguinte por ux_rede_nome).
    Por isso conexão própria, no padrão `_lote` do item irmão L4-04-b."""
    import psycopg2

    from app.rede_utilidades import deposito, instalados
    from app.rede_utilidades import pacote as pacote_mod
    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.test_rls import ids_por_slug

    con = psycopg2.connect(os.environ["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    ids = ids_por_slug(con)
    tenant_id = ids["demo"]
    with con.cursor() as cur:
        contexto(con, tenant_id)
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s AND ativo ORDER BY id LIMIT 1", (tenant_id,))
        usuario_id = cur.fetchone()["id"]
        contexto(con, tenant_id, usuario_id)
        cur.execute(
            "INSERT INTO plat.rede (tenant_id, nome, disciplina, tolerancia_m, dono_id) "
            "VALUES (%s, %s, 'eletrica', 0.05, %s) RETURNING id",
            (tenant_id, f"zt-bdgd-job-{uuid.uuid4().hex[:10]}", usuario_id),
        )
        rede_id = str(cur.fetchone()["id"])
        bruto = instalados.bruto("eletrica-br")
        doc = pacote_mod.ler(bruto)
        deposito.importar(cur, tenant_id, rede_id, doc, usuario_id, hashlib.sha256(bruto).hexdigest(), len(bruto))
    con.commit()
    yield con, tenant_id, usuario_id, rede_id
    apagada = sessao_a.delete(f"/api/rede/{rede_id}")
    assert apagada.status_code in (200, 204), apagada.text
    con.close()


def _gpkg_pacote_sintetico(destino: Path) -> str:
    """Pacote BDGD sintético COMPLETO (todas as camadas que o importador lê), em escala de bancada.

    Os 3 pacotes reais do portão (a casa em `/home/dev/liga/`) não existem neste servidor — a cláusula
    de escala fica na suíte `lento`, que pula sem eles. O que esta função provê é a régua da cláusula
    "importa POR JOB": o mesmo extrato sintético de `gerar_bdgd_unidades` (SUB/CTMT/PONNOT/SSDMT/
    UNTRMT/UCBT_tab, geometria e COMP geodésico de verdade) mais as três camadas que o portão conta
    e faltavam ali — SSDBT (com COMP próprio), PIP e UGBT_tab — gravadas na mesma régua: ligação por
    PN_CON, transformador por UNI_TR_MT, energia em kWh coerente com a potência declarada."""
    import geopandas as gpd
    import pandas as pd
    from pyproj import Geod
    from shapely.geometry import LineString

    from tests.dados import gerar_bdgd_unidades as ger

    caminho = ger.escrever(destino, unidade_comp="m", unidade_ene="kWh")
    geod = Geod(ellps="WGS84")

    # SSDBT: sai da junção do transformador 0 (PN2) para a junção seguinte (PN3), ~195 m ao sul da MT
    seg = LineString([(ger.LON0 + 2 * 0.002, ger.LAT0 - 0.0005), (ger.LON0 + 3 * 0.002, ger.LAT0 - 0.0005)])
    gpd.GeoDataFrame(
        {
            "COD_ID": ["SSDBT0"],
            "PN_CON_1": ["PN2"],
            "PN_CON_2": ["PN3"],
            "CTMT": ["CTMT1"],
            "UNI_TR_MT": ["TRAFO0"],
            "FAS_CON": ["ABCN"],
            "COMP": [round(geod.geometry_length(seg), 6)],
        },
        geometry=[seg], crs=f"EPSG:{ger.SRID}",
    ).to_file(caminho, layer="SSDBT", driver="GPKG")

    # PIP: 3 pontos de iluminação pública na junção do trafo 0; 100 W × ~12 h/dia ≈ 37 kWh/mês
    pip = pd.DataFrame(
        {
            "COD_ID": [f"PIP{i}" for i in range(3)],
            "PN_CON": ["PN2"] * 3,
            "UNI_TR_MT": ["TRAFO0"] * 3,
            "POT_LAMP": [100.0] * 3,
            **{f"ENE_{m:02d}": [37.0] * 3 for m in range(1, 13)},
        }
    )
    gpd.GeoDataFrame(pip, geometry=[None] * 3, crs=f"EPSG:{ger.SRID}").to_file(
        caminho, layer="PIP", driver="GPKG")

    # UGBT_tab: 2 unidades geradoras de baixa tensão na outra ponta do SSDBT; 5 kW × ~4 h sol ≈ 600 kWh/mês
    ugbt = pd.DataFrame(
        {
            "COD_ID": [f"UGBT{i}" for i in range(2)],
            "PN_CON": ["PN3"] * 2,
            "UNI_TR_MT": ["TRAFO0"] * 2,
            "CEG_GD": ["GD.ZT.0001", "GD.ZT.0002"],
            "POT_INST": [5.0] * 2,
            **{f"ENE_{m:02d}": [600.0] * 2 for m in range(1, 13)},
        }
    )
    gpd.GeoDataFrame(ugbt, geometry=[None] * 2, crs=f"EPSG:{ger.SRID}").to_file(
        caminho, layer="UGBT_tab", driver="GPKG")
    return caminho


def test_job_importa_pacote_local_com_barra_de_progresso(rede_propria, sessao_a, tmp_path,
                                                         monkeypatch, request):
    """Cláusula "os pacotes importam POR JOB com barra de progresso", provada pela porta da frente:

    1. enfileira `rede.importar_bdgd` pela rota oficial POST /api/jobs (a mesma que a tela usa);
    2. pega o job pela MESMA função do worker (`plat.job_pegar`, com a role do worker) e roda o corpo
       da tarefa com o `ContextoJob` real — progresso e log passam por `plat.job_progresso`/`plat.job_log`,
       o encanamento da barra, não por um dublê;
    3. termina por `plat.job_terminar` e confere: progresso 100, contagens iguais ao arquivo (PIP e
       UGBT_tab incluídos — o portão os conta e o importador não os tinha), COMP detectado em metros,
       relatório do contrato gravado na auditoria COM o job_id e linha de log da avaliação no job.

    Sem worker externo: a fila da trilha é consumida no processo do teste (o padrão `_lote` do item
    irmão L4-04-b), porque o que se prova é o CORPO do job e a escrita da barra, não o agendador."""
    import psycopg2
    from psycopg2.extras import Json

    from app import settings as cfg
    from app.jobs.contexto_job import ContextoJob
    from app.rede_utilidades import tarefas as tarefas_mod
    from app.schema_ambiente import CursorSchemaAmbiente

    dsn_worker = os.environ.get("PLAT_DSN_WORKER")
    if not dsn_worker:
        pytest.skip("sem PLAT_DSN_WORKER nesta trilha: a prova do job precisa da role do worker")

    con, tenant_id, usuario_id, rede_id = rede_propria
    raiz = tmp_path / "raiz_bdgd"
    raiz.mkdir()
    pacote = _gpkg_pacote_sintetico(raiz / "cooperativa_zt_2024.gpkg")
    monkeypatch.setenv("PLAT_BDGD_RAIZ", str(raiz))
    cfg.obter.cache_clear()
    request.addfinalizer(cfg.obter.cache_clear)

    r = sessao_a.post(
        "/api/jobs",
        json={"tipo": "rede.importar_bdgd",
              "parametros": {"rede_id": rede_id, "caminho": "cooperativa_zt_2024.gpkg"}},
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]

    worker = f"zt-worker-bdgd-{uuid.uuid4().hex[:6]}"
    conw = psycopg2.connect(dsn_worker, cursor_factory=CursorSchemaAmbiente)
    try:
        with conw.cursor() as cur:
            cur.execute("SELECT * FROM plat.job_pegar(%s, %s)", (worker, True))
            pego = cur.fetchone()
        conw.commit()
        assert pego is not None and str(pego["id"]) == job_id, (
            "a fila da trilha tinha outro job pendente na frente do nosso"
        )
        ctx = ContextoJob(dict(pego), tmp_path / "trabalho", worker)
        resultado = tarefas_mod.rede_importar_bdgd(
            ctx, rede_id=uuid.UUID(rede_id), caminho="cooperativa_zt_2024.gpkg")
        with conw.cursor() as cur:
            cur.execute(
                "SELECT plat.job_terminar(%s, %s, 'concluido', %s, NULL, %s) AS ok",
                (job_id, worker, Json(resultado), Json({"origem": "teste"})),
            )
            assert cur.fetchone()["ok"]
        conw.commit()
    finally:
        conw.close()

    assert resultado["conferido"], resultado["contagens"]
    esperado = inspecionar(pacote)  # a régua: GetFeatureCount do MESMO pacote, camada a camada
    for camada, n in (("PIP", 3), ("UGBT_tab", 2), ("UCBT_tab", 30), ("SSDMT", 12),
                      ("SSDBT", 1), ("UNTRMT", 3), ("SUB", 1), ("CTMT", 1)):
        assert esperado[camada] == n, (camada, esperado[camada])
        assert resultado["contagens"][camada] == {"arquivo": n, "inserido": n}, (
            camada, resultado["contagens"][camada])
    assert resultado["comp"]["SSDMT"]["unidade"] == "metros"
    assert resultado["comp"]["SSDBT"]["unidade"] == "metros"

    with con.cursor() as cur:
        contexto(con, tenant_id)
        cur.execute("SELECT progresso, estado, mensagem FROM plat.job WHERE id = %s::uuid", (job_id,))
        j = cur.fetchone()
        assert j["estado"] == "concluido" and j["progresso"] == 100 and j["mensagem"], j
        cur.execute(
            "SELECT nivel, mensagem FROM plat.job_log WHERE job_id = %s::uuid AND mensagem LIKE %s",
            (job_id, "contrato:%"),
        )
        assert cur.fetchone(), "a avaliação do contrato não deixou linha no log do job"
        cur.execute(
            "SELECT contrato, job_id, estado FROM plat.rede_importacao WHERE id = %s::uuid",
            (resultado["importacao_id"],),
        )
        aud = cur.fetchone()
    assert aud["estado"] == "concluida" and str(aud["job_id"]) == job_id
    assert aud["contrato"]["total"] == 61, "o relatório gravado é o do YAML da casa, inteiro"
    assert aud["contrato"]["avaliadas"] >= 30, {
        e["id"]: e["detalhe"] for e in aud["contrato"]["expectativas"] if e["resultado"] == "nao_avaliada"
    }


def test_job_recusa_caminho_fora_da_raiz(rede_propria, tmp_path, monkeypatch, request):
    """O job só lê dentro de PLAT_BDGD_RAIZ (defesa de caminho arbitrário do servidor): um caminho
    fora da raiz falha na hora, sem tocar em banco nem em arquivo."""
    from app import settings as cfg
    from app.jobs.registro import FalhaDefinitiva
    from app.rede_utilidades import tarefas as tarefas_mod

    monkeypatch.setenv("PLAT_BDGD_RAIZ", str(tmp_path / "raiz"))
    cfg.obter.cache_clear()
    request.addfinalizer(cfg.obter.cache_clear)
    (tmp_path / "raiz").mkdir()
    fora = tmp_path / "fora_2024.gpkg"
    _gpkg_pacote_sintetico(fora)
    with pytest.raises(FalhaDefinitiva):
        tarefas_mod._resolver_caminho(str(fora))
    # e sem PLAT_BDGD_RAIZ configurada a importação por caminho local fica desligada (D21)
    monkeypatch.delenv("PLAT_BDGD_RAIZ", raising=False)
    cfg.obter.cache_clear()
    with pytest.raises(FalhaDefinitiva):
        tarefas_mod._resolver_caminho("qualquer.gpkg")
