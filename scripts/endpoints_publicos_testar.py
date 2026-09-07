"""Testa por HTTP o catálogo de conectores públicos (item L6-02-m-catalogo-endpoints-brasil) e grava a medida em
`tests/medidas/L6-02-m-catalogo-endpoints-brasil.json`: quantos endpoints estão verdes NA DATA, quais, por tipo e
por origem, com o motivo de cada vermelho. É o "script + JSON" do portão ("≥ 60 endpoints com teste HTTP verde na
data"). Lê a semente (`app/conexao/endpoints_publicos_semente.json`) e, quando há banco (`PLAT_DSN` no ambiente),
também os candidatos derivados do registro do acervo. Não escreve no banco: quem grava o resultado é o job
`endpoints_publicos.retestar`. Uso:

    set -a; source <env da trilha>; set +a; venv/bin/python scripts/endpoints_publicos_testar.py [--paralelo 8]
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.conexao import endpoints_publicos as ep  # noqa: E402
from app.versao import git_sha_curto  # noqa: E402

ITEM = "L6-02-m-catalogo-endpoints-brasil"
DESTINO = RAIZ / "tests" / "medidas" / f"{ITEM}.json"


def _carga() -> tuple[float | None, float | None]:
    try:
        carga = os.getloadavg()[0]
    except OSError:
        carga = None
    livre = None
    try:
        for linha in Path("/proc/meminfo").read_text().splitlines():
            if linha.startswith("MemAvailable:"):
                livre = round(int(linha.split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    return carga, livre


def candidatos() -> list[dict]:
    lista = ep.candidatos_da_semente()
    dsn = os.environ.get("PLAT_DSN")
    if dsn:
        import psycopg2

        from app.schema_ambiente import CursorSchemaAmbiente

        con = psycopg2.connect(dsn, cursor_factory=CursorSchemaAmbiente)
        try:
            with con.cursor() as cur:
                cur.execute("SET search_path = plat, public")
                vistos = {(c["tipo"], c["url"]) for c in lista}
                for c in ep.candidatos_do_registro(cur):
                    if (c["tipo"], c["url"]) not in vistos:
                        lista.append(c)
        finally:
            con.close()
    return lista


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paralelo", type=int, default=8)
    a = ap.parse_args()
    lista = candidatos()
    inicio = datetime.datetime.now(datetime.UTC)
    with cf.ThreadPoolExecutor(max(1, a.paralelo)) as ex:
        resultados = list(ex.map(lambda e: (e, ep.testar(e["url"], e["tipo"])), lista))
    fim = datetime.datetime.now(datetime.UTC)
    verdes = [(e, r) for e, r in resultados if r.vivo]
    vermelhos = [(e, r) for e, r in resultados if not r.vivo]
    por_tipo = {t: sum(1 for e, _ in verdes if e["tipo"] == t) for t in ep.TIPOS}
    por_origem = {o: sum(1 for e, _ in verdes if e["origem"] == o) for o in ("registro", "curadoria", "fila_keyless")}
    carga, ram = _carga()
    comando = (
        "venv/bin/python scripts/endpoints_publicos_testar.py "
        "(GET do documento do protocolo por buscar_seguro + assinatura do corpo)"
    )
    dados = {
        "item": ITEM,
        "medidas": {
            "endpoints_candidatos": {"valor": len(lista), "unidade": "endpoints", "comando": comando},
            "endpoints_verdes_na_data": {"valor": len(verdes), "unidade": "endpoints", "comando": comando},
            "endpoints_vermelhos_na_data": {"valor": len(vermelhos), "unidade": "endpoints", "comando": comando},
            "verdes_por_tipo": {"valor": por_tipo, "unidade": "endpoints", "comando": comando},
            "verdes_por_origem": {"valor": por_origem, "unidade": "endpoints", "comando": comando},
            "duracao_s": {"valor": round((fim - inicio).total_seconds(), 1), "unidade": "s", "comando": comando},
        },
        "contexto": {"carga_1min": carga, "ram_livre_gb": ram, "medido_em": fim.strftime("%Y-%m-%dT%H:%M:%SZ")},
        "verdes": [
            {"tipo": e["tipo"], "orgao": e["orgao"], "url": e["url"], "http": r.http, "ms": r.ms, "origem": e["origem"]}
            for e, r in sorted(verdes, key=lambda x: (x[0]["orgao"], x[0]["url"]))
        ],
        "vermelhos": [
            {"tipo": e["tipo"], "orgao": e["orgao"], "url": e["url"], "http": r.http, "motivo": r.motivo}
            for e, r in sorted(vermelhos, key=lambda x: (x[0]["orgao"], x[0]["url"]))
        ],
        "gerado_em": fim.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": git_sha_curto(),
    }
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(verdes)} verdes de {len(lista)} em {dados['medidas']['duracao_s']['valor']} s -> {DESTINO}")
    for e, r in vermelhos:
        print(f"  vermelho {e['tipo']:9} {r.motivo:32} {e['url']}")
    return 0 if len(verdes) >= 60 else 1


if __name__ == "__main__":
    sys.exit(main())
