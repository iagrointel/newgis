"""L0-04-k-rota-formatos-encoberta: varredura de sombreamento de rota em TODA a aplicação.

Uma rota A "encobre" uma rota B, registrada depois, quando as duas têm o mesmo método e o mesmo
número de segmentos de caminho, e em toda posição onde os segmentos diferem A tem um parâmetro
({id}, {slug}, ...) exatamente onde B tem um segmento literal — nesse caso, uma requisição para o
caminho literal de B é capturada por A primeiro (FastAPI resolve por ordem de registro dentro do
roteador, ADR 0001 seção 4.3) e nunca chega ao handler de B. É a classe de bug medida ao vivo em
GET /api/importacoes/formatos, capturado por GET /api/importacoes/{id} antes da correção deste item
(devolvia 404 "importacao_inexistente" em vez da lista de formatos).

O teste importa `app.main` em subprocesso mínimo (mesma técnica de test_dependencias.py: só a venv,
sem banco), colhe as 500+ rotas na ORDEM REAL de registro (desembrulhando app.main.ROUTERS via
fastapi.routing._IncludedRouter), e para cada par (A antes de B, mesmo método) confere se A encobre
B segmento a segmento. Zero pares encobertos é o portão; a lista de exceções abaixo documenta pares
que colidem em forma mas nunca em uso real (mesmo path, rotas HEAD implícitas de GET, etc.) — vazia
hoje, existe só para não silenciar um achado novo sem decisão explícita.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AMBIENTE_MINIMO = {
    "PLAT_DSN": "postgresql://plat_app:x@127.0.0.1:5432/iagro_sat",
    "PLAT_SECRET": "ab" * 32,
    "PLAT_AMBIENTE": "dev",
    "PLAT_URL_PUBLICA": "https://exemplo.invalido",
}

# pares (path_A, path_B, metodo) que colidem em forma e são aceitos conscientemente — vazio por ora.
EXCECOES: set[tuple[str, str, str]] = set()

PROGRAMA = r"""
import json
import app.main as m
from fastapi.routing import _IncludedRouter, APIRoute
from starlette.routing import Route

def coletar(routes, saida):
    for r in routes:
        if isinstance(r, _IncludedRouter):
            coletar(r.original_router.routes, saida)
        elif isinstance(r, (APIRoute, Route)):
            metodos = sorted(getattr(r, "methods", None) or [])
            if metodos:
                saida.append({"path": r.path, "methods": metodos})

saida = []
coletar(m.app.routes, saida)
print(json.dumps(saida))
"""


def _segmentos(path: str) -> list[str]:
    return [s for s in path.split("/") if s != ""]


_PARAM_PURO = re.compile(r"^\{[^{}]+\}$")


def _eh_param(segmento: str) -> bool:
    """Só um `{nome}` puro generaliza sobre QUALQUER valor do segmento irmão. Um segmento composto como
    `{y}.{ext}` (usado nas rotas /svc/.../{z}/{x}/{y}.{ext}) só bate em valores com aquele literal (o
    ponto) no meio — não é um coringa total, e tratá-lo como um encobriria falsos positivos (medido:
    3 pares em /svc/.../raster, /svc/.../mosaico, /svc/.../ogc/tiles — nenhum é sombreamento real)."""
    return bool(_PARAM_PURO.match(segmento))


def _encobre(a: list[str], b: list[str]) -> bool:
    """True se o template `a`, registrado antes, captura qualquer caminho concreto que bate em `b`,
    registrado depois, sem que `a` e `b` sejam o mesmo template (mesma rota reaberta não conta)."""
    if len(a) != len(b) or a == b:
        return False
    for sa, sb in zip(a, b):
        if sa == sb:
            continue
        if _eh_param(sa):
            continue  # a generaliza aqui — ok se for o único jeito de bater
        return False  # segmento literal de A diferente do de B: não encobre
    return True


def _colher_rotas() -> list[dict]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PLAT_")}
    env.update(AMBIENTE_MINIMO)
    env["PYTHONNOUSERSITE"] = "1"
    r = subprocess.run(
        [sys.executable, "-c", PROGRAMA], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, f"falha ao importar app.main:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout)


def test_zero_rotas_encobertas():
    rotas = _colher_rotas()
    assert len(rotas) > 400, f"esperava ordem de 500 rotas registradas, achou {len(rotas)} — app.main mudou?"

    achados = []
    for i, ra in enumerate(rotas):
        for rb in rotas[i + 1 :]:
            metodos_comuns = set(ra["methods"]) & set(rb["methods"])
            if not metodos_comuns:
                continue
            sa, sb = _segmentos(ra["path"]), _segmentos(rb["path"])
            if _encobre(sa, sb):
                for metodo in metodos_comuns:
                    par = (ra["path"], rb["path"], metodo)
                    if par not in EXCECOES:
                        achados.append(par)

    assert achados == [], (
        f"{len(achados)} par(es) de rota encoberta (A registrada antes captura B): {achados[:20]}"
    )


def test_importacoes_formatos_nao_e_mais_encoberta_por_id():
    """Caso concreto que originou o item: garante que a regressão específica não volta."""
    rotas = _colher_rotas()
    caminhos = [r["path"] for r in rotas if "GET" in r["methods"] and r["path"].startswith("/api/importacoes")]
    assert "/api/importacoes/formatos" in caminhos
    assert "/api/importacoes/{id}" in caminhos
    i_formatos = caminhos.index("/api/importacoes/formatos")
    i_id = caminhos.index("/api/importacoes/{id}")
    assert i_formatos < i_id, "GET /api/importacoes/formatos precisa ser registrada antes de /{id}"
