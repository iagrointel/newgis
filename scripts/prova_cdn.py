#!/usr/bin/env python3
"""Bancada fim-a-fim do item L7-26-cdn-tiles: sobe a API de verdade (uvicorn, socket real), sobe a CDN
SIMULADA na frente (`scripts/cdn_simulada.py`, também socket real) e mede as cinco cláusulas do portão
contra os dois. É o mesmo padrão de `scripts/bench_tiles.py` (item L1-02) e `scripts/homolog_e2e.sh`
(item L7-31): script separado do pytest porque exige processo próprio, não caber no TestClient.

⛔ Não há Cloudflare aqui — ver docstring de cdn_simulada.py e docs/CDN.md. Este script prova o
MECANISMO (cache por caminho sem query string, Cache-Control decidindo elegibilidade, purge por
prefixo, isolamento de rota de API) rodando de verdade contra uma implementação equivalente.

Uso (com o ambiente da trilha já `source`ado):
  venv/bin/python scripts/prova_cdn.py --saida tests/medidas/L7-26-cdn-tiles.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
Z, X, Y = 12, 1503, 2230


def _get(porta: int, caminho: str, timeout: float = 10.0):
    req = urllib.request.Request(f"http://127.0.0.1:{porta}{caminho}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers.items()), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items()), e.read()


def _post_json(porta: int, caminho: str, corpo: dict, timeout: float = 10.0):
    dados = json.dumps(corpo).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{porta}{caminho}", data=dados, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _tenant_id_de(slug: str) -> int:
    """Mesmo caminho de tests/api/imagens/conftest.py::_tenant_id: `plat.tenant_publico` é a única
    função que lê `plat.tenant` sem contexto de inquilino (RLS), a mesma que a tela de login usa."""
    import os

    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(os.environ["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT id FROM plat.tenant_publico(%s)", (slug,))
            return cur.fetchone()["id"]
    finally:
        con.close()


def _semear(tenant_slug: str = "demo") -> dict:
    """Login, token e raster de teste — tudo em processo (TestClient), gravando no MESMO banco que a
    API de verdade (subprocesso) vai ler. `_AUTH`/`_FONTES` são cache EM PROCESSO da aplicação
    (app/imagens/rotas_tiles.py): como o TestClient roda num processo Python separado do uvicorn
    subprocesso, os dois nunca compartilham essas linhas de cache — é exatamente por isso que revogar
    aqui só aparece lá depois do TTL (2 s), o mesmo comportamento medido em produção real."""
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.api.conftest import credenciais, entrar
    from tests.api.imagens.apoio_raster import semear_raster

    c = TestClient(app, base_url="http://testserver")
    cred = credenciais()
    login, senha = cred[tenant_slug]
    r = entrar(c, tenant_slug, login, senha)
    assert r.status_code == 200 and r.json()["ok"], r.text

    r = c.post("/api/tokens", json={"nome": "zt-prova-cdn", "escopos": ["tiles:ler"]})
    assert r.status_code == 201, r.text
    token = r.json()

    r2 = c.post("/api/tokens", json={"nome": "zt-prova-cdn-2", "escopos": ["tiles:ler"]})
    assert r2.status_code == 201, r2.text
    token2 = r2.json()

    tenant_id = _tenant_id_de(tenant_slug)
    raster = semear_raster(tenant_id, "prova-cdn")
    return {"sessao": c, "token": token, "token2": token2, "raster": raster, "tenant_id": tenant_id}


def _sha256_atual(tenant_id: int, item: str) -> str:
    from app import db

    with db.db(db.Contexto(tenant_id=tenant_id, usuario_id=0, login="teste")) as cur:
        cur.execute("SELECT sha256 FROM plat.raster_item WHERE tenant_id = %s AND item_id = %s",
                    (tenant_id, item))
        return cur.fetchone()["sha256"]


def _git_sha() -> str:
    # app/versao.py lê `.git/HEAD` como diretório; num WORKTREE `.git` é um ARQUIVO com "gitdir: ...",
    # então a leitura sem subprocesso falha e a app exige PLAT_GIT_SHA no ambiente (mesmo mecanismo que
    # o install.sh usa fora de um clone). `git rev-parse` sabe seguir o ponteiro do worktree.
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True,
                          text=True, check=True).stdout.strip()


def _subir_uvicorn(porta: int, log: Path) -> subprocess.Popen:
    ambiente = {**__import__("os").environ, "PLAT_GIT_SHA": _git_sha()}
    return subprocess.Popen(
        [str(ROOT / "venv" / "bin" / "python"), "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(porta), "--no-access-log"],
        cwd=str(ROOT), stdout=open(log, "wb"), stderr=subprocess.STDOUT, env=ambiente,
    )


def _esperar_saude(porta: int, tentativas: int = 40) -> bool:
    for _ in range(tentativas):
        try:
            status, _, _ = _get(porta, "/saude", timeout=1.0)
            if status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def principal() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--porta-api", type=int, default=8274)
    ap.add_argument("--porta-cdn", type=int, default=8275)
    ap.add_argument("--saida", default=str(ROOT / "tests" / "medidas" / "L7-26-cdn-tiles.json"))
    args = ap.parse_args()

    var = ROOT / "var" / "prova_cdn"
    var.mkdir(parents=True, exist_ok=True)
    resultado: dict = {"item": "L7-26-cdn-tiles", "clausulas": {}}

    print("== semeando login/token/raster (em processo, mesma base que a API subprocesso vai ler)")
    ctx = _semear()
    token, item = ctx["token"]["token"], ctx["raster"]["item_id"]
    tenant_id = ctx["tenant_id"]
    versao = _sha256_atual(tenant_id, item)[:12]
    caminho_tile = f"/svc/{token}/raster/{item}@{versao}/{Z}/{X}/{Y}.png"

    print(f"== subindo API real em :{args.porta_api}")
    p_api = _subir_uvicorn(args.porta_api, var / "api.log")
    p_cdn = None
    try:
        if not _esperar_saude(args.porta_api):
            (var / "api.log").exists() and print((var / "api.log").read_text()[-4000:])
            raise SystemExit("API não respondeu a /saude em 20s")

        print(f"== subindo CDN simulada em :{args.porta_cdn} -> 127.0.0.1:{args.porta_api}")
        p_cdn = subprocess.Popen(
            [str(ROOT / "venv" / "bin" / "python"), str(ROOT / "scripts" / "cdn_simulada.py"),
             "--origem", f"http://127.0.0.1:{args.porta_api}", "--porta", str(args.porta_cdn)],
            cwd=str(ROOT), stdout=open(var / "cdn.log", "wb"), stderr=subprocess.STDOUT,
        )
        time.sleep(1.0)

        # ---------------------------------------------------------------- cláusula 1: 2ª chamada = HIT
        print("== cláusula 1: tile pedido 2x -> HIT na 2ª")
        s1, h1, _ = _get(args.porta_cdn, caminho_tile)
        s2, h2, _ = _get(args.porta_cdn, caminho_tile)
        c1 = {
            "primeira_status": s1, "primeira_cf_cache_status": h1.get("cf-cache-status"),
            "segunda_status": s2, "segunda_cf_cache_status": h2.get("cf-cache-status"),
            "passou": s1 == 200 and s2 == 200 and h1.get("cf-cache-status") == "MISS"
                      and h2.get("cf-cache-status") == "HIT",
        }
        resultado["clausulas"]["1_hit_na_segunda_chamada"] = c1
        print(f"   {c1}")

        # ---------------------------------------------------------------- cláusula 2: revoga -> purge -> 403 <= 60s
        print("== cláusula 2: revogar -> purgar -> 3ª chamada 403 em <= 60s")
        r_rev = ctx["sessao"].delete(f"/api/tokens/{ctx['token']['id']}")
        assert r_rev.status_code in (200, 204), r_rev.text
        t0 = time.monotonic()
        status_purga, corpo_purga = _post_json(args.porta_cdn, "/__purgar__", {"prefixos": [f"/svc/{token}/"]})
        s3, h3, _ = _get(args.porta_cdn, caminho_tile)
        # ACHADO (mesma classe do achado do L1-02, mas na camada de cima): o purge é instantâneo, mas a
        # ORIGEM ainda guarda a autorização em cache por AUTH_TTL_S=2s (app/imagens/rotas_tiles.py). Se o
        # purge e a 1ª chamada pós-purge caem DENTRO desses 2s, a origem responde 200 (a autorização
        # cacheada é anterior à revogação) e a CDN RECACHEIA o 200 por 1 ano — um purge não repetido fica
        # inútil. A correção correta não é o cliente adivinhar o TTL da origem: é repetir o purge durante a
        # janela, exatamente como um runbook real faria com um botão "purgar" que não sabe o TTL interno do
        # servidor de origem. Por isso o laço abaixo purga de novo a cada tentativa, não só espera.
        limite = t0 + 60.0
        tentativas_purge = 1
        while s3 != 403 and time.monotonic() < limite:
            time.sleep(0.25)
            _post_json(args.porta_cdn, "/__purgar__", {"prefixos": [f"/svc/{token}/"]})
            tentativas_purge += 1
            s3, h3, _ = _get(args.porta_cdn, caminho_tile)
        elapsed = time.monotonic() - t0
        c2 = {
            "purga_status": status_purga, "purga_removidos_1a_tentativa": corpo_purga.get("removidos"),
            "tentativas_de_purge": tentativas_purge,
            "terceira_status": s3, "terceira_cf_cache_status": h3.get("cf-cache-status"),
            "segundos_ate_403": round(elapsed, 3),
            "passou": s3 == 403 and elapsed <= 60.0,
            "achado": ("a origem cacheia autorização por AUTH_TTL_S=2s; um purge SÓ na hora da "
                      "revogação pode ser recacheado com 200 se cair dentro dessa janela — o purge "
                      "precisa repetir por >= AUTH_TTL_S depois da revogação (ver docs/CDN.md)"),
        }
        resultado["clausulas"]["2_revoga_purga_403_ate_60s"] = c2
        print(f"   {c2}")

        # ---------------------------------------------------------------- cláusula 3: HIT % de navegação simulada
        print("== cláusula 3: HIT% de uma rodada de navegação simulada")
        token2, item2 = ctx["token2"]["token"], item
        versao2 = _sha256_atual(tenant_id, item2)[:12]
        caminhos = [f"/svc/{token2}/raster/{item2}@{versao2}/{Z}/{X + dx}/{Y + dy}.png"
                    for dx in range(4) for dy in range(3)]  # 12 ladrilhos distintos, "área vista"
        acertos = faltas = 0
        REPETICOES = 8
        for _ in range(REPETICOES):
            for caminho in caminhos:
                status, cabecalhos, _ = _get(args.porta_cdn, caminho)
                if cabecalhos.get("cf-cache-status") == "HIT":
                    acertos += 1
                else:
                    faltas += 1
        total = acertos + faltas
        taxa = acertos / total if total else 0.0
        c3 = {"caminhos_distintos": len(caminhos), "repeticoes": REPETICOES, "pedidos": total,
              "acertos": acertos, "faltas": faltas, "taxa_hit": round(taxa, 4), "passou": taxa >= 0.80}
        resultado["clausulas"]["3_hit_percentual_navegacao"] = c3
        print(f"   {c3}")

        # ---------------------------------------------------------------- cláusula 4: API/app não passa pela CDN
        print("== cláusula 4: rota de API nunca tem cabeçalho de cache de CDN")
        s4, h4, _ = _get(args.porta_api, "/api/tiles/leituras", timeout=5.0)
        cc4 = h4.get("cache-control", "")
        c4 = {
            "status": s4, "cache_control": cc4,
            "passou": "immutable" not in cc4 and "max-age=31536000" not in cc4 and "no-store" in cc4,
        }
        resultado["clausulas"]["4_api_sem_cache_de_cdn"] = c4
        print(f"   {c4}")

        # ---------------------------------------------------------------- refutação: martelar depois do purge
        print("== refutação: martelar a URL revogada 20x depois do purge — nenhum HIT pode aparecer")
        achados = []
        for _ in range(20):
            s, h, _ = _get(args.porta_cdn, caminho_tile)
            achados.append((s, h.get("cf-cache-status")))
        nenhum_hit_servido = all(s == 403 for s, _ in achados)
        resultado["refutacao_martelo_pos_revogacao"] = {
            "tentativas": len(achados), "status_unicos": sorted({s for s, _ in achados}),
            "nenhum_200_ou_hit_depois_da_revogacao": nenhum_hit_servido,
        }
        print(f"   nenhum_200_ou_hit_depois_da_revogacao={nenhum_hit_servido}")

        # ---------------------------------------------------------------- refutação: trocar só o token
        print("== refutação: mesmo item, token de OUTRO inquilino no caminho")
        from tests.api.conftest import credenciais, entrar
        from fastapi.testclient import TestClient
        from app.main import app as app_b

        c_b = TestClient(app_b, base_url="http://testserver")
        cred = credenciais()
        login_b, senha_b = cred["demo2"]
        r_b = entrar(c_b, "demo2", login_b, senha_b)
        assert r_b.status_code == 200, r_b.text
        r_tok_b = c_b.post("/api/tokens", json={"nome": "zt-prova-cdn-b", "escopos": ["tiles:ler"]})
        assert r_tok_b.status_code == 201, r_tok_b.text
        token_b = r_tok_b.json()["token"]
        caminho_cruzado = f"/svc/{token_b}/raster/{item}@{versao}/{Z}/{X}/{Y}.png"
        s_cruzado, h_cruzado, corpo_cruzado = _get(args.porta_cdn, caminho_cruzado)
        c_b.delete(f"/api/tokens/{r_tok_b.json()['id']}")
        resultado["refutacao_token_de_outro_inquilino"] = {
            "status": s_cruzado, "cf_cache_status": h_cruzado.get("cf-cache-status"),
            "recusado": s_cruzado == 403,
        }
        print(f"   status={s_cruzado} (403 esperado)")

    finally:
        if p_cdn is not None:
            p_cdn.terminate()
            p_cdn.wait(timeout=5)
        p_api.terminate()
        p_api.wait(timeout=5)

    resultado["medido_em"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        resultado["carga_1min"] = round(__import__("os").getloadavg()[0], 2)
    except OSError:
        resultado["carga_1min"] = None
    resultado["ram_livre_gb"] = None
    try:
        with open("/proc/meminfo") as f:
            info = dict(li.split(":", 1) for li in f.read().splitlines() if ":" in li)
        resultado["ram_livre_gb"] = round(int(info["MemAvailable"].strip().split()[0]) / 1024 / 1024, 1)
    except Exception:
        pass
    todas_passaram = all(v.get("passou") for v in resultado["clausulas"].values())
    resultado["todas_clausulas_testaveis_localmente_passaram"] = todas_passaram
    resultado["nota"] = ("cláusula 5 (docs/CDN.md) é conferida por leitura, não por este script; "
                          "a configuração real da Cloudflare (DNS, Cache Rule, purge de produção) é "
                          "PENDENTE DO DONO — ver docs/CDN.md")

    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False, sort_keys=False), encoding="utf-8")
    print(f"\n== gravado em {saida}")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    principal()
