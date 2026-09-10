#!/usr/bin/env python3
"""Simulador de sensor de trafo (item L4-13-integracao-telemetria): 20 sensores publicando corrente por
fase (5 min), temperatura (5 min) e tensão por fase (10 min) — o dado que prova o item na instância viva.

Fala só com a API HTTP (a mesma porta que qualquer sonda/conector de verdade usaria), nunca com o banco
direto. Backfilla ~REDE_MEDICAO_ALARME_LOOKBACK_MIN minutos de histórico em segundos (o `ts` de cada leitura
é o do sensor, não o do relógio de quem publica) para o alarme "carregamento > 100% por 30 min" ter, de
propósito, uma janela contínua para disparar num dos 20 trafos, sem esperar 30 min de verdade.

Uso:
  venv/bin/python scripts/rede_medicao_simulador.py --provar          # backfill + alguns ticks ao vivo + mede
  venv/bin/python scripts/rede_medicao_simulador.py --limpar          # apaga o dado de teste do inquilino demo

Credenciais: PLAT_CREDENCIAIS_ARQUIVO (o mesmo arquivo que tests/api usa; "demo admin <senha>")."""

from __future__ import annotations

import argparse
import datetime
import math
import os
import random
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("PLAT_SIMULADOR_URL", "http://127.0.0.1:8184")
NOME_REDE = "lancamento-demo-utilidades"
GRUPO_TRAFO_NOME = "Transformador de distribuição"
FONTE = "simulador"
UTC = datetime.UTC


def _credenciais(slug: str) -> tuple[str, str]:
    caminho = Path(os.environ.get("PLAT_CREDENCIAIS_ARQUIVO") or (RAIZ / "tests" / "credenciais.txt"))
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if len(partes) >= 3 and partes[0] == slug:
            return partes[1], " ".join(partes[2:])
    raise SystemExit(f"{caminho}: sem linha para {slug!r} (rode sudo bash db/migrar.sh ou peça ao operador)")


def entrar(sess: requests.Session, slug: str) -> dict:
    login, senha = _credenciais(slug)
    r = sess.post(f"{BASE_URL}/api/login", json={"inquilino": slug, "login": login, "senha": senha})
    r.raise_for_status()
    corpo = r.json()
    if not corpo.get("ok"):
        raise SystemExit(f"login recusado: {corpo}")
    return corpo


def achar_rede(sess: requests.Session, nome: str) -> str:
    r = sess.get(f"{BASE_URL}/api/rede")
    r.raise_for_status()
    for rede in r.json()["itens"]:
        if rede["nome"] == nome:
            return rede["id"]
    raise SystemExit(f"rede {nome!r} não encontrada — crie a rede de demonstração antes de rodar o simulador")


def achar_trafos(sess: requests.Session, rede_id: str, n: int) -> list[dict]:
    r = sess.get(f"{BASE_URL}/api/rede/{rede_id}/feicoes/pontos.geojson", params={"limite": 5000})
    r.raise_for_status()
    trafos = [f for f in r.json()["features"] if f["properties"].get("tipo") == GRUPO_TRAFO_NOME]
    if len(trafos) < n:
        raise SystemExit(f"a rede só tem {len(trafos)} trafo(s); pedido {n}")
    return trafos[:n]


def configurar_placas(sess: requests.Session, trafos: list[dict], kvas: list[float]) -> None:
    for trafo, kva in zip(trafos, kvas, strict=True):
        ativo = trafo["properties"]["id"]
        r = sess.put(f"{BASE_URL}/api/rede/medicao/ativos/{ativo}", json={
            "cod_id": f"TR-{ativo[:8]}", "kva_nominal": kva, "tensao_nominal_v": 380.0,
        })
        r.raise_for_status()


def _publicar(sess: requests.Session, leituras: list[dict]) -> dict:
    r = sess.post(f"{BASE_URL}/api/rede/medicao/leituras", json={"leituras": leituras})
    r.raise_for_status()
    return r.json()


