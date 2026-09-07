#!/usr/bin/env python3
"""Bancada de carga do serviço de ladrilho (item L1-02-tiles-token).

Mede o que o portão do item pede — ladrilhos por segundo QUENTE, com o cache do nginx — e mais três
coisas que só se sabem medindo: a taxa de acerto do cache, o comportamento do `proxy_cache_lock` com N
pedidos simultâneos ao MESMO ladrilho frio, e o tempo entre revogar o token e receber 403.

Não usa biblioteca de carga: `http.client` em threads, para a medida não depender de nada que não esteja
instalado. Números vão para `tests/medidas/L1-02-tiles-token.json` pelo `--saida`.

Uso:
  scripts/bench_tiles.py --base http://127.0.0.1:8238 --token <tok> --item <uuid> [--saida arq.json]
"""

from __future__ import annotations

import argparse
import http.client
import json
import statistics
import threading
import time
import urllib.parse


def _pedir(base: str, caminho: str, timeout: float = 30.0) -> tuple[int, int, str]:
    partes = urllib.parse.urlsplit(base)
    con = http.client.HTTPConnection(partes.hostname, partes.port or 80, timeout=timeout)
    try:
        con.request("GET", caminho)
        r = con.getresponse()
        corpo = r.read()
        return r.status, len(corpo), r.headers.get("X-Plat-Cache", "-")
    finally:
        con.close()


def _sessao(base: str, caminhos: list[str], segundos: float, resultado: list, timeout: float = 30.0):
    """Uma conexão persistente pedindo em rajada por `segundos` (é o que um cliente de mapa faz)."""
    partes = urllib.parse.urlsplit(base)
    con = http.client.HTTPConnection(partes.hostname, partes.port or 80, timeout=timeout)
    n_ok = n_erro = bytes_total = 0
    tempos = []
    fim = time.monotonic() + segundos
    i = 0
    try:
        while time.monotonic() < fim:
            caminho = caminhos[i % len(caminhos)]
            i += 1
            t0 = time.perf_counter()
            try:
                con.request("GET", caminho)
                r = con.getresponse()
                corpo = r.read()
                tempos.append((time.perf_counter() - t0) * 1000)
                if r.status in (200, 204):
                    n_ok += 1
                    bytes_total += len(corpo)
                else:
                    n_erro += 1
            except Exception:
                n_erro += 1
                con.close()
                con = http.client.HTTPConnection(partes.hostname, partes.port or 80, timeout=timeout)
    finally:
        con.close()
    resultado.append({"ok": n_ok, "erro": n_erro, "bytes": bytes_total, "tempos": tempos})


def carga(base: str, caminhos: list[str], conexoes: int, segundos: float) -> dict:
    resultados: list = []
    fios = [threading.Thread(target=_sessao, args=(base, caminhos, segundos, resultados))
            for _ in range(conexoes)]
    t0 = time.perf_counter()
    for f in fios:
        f.start()
    for f in fios:
        f.join()
    duracao = time.perf_counter() - t0
    ok = sum(r["ok"] for r in resultados)
    erro = sum(r["erro"] for r in resultados)
    tempos = [t for r in resultados for t in r["tempos"]]
    tempos.sort()
    return {
        "conexoes": conexoes,
        "segundos": round(duracao, 3),
        "ladrilhos": ok,
        "erros": erro,
        "ladrilhos_por_segundo": round(ok / duracao, 1) if duracao else 0,
        "ms_mediana": round(statistics.median(tempos), 2) if tempos else None,
        "ms_p95": round(tempos[int(len(tempos) * 0.95)], 2) if tempos else None,
        "bytes": sum(r["bytes"] for r in resultados),
    }


def rebanho(base: str, caminho: str, n: int) -> dict:
    """N pedidos SIMULTÂNEOS ao mesmo ladrilho frio: com `proxy_cache_lock`, um vai ao servidor e os
    outros esperam a mesma resposta (MISS = 1)."""
    saida: list = []
    trava = threading.Lock()

    def um():
        r = _pedir(base, caminho)
        with trava:
            saida.append(r)

    fios = [threading.Thread(target=um) for _ in range(n)]
    t0 = time.perf_counter()
    for f in fios:
        f.start()
    for f in fios:
        f.join()
    estados: dict[str, int] = {}
    for _status, _bytes, cache in saida:
        estados[cache] = estados.get(cache, 0) + 1
    return {"pedidos": n, "segundos": round(time.perf_counter() - t0, 3),
            "estados": estados, "status": sorted({s for s, _b, _c in saida})}


