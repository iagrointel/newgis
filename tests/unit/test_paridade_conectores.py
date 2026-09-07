"""A seção "Conectores e acervo" de `docs/PARIDADE.md` (item L6-03-paridade-conectores) não pode mentir: o
adversário do item escolhe 5 linhas `feito` e tenta reproduzir — logo cada `feito`/`parcial` precisa apontar
para um teste que exista. Três travas, lidas dos arquivos:

1. toda linha `feito` ou `parcial` da seção cita ao menos um caminho `tests/...` que existe em `master` (a
   árvore atual) OU no ramo nomeado entre parênteses na mesma célula (ramo wt/...), conferido com
   `git cat-file -e <ramo>:<caminho>` — o ramo da fila ainda não juntado é onde o adversário reproduz;
2. toda linha `fora` NÃO cita teste (o que não existe não tem prova) e nomeia o item ou a decisão que a cobre;
3. `docs/urls_paridade.txt` tem toda chave `[X-...]` citada nos títulos da seção, e cada URL da lista está com
   HTTP 200 em `tests/medidas/L6-03-paridade-conectores.json` (gerado por `scripts/paridade_urls_testar.py`;
   o teste não vai à rede — lê a medida gravada e a data dela)."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PARIDADE = RAIZ / "docs" / "PARIDADE.md"
URLS = RAIZ / "docs" / "urls_paridade.txt"
MEDIDAS = RAIZ / "tests" / "medidas" / "L6-03-paridade-conectores.json"
TITULO = "## Conectores e acervo (item L6-03-paridade-conectores"
RE_TESTE = re.compile(r"`(tests/[A-Za-z0-9_./-]+\.py)`")
RE_RAMO = re.compile(r"ramo `(wt/[A-Za-z0-9_-]+)`")
RE_CHAVE = re.compile(r"\[([A-Z]+(?:-[a-z0-9-]+)+(?:, [A-Z]+(?:-[a-z0-9-]+)+)*)\]")


def _secao() -> str:
    texto = PARIDADE.read_text(encoding="utf-8")
    i = texto.find(TITULO)
    assert i >= 0, "seção de conectores ausente em docs/PARIDADE.md"
    resto = texto[i + len(TITULO):]
    fim = resto.find("\n## ")
    return resto if fim < 0 else resto[:fim]


def _linhas() -> list[dict]:
    saida = []
    for linha in _secao().splitlines():
        if not linha.startswith("| ") or linha.startswith("| capacidade") or linha.startswith("|---"):
            continue
        celulas = [c.strip() for c in linha.strip().strip("|").split(" | ")]
        if len(celulas) < 7:
            continue
        estado = celulas[3].split(" ")[0].split("(")[0].strip()
        saida.append({"capacidade": celulas[0], "estado": estado, "testado_por": celulas[4], "linha": linha})
    return saida


def _existe_em(ramo: str, caminho: str) -> bool:
    r = subprocess.run(
        ["git", "cat-file", "-e", f"{ramo}:{caminho}"], cwd=RAIZ, capture_output=True, text=True, timeout=20
    )
    return r.returncode == 0


def test_secao_tem_linhas_e_estados_validos():
    linhas = _linhas()
    assert len(linhas) >= 25, len(linhas)
    assert {x["estado"] for x in linhas} <= {"feito", "parcial", "fora"}, {x["estado"] for x in linhas}
    assert sum(1 for x in linhas if x["estado"] == "feito") >= 10


@pytest.mark.parametrize("linha", [pytest.param(x, id=x["capacidade"][:50]) for x in _linhas()])
def test_feito_e_parcial_apontam_para_teste_existente(linha):
    testes = RE_TESTE.findall(linha["testado_por"])
    ramos = RE_RAMO.findall(linha["testado_por"])
    if linha["estado"] == "fora":
        assert not testes, "linha `fora` não pode citar teste"
        assert "(" in linha["linha"].split(" | ")[3], "linha `fora` nomeia o item ou a decisão que a cobre"
        return
    assert testes, f"linha `{linha['estado']}` sem teste citado: {linha['capacidade']}"
    faltando = []
    for t in testes:
        if (RAIZ / t).exists():
            continue
        if any(_existe_em(r, t) for r in ramos):
            continue
        faltando.append(t)
    assert not faltando, f"{linha['capacidade']}: teste(s) inexistente(s) em master e nos ramos {ramos}: {faltando}"


def test_urls_de_referencia_com_200_na_data():
    chaves_doc = set()
    for m in RE_CHAVE.finditer(_secao()):
        chaves_doc.update(c.strip() for c in m.group(1).split(","))
    lista = {}
    for linha in URLS.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            chave, url = linha.split("\t", 1)
            lista[chave] = url
    assert chaves_doc, "seção sem chaves [X-...] nos títulos"
    assert chaves_doc <= set(lista), f"chaves citadas sem URL em docs/urls_paridade.txt: {chaves_doc - set(lista)}"
    assert MEDIDAS.exists(), "rode scripts/paridade_urls_testar.py"
    m = json.loads(MEDIDAS.read_text(encoding="utf-8"))
    por_url = {u["url"]: u for u in m["urls"]}
    assert set(por_url) == set(lista.values()), "medida e lista de URLs divergem: rode o script de novo"
    ruins = [u for u, r in por_url.items() if r["http"] != 200]
    assert not ruins, ruins
    assert m["medidas"]["urls_200_na_data"]["valor"] == len(lista)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", m["gerado_em"])