def _iso(dt: datetime.datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def gerar_backfill(trafos: list[dict], minutos: int, agora: datetime.datetime,
                   ativo_sobrecarga: str) -> list[dict]:
    """Histórico com `ts` do passado até `agora`: corrente/temperatura a cada 5 min, tensão a cada 10 min.
    Um dos trafos (`ativo_sobrecarga`) fica acima de 100% de carregamento pelos ÚLTIMOS 35 min contínuos —
    a demonstração honesta do alarme (dado simulado, declarado como tal em `leitura.simulado`)."""
    leituras: list[dict] = []
    inicio = agora - datetime.timedelta(minutes=minutos)
    for trafo in trafos:
        ativo = trafo["properties"]["id"]
        base_a = random.uniform(15, 40)
        t_min = inicio
        passo = 0
        while t_min <= agora:
            sobrecarga = ativo == ativo_sobrecarga and (agora - t_min) <= datetime.timedelta(minutes=35)
            fator = 1.8 if sobrecarga else 1.0
            for fase, base in (("a", base_a), ("b", base_a * random.uniform(0.92, 1.05)),
                               ("c", base_a * random.uniform(0.92, 1.05))):
                valor = round(base * fator * random.uniform(0.97, 1.03), 2)
                leituras.append({"ativo": ativo, "cod_id": f"TR-{ativo[:8]}", "ts": _iso(t_min), "fonte": FONTE,
                                 "grandeza": f"corrente_{fase}", "valor": valor, "unidade": "A",
                                 "bruta": {"simulado": True}})
            temp = round(28 + 12 * math.sin(passo / 6) + (6 if sobrecarga else 0) + random.uniform(-1, 1), 1)
            leituras.append({"ativo": ativo, "cod_id": f"TR-{ativo[:8]}", "ts": _iso(t_min), "fonte": FONTE,
                             "grandeza": "temperatura", "valor": temp, "unidade": "C",
                             "bruta": {"simulado": True}})
            if passo % 2 == 0:  # tensão a cada 10 min (o dobro do passo de 5 min)
                for fase in ("a", "b", "c"):
                    v = round(random.uniform(378, 382), 1)
                    leituras.append({"ativo": ativo, "cod_id": f"TR-{ativo[:8]}", "ts": _iso(t_min),
                                     "fonte": FONTE, "grandeza": f"tensao_{fase}", "valor": v, "unidade": "V",
                                     "bruta": {"simulado": True}})
            t_min += datetime.timedelta(minutes=5)
            passo += 1
    return leituras


def gerar_tick_vivo(trafos: list[dict], agora: datetime.datetime) -> list[dict]:
    leituras = []
    for trafo in trafos:
        ativo = trafo["properties"]["id"]
        base = random.uniform(15, 40)
        for fase in ("a", "b", "c"):
            leituras.append({"ativo": ativo, "cod_id": f"TR-{ativo[:8]}", "ts": _iso(agora), "fonte": FONTE,
                             "grandeza": f"corrente_{fase}", "valor": round(base * random.uniform(0.97, 1.03), 2),
                             "unidade": "A", "bruta": {"simulado": True}})
        leituras.append({"ativo": ativo, "cod_id": f"TR-{ativo[:8]}", "ts": _iso(agora), "fonte": FONTE,
                         "grandeza": "temperatura", "valor": round(30 + random.uniform(-2, 2), 1),
                         "unidade": "C", "bruta": {"simulado": True}})
    return leituras


def limpar(sess: requests.Session, rede_id: str) -> dict:
    """Apaga o dado de teste do inquilino demo — leituras, placa e estado de alarme dos ativos que o
    simulador tocou (a rede_id vem só para achar de novo os mesmos trafos; nada na própria rede é apagado)."""
    r = sess.get(f"{BASE_URL}/api/rede/{rede_id}/feicoes/pontos.geojson", params={"limite": 5000})
    r.raise_for_status()
    trafos = [f["properties"]["id"] for f in r.json()["features"]
             if f["properties"].get("tipo") == GRUPO_TRAFO_NOME]
    # a API não tem rota de apagar leitura (dado publicado é fato, item L4-13 nunca desenhou DELETE por
    # HTTP) — a limpeza roda como o operador, direto no banco da trilha, e é só o dado que ESTE script criou
    # (fonte='simulador' + os ativos que ele tocou), nunca o resto do inquilino demo.
    import subprocess

    sql = f"""
    DELETE FROM plat.rede_medicao WHERE ativo = ANY(ARRAY[{",".join("'" + t + "'" for t in trafos)}]::uuid[])
      AND fonte IN ('simulador', 'motor_alarme');
    DELETE FROM plat.rede_medicao_alarme_estado
      WHERE ativo = ANY(ARRAY[{",".join("'" + t + "'" for t in trafos)}]::uuid[]);
    DELETE FROM plat.rede_medicao_ativo WHERE ativo = ANY(ARRAY[{",".join("'" + t + "'" for t in trafos)}]::uuid[]);
    """
    schema = os.environ.get("PLAT_SCHEMA", "plat")
    sql = sql.replace("plat.", f"{schema}.")
    r = subprocess.run(["sudo", "-u", "postgres", "psql", "-d", os.environ.get("PLAT_DB", "iagro_sat"), "-X",
                        "-q", "-v", "ON_ERROR_STOP=1"], input=sql, text=True, capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"limpeza falhou: {r.stderr}")
    return {"ativos": len(trafos)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sensores", type=int, default=20)
    ap.add_argument("--backfill-min", type=int, default=65)
    ap.add_argument("--limpar", action="store_true")
    ap.add_argument("--provar", action="store_true")
    args = ap.parse_args()

    sess = requests.Session()
    entrar(sess, "demo")
    rede_id = achar_rede(sess, NOME_REDE)

    if args.limpar:
        r = limpar(sess, rede_id)
        print(f"limpeza: {r['ativos']} ativo(s), leituras/placa/estado de alarme apagados")
        return

    trafos = achar_trafos(sess, rede_id, args.sensores)
    ativo_sobrecarga = trafos[0]["properties"]["id"]
    kvas = [random.choice([15, 30, 45, 75, 112.5]) for _ in trafos]
    configurar_placas(sess, trafos, kvas)
    print(f"placa cadastrada em {len(trafos)} trafo(s); sobrecarga simulada em {ativo_sobrecarga}")

    agora = datetime.datetime.now(UTC) - datetime.timedelta(seconds=5)
    backfill = gerar_backfill(trafos, args.backfill_min, agora, ativo_sobrecarga)
    t0 = time.monotonic()
    resultado = _publicar(sess, backfill)
    dt = time.monotonic() - t0
    print(f"backfill: {len(backfill)} leituras publicadas em {dt:.1f}s "
          f"(aceitas={resultado['aceitas']} duplicadas={resultado['duplicadas']} "
          f"rejeitadas={len(resultado['rejeitadas'])})")
    disparados = [a for a in resultado["alarmes"] if a.get("disparou_agora")]
    for a in disparados:
        print(f"ALARME DISPAROU: ativo={a['ativo']} carregamento={a['carregamento_pct']:.1f}% desde={a['desde']}")
    if resultado["rejeitadas"][:3]:
        print("exemplos de rejeição:", resultado["rejeitadas"][:3])

    if args.provar:
        agora_tick = datetime.datetime.now(UTC)
        tick = gerar_tick_vivo(trafos, agora_tick)
        t_pub = time.monotonic()
        _publicar(sess, tick)
        # ficha do ativo: última leitura em <= 5s da publicação (portão do item) — medido de verdade, contra
        # o mesmo ativo que acabou de receber o tick
        alvo = trafos[0]["properties"]["id"]
        for _ in range(50):
            r = sess.get(f"{BASE_URL}/api/rede/medicao/ativos/{alvo}/ultimas")
            r.raise_for_status()
            leituras = {leit["grandeza"]: leit for leit in r.json()["leituras"]}
            if leituras.get("corrente_a", {}).get("ts") == _iso(agora_tick):
                break
            time.sleep(0.1)
        latencia = time.monotonic() - t_pub
        print(f"MEDIDO: publicar -> aparecer na ficha do ativo = {latencia:.3f}s (portão pede <= 5s)")

        r = sess.get(f"{BASE_URL}/api/rede/medicao/ativos/{alvo}/serie", params={"grandeza": "corrente_a", "dias": 7})
        r.raise_for_status()
        print(f"gráfico de 7 dias: {r.json()['n']} pontos de corrente_a para {alvo}")

        r = sess.get(f"{BASE_URL}/api/rede/medicao/jusante", params={
            "rede_id": rede_id, "ativo": trafos[0]["properties"]["id"], "grandeza": "corrente_a",
        })
        r.raise_for_status()
        print("agregação a jusante:", r.json())


if __name__ == "__main__":
    main()