def revogacao(base: str, item: str, credenciais: str) -> dict:
    """Mede o tempo entre revogar o token e o serviço passar a devolver 403 — a cláusula "<= 5 s" do
    portão. Usa a aplicação em processo só para CRIAR e REVOGAR o token (é operação de sessão, não do
    serviço de ladrilho); a medida em si é HTTP contra o `base`, que deve ser o nginx."""
    import os

    os.environ.setdefault("PLAT_AMBIENTE", "dev")
    from fastapi.testclient import TestClient

    from app.main import app

    cred = {}
    for linha in open(credenciais, encoding="utf-8"):
        partes = linha.split()
        if len(partes) >= 3:
            cred[partes[0]] = (partes[1], " ".join(partes[2:]))
    login, senha = cred["demo"]
    c = TestClient(app, base_url="http://testserver")
    r = c.post("/api/login", json={"inquilino": "demo", "login": login, "senha": senha})
    if r.status_code != 200:
        raise SystemExit(f"login de demo falhou: {r.status_code} {r.text[:200]}")
    r = c.post("/api/tokens", json={"nome": "zt-bancada-revogacao", "escopos": ["tiles:ler"]})
    tok, token_id = r.json()["token"], r.json()["id"]
    caminho = f"/svc/{tok}/raster/{item}/12/1503/2230.png"
    for _ in range(5):
        status, _n, _c = _pedir(base, caminho)
        if status != 200:
            raise SystemExit(f"o ladrilho tinha de vir 200 antes de revogar; veio {status}")
    t0 = time.monotonic()
    c.delete(f"/api/tokens/{token_id}")
    while time.monotonic() - t0 < 30:
        status, _n, _c = _pedir(base, caminho)
        if status == 403:
            return {"segundos_ate_403": round(time.monotonic() - t0, 3), "status_final": 403}
        time.sleep(0.05)
    return {"segundos_ate_403": None, "status_final": status}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--item", required=True)
    p.add_argument("--z", type=int, default=12)
    p.add_argument("--x", type=int, default=1503)
    p.add_argument("--y", type=int, default=2230)
    p.add_argument("--lon", type=float, help="se dado com --lat, x e y saem da grade WebMercatorQuad")
    p.add_argument("--lat", type=float)
    p.add_argument("--conexoes", type=int, default=32)
    p.add_argument("--frios", type=int, default=40, help="pedidos frios (URL única) na medida fria")
    p.add_argument("--tela", type=int, default=40, help="ladrilhos distintos na medida de tela cheia")
    p.add_argument("--segundos", type=float, default=10.0)
    p.add_argument("--saida")
    p.add_argument("--revogar", metavar="ARQUIVO_CREDENCIAIS",
                   help="mede o tempo entre revogar o token e receber 403 (cria e revoga um token próprio)")
    a = p.parse_args()
    if a.lon is not None and a.lat is not None:
        from morecantile import tms as _tms
        t = _tms.get("WebMercatorQuad").tile(a.lon, a.lat, a.z)
        a.x, a.y = t.x, t.y

    um_so = [f"/svc/{a.token}/raster/{a.item}/{a.z}/{a.x}/{a.y}.png"]
    lado = int(a.tela ** 0.5) + 1
    tela = [f"/svc/{a.token}/raster/{a.item}/{a.z}/{a.x + dx}/{a.y + dy}.png"
            for dx in range(lado) for dy in range(lado)][:a.tela]
    for c in um_so + tela:  # aquece o cache do nginx
        _pedir(a.base, c)
    medida = {
        "quente_um_ladrilho": carga(a.base, um_so, a.conexoes, a.segundos),
        "quente_tela": carga(a.base, tela, a.conexoes, a.segundos),
        "frio_uma_conexao": None,
        "rebanho": None,
    }
    # FRIO de verdade: cada pedido tem uma faixa diferente, então nenhuma resposta pode vir do cache.
    # (a primeira versão desta bancada repetia 16 URLs por 5 s e chamava isso de "frio" — media cache.)
    marca = int(time.time())
    frios = [f"/svc/{a.token}/raster/{a.item}/{a.z}/{a.x + (i % 3)}/{a.y + (i // 3) % 3}.png?faixa=0,{marca + i}"
             for i in range(a.frios)]
    t0 = time.perf_counter()
    estados_frio: dict[str, int] = {}
    tempos_frio = []
    for c in frios:
        t1 = time.perf_counter()
        status, _n, cache = _pedir(a.base, c)
        tempos_frio.append((time.perf_counter() - t1) * 1000)
        estados_frio[f"{status}/{cache}"] = estados_frio.get(f"{status}/{cache}", 0) + 1
    dur = time.perf_counter() - t0
    medida["frio_uma_conexao"] = {
        "pedidos": len(frios), "segundos": round(dur, 3),
        "ladrilhos_por_segundo": round(len(frios) / dur, 1),
        "ms_mediana": round(statistics.median(tempos_frio), 2),
        "estados": estados_frio,
    }
    medida["rebanho"] = rebanho(
        a.base, f"/svc/{a.token}/raster/{a.item}/{a.z}/{a.x}/{a.y}.png?faixa=0,{marca + 99}", 20)
    if a.revogar:
        medida["revogacao"] = [revogacao(a.base, a.item, a.revogar) for _ in range(3)]
    print(json.dumps(medida, ensure_ascii=False, indent=2))
    if a.saida:
        with open(a.saida, "w", encoding="utf-8") as f:
            json.dump(medida, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
