"""Item L7-06-d-paineis — cláusula "todo painel referencia só métricas que existem".

O teste percorre os JSON dos cinco painéis, extrai cada consulta, resolve as variáveis do painel e
pergunta ao Prometheus de homologação. Consulta que devolve vazio é 'No data' na tela — reprova.

Precisa da pilha de homologação no ar:
    bash deploy/paineis_homologacao.sh subir
    set -a; source /tmp/plat_paineis_homolog/ambiente; set +a
"""

import json
import os
import re
from pathlib import Path

import httpx
import pytest

RAIZ = Path(__file__).resolve().parents[2]
PAINEIS = RAIZ / "deploy/grafana/paineis"
PROM = os.environ.get("PLAT_PAINEIS_PROM")


def prometheus_no_ar() -> str:
    if not PROM:
        pytest.skip("PLAT_PAINEIS_PROM não definido (rode deploy/paineis_homologacao.sh subir)")
    try:
        httpx.get(f"{PROM}/-/ready", timeout=5).raise_for_status()
    except httpx.HTTPError as e:
        pytest.skip(f"{PROM} não responde: {e}")
    return PROM


def consulta(expr: str) -> list:
    r = httpx.get(f"{PROM}/api/v1/query", params={"query": expr}, timeout=30)
    r.raise_for_status()
    corpo = r.json()
    assert corpo["status"] == "success", (expr, corpo)
    return corpo["data"]["result"]


def valor_da_variavel(v: dict) -> str:
    """Resolve `label_values(<metrica>, <rotulo>)` do jeito que o Grafana resolve: pergunta os valores
    do rótulo ao Prometheus e fica com o primeiro. Sem isso a consulta iria com `$inquilino` literal."""
    q = v["query"]["query"] if isinstance(v["query"], dict) else v["query"]
    m = re.fullmatch(r"label_values\((.+),\s*([A-Za-z_][A-Za-z0-9_]*)\)", q.strip())
    assert m, f"variável em forma não prevista: {q}"
    r = httpx.get(f"{PROM}/api/v1/series", params={"match[]": m.group(1)}, timeout=30)
    r.raise_for_status()
    valores = sorted({s[m.group(2)] for s in r.json()["data"] if m.group(2) in s})
    assert valores, f"a variável {v['name']} não tem nenhum valor: o seletor abriria vazio ({q})"
    return valores[0]


def paineis() -> list[tuple[str, str, str]]:
    """(painel, quadro, consulta já com as variáveis resolvidas)."""
    fora = []
    for caminho in sorted(PAINEIS.glob("*.json")):
        d = json.loads(caminho.read_text())
        subst = {v["name"]: valor_da_variavel(v) for v in d["templating"]["list"]}
        for p in d["panels"]:
            for t in p["targets"]:
                expr = t["expr"]
                for nome, valor in subst.items():
                    expr = expr.replace(f"${{{nome}}}", valor).replace(f"${nome}", valor)
                fora.append((d["uid"], p["title"], expr))
    return fora


def test_toda_consulta_de_painel_devolve_serie():
    prometheus_no_ar()
    vazias = [(u, q, e) for u, q, e in paineis() if not consulta(e)]
    assert not vazias, "consulta de painel sem série (seria 'No data' na tela): " + json.dumps(
        [{"painel": u, "quadro": q, "consulta": e} for u, q, e in vazias], ensure_ascii=False, indent=2)


def nomes_de_metrica(expr: str) -> set[str]:
    """Nomes de métrica de uma consulta PromQL. Tira antes o que NÃO é métrica e se parece com uma:
    o conteúdo dos seletores de rótulo ({...}), o texto entre aspas, a lista de agrupamento depois de
    `by`/`without`/`on`/`ignoring`, e o nome de função (identificador seguido de parêntese)."""
    limpo = re.sub(r'"[^"]*"', '""', expr)
    limpo = re.sub(r"\{[^}]*\}", "", limpo)
    limpo = re.sub(r"\b(by|without|on|ignoring|group_left|group_right)\s*\([^)]*\)", " ", limpo)
    limpo = re.sub(r"\b[a-zA-Z_][a-zA-Z0-9_]*\s*\(", "(", limpo)
    palavras = {"or", "and", "unless", "offset", "bool", "inf", "nan"}
    return {n for n in re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", limpo) if n not in palavras}


def test_toda_metrica_citada_existe_no_prometheus():
    """Segunda rede, mais direta que a primeira: cada NOME de métrica citado em qualquer consulta tem
    de estar na lista de nomes que o Prometheus conhece. Pega erro de digitação que a primeira
    esconderia atrás de um `or vector(0)`."""
    prometheus_no_ar()
    conhecidos = set(httpx.get(f"{PROM}/api/v1/label/__name__/values", timeout=30).json()["data"])
    faltando = [{"painel": uid, "quadro": quadro, "metrica": n}
                for uid, quadro, expr in paineis()
                for n in sorted(nomes_de_metrica(expr)) if n not in conhecidos]
    assert not faltando, json.dumps(faltando, ensure_ascii=False, indent=2)


def test_o_or_vector_zero_so_aparece_onde_ausencia_significa_zero():
    """`or vector(0)` impede 'No data', e por isso é a porta dos fundos para um painel que não mede
    nada parecer saudável. Ele só é aceitável onde a ausência de série realmente quer dizer zero:
    contagem de erro e contagem de coisa do inquilino. Onde a ausência é NOTÍCIA (backup que nunca
    rodou, réplica que sumiu), o painel tem de mostrar o vazio."""
    permitido = {"8. Respostas 5xx (15 min)", "Cota de armazenamento usada", "Tamanho do schema de dado",
                 "Objetos guardados"}
    usam = {q for _, q, e in [(u, q, e) for u, q, e in
                              [(json.loads(c.read_text())["uid"], p["title"], t["expr"])
                               for c in sorted(PAINEIS.glob("*.json"))
                               for p in json.loads(c.read_text())["panels"]
                               for t in p["targets"]]] if "vector(0)" in e}
    assert usam <= permitido, usam - permitido
