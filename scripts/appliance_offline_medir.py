"""Prova dinâmica do appliance sem internet (item L7-11-b-appliance-sem-internet): roda a suíte e2e INTEIRA com o
navegador atrás do proxy de captura (`tests/operacao/proxy_captura.py`), que só repassa a própria instalação e
conta cada pedido que tentou sair. Grava `tests/medidas/L7-11-b-appliance-sem-internet.json`: pedidos totais,
pedidos externos bloqueados (tem de ser 0), hosts externos vistos, resultado do e2e, e se o mapa-base apareceu
(o e2e do mapa, `tests/e2e/test_mapa.py`, é quem prova o PMTiles local).

Uso (contra uma instalação já de pé — trilha atrás de uma frente que serve /static/, ou produção pelo nginx):

    set -a; source <env da trilha>; set +a
    venv/bin/python scripts/appliance_offline_medir.py --base-url http://127.0.0.1:<porta> [-k expr]

O host da `--base-url` é o único permitido. Sai com 1 se houve pedido externo ou se o e2e reprovou."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.versao import git_sha_curto  # noqa: E402
from tests.operacao.proxy_captura import ProxyCaptura  # noqa: E402

ITEM = "L7-11-b-appliance-sem-internet"
DESTINO = RAIZ / "tests" / "medidas" / f"{ITEM}.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("-k", default=None, help="expressão -k do pytest para restringir o e2e")
    ap.add_argument("--timeout", type=int, default=3000)
    a = ap.parse_args()
    host = urlsplit(a.base_url).hostname or "127.0.0.1"
    log = RAIZ / "var" / "proxy_captura.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.unlink(missing_ok=True)
    proxy = ProxyCaptura({host, "localhost"} if host == "127.0.0.1" else {host}, log=str(log)).iniciar()
    inicio = datetime.datetime.now(datetime.UTC)
    junit = RAIZ / "var" / "e2e_offline.xml"
    junit.unlink(missing_ok=True)
    cmd = [str(RAIZ / "venv" / "bin" / "pytest"), "tests/e2e", "-q", "-m", "lento", "-p", "no:cacheprovider",
           "--base-url", a.base_url, "--tb=line", f"--junitxml={junit}"]
    if a.k:
        cmd += ["-k", a.k]
    env = {**os.environ, "PLAT_E2E_PROXY": proxy.url, "PYTHONNOUSERSITE": "1"}
    r = subprocess.run(cmd, cwd=RAIZ, env=env, capture_output=True, text=True, timeout=a.timeout)
    proxy.parar()
    fim = datetime.datetime.now(datetime.UTC)
    (RAIZ / "var" / "e2e_offline_saida.txt").write_text(r.stdout + "\n--- stderr ---\n" + r.stderr, encoding="utf-8")
    resumo = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    # contagens do junit (a saída -q desta suíte não traz a linha de totais)
    import xml.etree.ElementTree as ET

    total = falharam = pulados = 0
    if junit.exists():
        raiz_xml = ET.parse(junit).getroot()
        for ts in raiz_xml.iter("testsuite"):
            total += int(ts.get("tests", 0))
            falharam += int(ts.get("failures", 0)) + int(ts.get("errors", 0))
            pulados += int(ts.get("skipped", 0))
    passaram = total - falharam - pulados
    externos = proxy.externos
    hosts_externos = sorted({h for _, h, _ in externos})
    mapa_ok = "test_mapa" in (r.stdout + junit.read_text(encoding="utf-8") if junit.exists() else r.stdout) \
        and not re.search(r"FAILED tests/e2e/test_mapa", r.stdout)
    comando = " ".join(cmd[1:]) + " (navegador atrás de tests/operacao/proxy_captura.py)"
    dados = {"item": ITEM, "medidas": {}}
    if DESTINO.exists():
        dados = json.loads(DESTINO.read_text(encoding="utf-8"))
    med = dados.setdefault("medidas", {})
    med["pedidos_pelo_proxy"] = {"valor": proxy.total, "unidade": "pedidos", "comando": comando}
    med["pedidos_a_host_externo"] = {"valor": len(externos), "unidade": "pedidos", "comando": comando}
    med["hosts_externos_vistos"] = {"valor": hosts_externos, "unidade": "hosts", "comando": comando}
    med["e2e_passaram"] = {"valor": passaram, "unidade": "testes", "comando": comando}
    med["e2e_falharam"] = {"valor": falharam, "unidade": "testes", "comando": comando}
    med["e2e_pulados"] = {"valor": pulados, "unidade": "testes", "comando": comando}
    med["mapa_base_apareceu"] = {"valor": mapa_ok, "unidade": "bool",
                                 "comando": "tests/e2e/test_mapa.py verde atrás do proxy"}
    med["duracao_s"] = {"valor": round((fim - inicio).total_seconds(), 1), "unidade": "s", "comando": comando}
    dados["contexto"] = {
        "base_url": a.base_url, "resumo_pytest": resumo, "medido_em": fim.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "falhas": re.findall(r"FAILED (\S+)", r.stdout)[:40],
    }
    dados["gerado_em"] = fim.strftime("%Y-%m-%dT%H:%M:%SZ")
    dados["git_sha"] = git_sha_curto()
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"e2e: {resumo}\npedidos pelo proxy: {proxy.total}; externos bloqueados: {len(externos)} {hosts_externos}")
    for metodo, h, caminho in externos[:20]:
        print(f"  externo: {metodo} {h}{caminho}")
    return 0 if (not externos and falharam == 0 and r.returncode in (0, 5)) else 1


if __name__ == "__main__":
    sys.exit(main())
