"""Medida isolada da cláusula de desempenho do portão do item L2-02-b-classificacao-servidor:
"1 mi de valores classificados em <= 2 s (medido)". Não é pytest (roda_teste.sh não segura vaga
para uma medida de dezenas de segundos de carga do banco); grava direto em
`tests/medidas/L2-02-b-classificacao-servidor.json`, com `carga_1min`/`ram_livre_gb` ao lado do
número (regra do brief comum: tempo sem a carga da máquina do lado não vale como prova).

Uso: `set -a; source laco/var/trilha/<nome>.env; set +a; venv/bin/python
tests/api/catalogo/medir_classes_desempenho.py`"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from app.schema_ambiente import CursorSchemaAmbiente  # noqa: E402
from tests.api.conftest import novo_cliente  # noqa: E402
from tests.api.test_rls import contexto, ids_por_slug  # noqa: E402

MEDIDAS = ROOT / "tests" / "medidas" / "L2-02-b-classificacao-servidor.json"
ITEM = "L2-02-b-classificacao-servidor"


def _carga() -> tuple[float, float]:
    carga_1min = os.getloadavg()[0]
    linhas = Path("/proc/meminfo").read_text().splitlines()
    disp_kb = next(int(li.split()[1]) for li in linhas if li.startswith("MemAvailable:"))
    return carga_1min, round(disp_kb / 1024 / 1024, 1)


def main() -> None:
    dsn = os.environ["PLAT_DSN"]
    con = psycopg2.connect(dsn, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    tabela = "zt_class_perf_1m"
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    ids = ids_por_slug(con)
    contexto(con, ids["demo"], usuario_id=adm, login="admin")
    with con.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS plat_trabalho.{tabela}")
        cur.execute(f"CREATE TABLE plat_trabalho.{tabela} (id serial PRIMARY KEY, v double precision)")
        t0 = time.monotonic()
        cur.execute(
            f"INSERT INTO plat_trabalho.{tabela}(v) "
            f"SELECT (random() * 1000000)::double precision FROM generate_series(1, 1000000)"
        )
        t_carga = time.monotonic() - t0
    con.commit()

    cliente = novo_cliente()
    login, senha = None, None
    caminho_credenciais = Path(os.environ.get("PLAT_CREDENCIAIS_ARQUIVO") or (ROOT / "tests" / "credenciais.txt"))
    for linha in caminho_credenciais.read_text().splitlines():
        partes = linha.split()
        if partes and partes[0] == "demo":
            login, senha = partes[1], " ".join(partes[2:])
    r = cliente.post("/api/login", json={"inquilino": "demo", "login": login, "senha": senha})
    assert r.status_code == 200, r.text
    corpo_item = {
        "tipo": "camada_vetorial", "titulo": "zt perf classes 1m",
        "dados": {
            "schema": "plat_trabalho", "tabela": tabela, "geometria": "Point", "srid": 4326,
            "campos": [{"nome": "v", "tipo": "double precision"}], "fonte": "hospedada",
        },
    }
    r = cliente.post("/api/itens", json=corpo_item)
    assert r.status_code == 201, r.text
    item_id = r.json()["id"]

    carga_1min, ram_livre_gb = _carga()
    t0 = time.monotonic()
    r = cliente.get(f"/api/camadas/{item_id}/classes", params={"campo": "v", "metodo": "quantil", "n": 5})
    duracao_s = time.monotonic() - t0
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["amostrado"] is False, "1 milhão não deveria amostrar (teto é exatamente 1 milhão)"

    with con.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS plat_trabalho.{tabela}")
    con.commit()
    cliente.delete(f"/api/itens/{item_id}")

    MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
    dados = json.loads(MEDIDAS.read_text()) if MEDIDAS.exists() else {"item": ITEM, "medidas": {}}
    dados["medidas"]["classes_1mi_quantil_s"] = {
        "valor": round(duracao_s, 3), "unidade": "s", "alvo": "<= 2",
        "passou": duracao_s <= 2.0,
        "comando": "tests/api/catalogo/medir_classes_desempenho.py",
        "carga_1min": carga_1min, "ram_livre_gb": ram_livre_gb,
        "carga_geracao_dado_s": round(t_carga, 3),
        "medido_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    MEDIDAS.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(dados["medidas"]["classes_1mi_quantil_s"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
