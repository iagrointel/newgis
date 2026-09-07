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
from pathlib import Path

import pyogrio
import pytest

from app.rede_utilidades import contrato
from app.rede_utilidades.bdgd import importar, inspecionar
from tests.api.test_rede_modelo import extrato_real, rede_eletrica  # noqa: F401  (fixtures reusadas)
from tests.api.test_rls import contexto
from tests.dados.gerar_bdgd_extrato import FONTE, obter_extrato

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
    if not FONTE.exists():
        pytest.skip(f"{FONTE} ausente")
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
                "pacote": FONTE.name,
                "sha256_zip": hashlib.sha256(FONTE.read_bytes()).hexdigest()[:16],
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
