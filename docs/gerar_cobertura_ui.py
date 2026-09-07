"""Mapa vivo de cobertura da interface (item UX-00-mapa-de-cobertura-da-interface).

Regra da trilha de interface: nenhuma rota da API e nenhuma funcionalidade fica "só no backend". Este gerador
cruza três fontes e escreve `docs/COBERTURA_UI.md`:

1. As rotas da API. Por padrão lê a aplicação viva (`app.main.app.openapi()`), a mesma fonte de `make openapi`;
   `--arquivo` lê `docs/openapi.json` quando não há ambiente para importar a aplicação.
2. O que as telas chamam. Varre `web/**/*.js` e `web/**/*.html` (fora `web/vendor`) atrás de literais de URL
   (`/api/...`, `/ogc/...`, `/rest/...`, `/svc/...`, `/tiles/...`), infere o método pelo auxiliar usado na mesma
   instrução (`obter`/`GET`, `enviar`/`POST`, `alterar`/`PUT`, `apagar`/`DELETE`, `remendar`/`PATCH`, `chamar('X'`,
   `fetch` com `method:`), resolve apelidos locais como ``const I = (id) => `/api/itens/${id}` `` e liga cada módulo às
   telas que o carregam (grafo de `import` a partir do `<script type="module">` de cada página em `app/paginas.py`).
3. O backlog do laço (`laco/estado.json`): toda hipótese com efeito visível (cita uma página `/algo` ou uma rota
   `/api/...`) é conferida contra as páginas e as rotas cobertas.

Estados de uma rota: `coberto` (chamada por módulo alcançável de uma tela), `sem controle` (o grupo de rotas tem
tela, mas esta rota ninguém chama), `sem tela` (nenhuma rota do grupo é chamada por tela alguma), `externo` (rota
para cliente externo — QGIS, ArcGIS, OGC — coberta quando alguma tela expõe o prefixo como URL; senão `externo sem
exposição`). Estado de erro: `com erro` quando a chamada está a até 12 linhas de `catch`/`.erro(`/`mensagemDe`/
`status`, ou quando o módulo lança `ErroApi` e todas as telas que o importam têm `catch`; senão `sem estado de erro`.
São heurísticas de texto, declaradas aqui e no cabeçalho do documento; o que elas não veem, o e2e vê.

Lacunas em rotas de ESCRITA (POST/PUT/PATCH/DELETE) são a linha de base `docs/cobertura_ui_lacunas.json`: o teste
`tests/unit/test_cobertura_ui.py` reprova quando aparece uma lacuna de escrita fora dessa lista — rota nova entra
com controle na tela, ou com o registro da lacuna (`--registrar`, que também acrescenta o item UX-<n> ao backlog).

Uso: `python3 docs/gerar_cobertura_ui.py` escreve o .md e a linha de base; `--check` só confere a linha de base;
`--registrar` acrescenta ao `laco/estado.json` um item UX-<n> por grupo com lacuna (idempotente, sob a mesma
trava de `marcar_item.py`)."""

from __future__ import annotations

import argparse
import datetime
import fcntl
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
WEB = RAIZ / "web"
PAGINAS_PY = RAIZ / "app" / "paginas.py"
OPENAPI_JSON = RAIZ / "docs" / "openapi.json"
DESTINO = RAIZ / "docs" / "COBERTURA_UI.md"
LACUNAS = RAIZ / "docs" / "cobertura_ui_lacunas.json"
EXCECOES = RAIZ / "docs" / "cobertura_ui_excecoes.json"
ESTADO = Path(os.environ.get("PLAT_LACO_ESTADO", "/home/dev/plataforma/laco/estado.json"))
TRAVA_ESTADO = ESTADO.with_name(".estado.lock")

VERBOS = ("get", "post", "put", "patch", "delete")
ESCRITA = {"POST", "PUT", "PATCH", "DELETE"}
PREFIXOS_URL = ("/api/", "/ogc/", "/rest/", "/svc/", "/tiles/", "/saude")
RE_ASPAS = re.compile(r"'([^'\n]*)'|\"([^\"\n]*)\"")
RE_APELIDO = re.compile(r"const\s+([A-Za-z_]\w*)\s*=\s*\([^)]*\)\s*=>\s*`([^`]*)`")
RE_IMPORT = re.compile(r"""(?:import\s*(?:[^'";]*?\s*from\s*)?|import\()\s*['"](\.{1,2}/[^'"]+)['"]""")
RE_SCRIPT = re.compile(r"""<script[^>]*type="module"[^>]*src="/static/([^"]+)\"""")
RE_PAGINA = re.compile(r"""^\s*"(/[^"]*)":\s*"([^"]+)",""", re.MULTILINE)
RE_PAGINA_ROTA = re.compile(r"""@router\.get\("(/[^"]*)",\s*include_in_schema=False\)"""
                            r"""(?:.*\n){1,4}?.*paginas\.servir\("([^"]+)"\)""")
RE_ROTA_NO_TEXTO = re.compile(r"(?<![\w/])(/(?:api|admin|conteudo|mapa|conta|entrar|conexoes|uploads|tarefas|"
                              r"aceitar-convite|redefinir-senha|estilo-guia|construtor|analise|aplicativo|p|c)"
                              r"(?:/[A-Za-z0-9_{}\-]+)*)")
PALAVRAS_TELA = ("tela", "página", "pagina", "painel", "botão", "botao", "widget", "formulário", "formulario",
                 "arrast", "e2e", "captura", "navegador", "visualizador", "construtor")
JANELA_ERRO = 12
RE_TRATA_ERRO = re.compile(r"\bcatch\b|\.erro\(|mensagemDe|\.status\b|ErroApi|onerror|\berro\b")


# ----------------------------------------------------------------------------------------------- rotas
def carregar_rotas(vivo: bool = True) -> dict[tuple[str, str], dict]:
    """{(MÉTODO, caminho): operação} da aplicação viva ou do docs/openapi.json."""
    if vivo:
        from app.main import app

        paths = app.openapi().get("paths", {})
    else:
        paths = json.loads(OPENAPI_JSON.read_text(encoding="utf-8")).get("paths", {})
    rotas = {}
    for caminho, ops in paths.items():
        for m in VERBOS:
            if m in ops:
                rotas[(m.upper(), caminho)] = ops[m]
    return rotas


def grupo_de(caminho: str, op: dict | None = None) -> str:
    """grupo = etiqueta (tag) da operação no OpenAPI, que é o router; sem etiqueta, 2º segmento em /api
    (eu, itens, grupos...) ou 1º segmento fora dele (ogc, rest, svc)."""
    if op and op.get("tags"):
        return str(op["tags"][0])
    seg = [s for s in caminho.split("/") if s]
    if not seg:
        return "/"
    if seg[0] == "api" and len(seg) > 1:
        return seg[1]
    return seg[0]


# ----------------------------------------------------------------------------------------------- páginas
def paginas() -> dict[str, str]:
    """{caminho da página: arquivo html} de app/paginas.py mais a raiz (index.html, servida em app/main.py)."""
    texto = PAGINAS_PY.read_text(encoding="utf-8")
    mapa = {"/": "index.html"}
    for caminho, arquivo in RE_PAGINA.findall(texto):
        mapa[caminho] = arquivo
    # páginas registradas fora de PAGINAS (ex.: /tarefas em app/jobs/rotas.py, com paginas.servir("tarefas.html"))
    for py in sorted((RAIZ / "app").rglob("*.py")):
        for caminho, arquivo in RE_PAGINA_ROTA.findall(py.read_text(encoding="utf-8", errors="replace")):
            mapa.setdefault(caminho, arquivo)
    return mapa


def arquivos_web() -> list[Path]:
    saida = []
    for p in sorted(WEB.rglob("*")):
        if p.is_file() and p.suffix in (".js", ".html") and "vendor" not in p.parts and "dados" not in p.parts:
            saida.append(p)
    return saida


def _resolver_import(origem: Path, alvo: str) -> Path | None:
    destino = (origem.parent / alvo).resolve()
    return destino if destino.is_file() else None


def grafo_modulos(arquivos: list[Path]) -> dict[Path, set[Path]]:
    grafo: dict[Path, set[Path]] = {}
    for arq in arquivos:
        texto = arq.read_text(encoding="utf-8", errors="replace")
        filhos = set()
        if arq.suffix == ".html":
            for src in RE_SCRIPT.findall(texto):
                d = (WEB / src).resolve()
                if d.is_file():
                    filhos.add(d)
        else:
            for alvo in RE_IMPORT.findall(texto):
                d = _resolver_import(arq, alvo)
                if d:
                    filhos.add(d)
        grafo[arq] = filhos
    return grafo


def modulos_da_tela(html: Path, grafo: dict[Path, set[Path]]) -> set[Path]:
    vistos, fila = set(), [html]
    while fila:
        atual = fila.pop()
        if atual in vistos:
            continue
        vistos.add(atual)
        fila.extend(grafo.get(atual, ()))
    return vistos


# ----------------------------------------------------------------------------------------------- chamadas
def _metodo_na_instrucao(trecho: str) -> str | None:
    m = re.search(r"\b(?:chamar|chamarBase|enviarBruto|fetchJson)\(\s*['\"](GET|POST|PUT|PATCH|DELETE)['\"]", trecho)
    if m:
        return m.group(1)
    m = re.search(r"method:\s*['\"](GET|POST|PUT|PATCH|DELETE)['\"]", trecho)
    if m:
        return m.group(1)
    for nome, metodo in (("remendar(", "PATCH"), ("obter(", "GET"), ("enviar(", "POST"), ("alterar(", "PUT"),
                         ("apagar(", "DELETE"), ("EventSource(", "GET"), ("fetch(", "GET")):
        if nome in trecho:
            return metodo
    return None


def _normalizar_template(t: str, apelidos: dict[str, str]) -> str:
    def troca(m):
        expr = m.group(1).strip()
        nome = re.match(r"([A-Za-z_]\w*)\(", expr)
        if nome and nome.group(1) in apelidos:
            return apelidos[nome.group(1)]
        return "{x}"

    while "${" in t:
        ini = t.index("${")
        prof, fim = 0, ini
        for fim in range(ini, len(t)):
            if t[fim] == "{":
                prof += 1
            elif t[fim] == "}":
                prof -= 1
                if prof == 0:
                    break
        t = t[:ini] + troca(re.match(r"(.*)", t[ini + 2: fim])) + t[fim + 1:]
    t = t.split("?", 1)[0]
    # `/api/usuarios${consulta(...)}` -> "/api/usuarios{x}" : o {x} colado a um segmento é a query string
    t = re.sub(r"(?<=[A-Za-z0-9_\-}])\{x\}$", "", t)
    return t.rstrip("/") or "/"


def literais(linha: str) -> list[str]:
    """literais de uma linha: templates com `${...}` aninhado (chaves e aspas dentro) viram texto com {x};
    depois as aspas simples e duplas fora dos templates."""
    saida, resto, i = [], [], 0
    while i < len(linha):
        if linha[i] != "`":
            resto.append(linha[i])
            i += 1
            continue
        j, prof, partes = i + 1, 0, []
        while j < len(linha):
            c = linha[j]
            if prof == 0 and c == "`":
                break
            if c == "$" and linha[j + 1: j + 2] == "{":
                prof += 1
                partes.append("${")
                j += 2
                continue
            if prof and c == "{":
                prof += 1
            elif prof and c == "}":
                prof -= 1
                if prof == 0:
                    partes.append("}")
                    j += 1
                    continue
            partes.append(c if prof == 0 else (c if c not in "`" else " "))
            j += 1
        saida.append("".join(partes))
        resto.append(" " * (j - i + 1))
        i = j + 1
    for m in RE_ASPAS.finditer("".join(resto)):
        saida.append(next(g for g in m.groups() if g is not None))
    return saida


def chamadas(arquivos: list[Path]) -> list[dict]:
    """[{arquivo, linha, url, metodo, trata_erro}] para todo literal que pareça URL da API."""
    saida = []
    for arq in arquivos:
        texto = arq.read_text(encoding="utf-8", errors="replace")
        apelidos = {}
        for nome, tmpl in RE_APELIDO.findall(texto):
            if tmpl.startswith(PREFIXOS_URL):
                apelidos[nome] = _normalizar_template(tmpl, {})
        linhas = texto.splitlines()
        lanca = "throw new ErroApi" in texto
        for i, linha in enumerate(linhas):
            nus = [apelidos[n] for n in apelidos if re.search(rf"[(,]\s*{n}\(", linha)]
            for bruto in literais(linha) + nus:
                if not (bruto.startswith(PREFIXOS_URL) or bruto.startswith("${")):
                    continue
                url = _normalizar_template(bruto, apelidos)
                if not url.startswith(PREFIXOS_URL):
                    continue
                metodo = _metodo_na_instrucao(linha)
                if not metodo and re.match(r"\s*[`'\"]", linha):
                    # linha de continuação de uma chamada aberta acima (só o argumento): o método está antes
                    metodo = _metodo_na_instrucao(" ".join(linhas[max(0, i - 2): i]))
                metodo = metodo or "GET"
                janela = "\n".join(linhas[max(0, i - JANELA_ERRO): i + JANELA_ERRO + 1])
                saida.append({
                    "arquivo": arq, "linha": i + 1, "url": url, "metodo": metodo,
                    "trata_erro": bool(RE_TRATA_ERRO.search(janela)), "lanca": lanca,
                })
    return saida


def _casa(template: str, caminho: str) -> bool:
    a, b = template.split("/"), caminho.split("/")
    if len(a) != len(b):
        return False
    return all(x == y or x == "{x}" or (y.startswith("{") and y.endswith("}")) for x, y in zip(a, b, strict=True))


# ----------------------------------------------------------------------------------------------- excecoes
def carregar_excecoes() -> list[dict]:
    if not EXCECOES.exists():
        return []
    return json.loads(EXCECOES.read_text(encoding="utf-8")).get("excecoes", [])


def _excecao_de(caminho: str, excecoes: list[dict]) -> dict | None:
    for e in excecoes:
        if caminho.startswith(e["prefixo"]):
            return e
    return None


# ----------------------------------------------------------------------------------------------- cruzamento
def cruzar(vivo: bool = True) -> dict:
    rotas = carregar_rotas(vivo)
    pags = paginas()
    arquivos = arquivos_web()
    grafo = grafo_modulos(arquivos)
    excecoes = carregar_excecoes()
    html_para_pagina: dict[Path, list[str]] = defaultdict(list)
    for caminho, arquivo in pags.items():
        html_para_pagina[(WEB / arquivo).resolve()].append(caminho)
    modulo_para_telas: dict[Path, set[str]] = defaultdict(set)
    texto_da_tela: dict[str, str] = {}
    texto_proprio: dict[str, str] = {}
    for html, caminhos in html_para_pagina.items():
        if not html.is_file():
            continue
        mods = modulos_da_tela(html, grafo)
        texto_da_tela[caminhos[0]] = "\n".join(m.read_text(encoding="utf-8", errors="replace") for m in mods)
        proprios = [m for m in mods if (WEB / "js" / "base") not in m.parents]
        texto_proprio[caminhos[0]] = "\n".join(m.read_text(encoding="utf-8", errors="replace") for m in proprios)
        for m in mods:
            modulo_para_telas[m].update(caminhos)
    todas = chamadas(arquivos)
    # módulos que lançam ErroApi: o erro é tratado se toda tela que o alcança tem catch
    tela_tem_catch = {c: ("catch" in t) for c, t in texto_da_tela.items()}
    linhas_rotas = []
    grupos_com_tela: set[str] = set()
    cobertura_por_rota: dict[tuple[str, str], list[dict]] = defaultdict(list)
    exposicao_texto = "\n".join(a.read_text(encoding="utf-8", errors="replace") for a in arquivos)
    for (metodo, caminho) in rotas:
        for c in todas:
            if c["metodo"] == metodo and _casa(c["url"], caminho):
                telas = sorted(modulo_para_telas.get(c["arquivo"], set()))
                if telas:
                    cobertura_por_rota[(metodo, caminho)].append({**c, "telas": telas})
    for (metodo, caminho), op in rotas.items():
        if cobertura_por_rota.get((metodo, caminho)):
            grupos_com_tela.add(grupo_de(caminho, op))
    for (metodo, caminho), op in sorted(rotas.items(), key=lambda kv: (kv[0][1], VERBOS.index(kv[0][0].lower()))):
        chamadas_rota = cobertura_por_rota.get((metodo, caminho), [])
        exc = _excecao_de(caminho, excecoes)
        if chamadas_rota:
            estado = "coberto"
            erro_ok = any(
                c["trata_erro"] or (c["lanca"] and all(tela_tem_catch.get(t, False) for t in c["telas"]))
                for c in chamadas_rota
            )
            estado_erro = "com erro" if erro_ok else "sem estado de erro"
            telas = sorted({t for c in chamadas_rota for t in c["telas"]})
            controles = sorted({f"{c['arquivo'].relative_to(RAIZ)}:{c['linha']}" for c in chamadas_rota})
        elif exc:
            expoe = exc["prefixo"] in exposicao_texto
            estado = "externo" if expoe else "externo sem exposição"
            estado_erro = "não se aplica"
            telas, controles = [], [exc["motivo"]]
        else:
            estado = "sem controle" if grupo_de(caminho, op) in grupos_com_tela else "sem tela"
            estado_erro = "não se aplica"
            telas, controles = [], []
        linhas_rotas.append({
            "metodo": metodo, "caminho": caminho, "grupo": grupo_de(caminho, op), "estado": estado,
            "estado_erro": estado_erro, "telas": telas, "controles": controles,
            "resumo": (op.get("summary") or "").strip(),
        })
    # telas: estados vazio/carregando/erro
    linhas_telas = []
    for caminho, arquivo in pags.items():
        t = texto_proprio.get(caminho, "")
        linhas_telas.append({
            "pagina": caminho, "arquivo": arquivo, "existe": (WEB / arquivo).is_file(),
            "vazio": bool(re.search(r"\bvazio\b|\.vazio\b|sem_resultado", t)),
            "carregando": bool(re.search(r"carregando|aria-busy|ariaBusy", t)),
            "erro": bool(re.search(r"\.erro\(|\bcatch\b", t)),
            "negado": bool(re.search(r"\b403\b|sem[_ .]?permiss|negado|privileg", t)),
        })
    # chamadas a rotas que não existem na API (URL morta na tela)
    mortas = []
    for c in todas:
        if not any(c["metodo"] == m and _casa(c["url"], p) for (m, p) in rotas) and c["url"] != "/saude":
            if any(_casa(c["url"], p) for (_m, p) in rotas):
                continue  # caminho existe com outro método (ex.: URL de imagem)
            mortas.append(f"{c['arquivo'].relative_to(RAIZ)}:{c['linha']} {c['metodo']} {c['url']}")
    return {"rotas": linhas_rotas, "telas": linhas_telas, "mortas": sorted(set(mortas)),
            "paginas": pags, "backlog": cruzar_backlog(pags, linhas_rotas)}


def cruzar_backlog(pags: dict[str, str], linhas_rotas: list[dict]) -> list[dict]:
    """hipóteses com efeito visível: cada página ou rota citada no texto do item, conferida."""
    if not ESTADO.exists():
        return []
    itens = json.loads(ESTADO.read_text(encoding="utf-8")).get("backlog", [])
    cobertas = {(r["metodo"], r["caminho"]) for r in linhas_rotas if r["estado"] in ("coberto", "externo")}
    caminhos_cobertos = {p for _m, p in cobertas}
    saida = []
    for it in itens:
        if it.get("estado") not in ("entregue", "parcial"):
            continue
        texto = f"{it.get('hipotese', '')} {it.get('portao_de_pronto', '')}"
        if not any(p in texto.lower() for p in PALAVRAS_TELA):
            continue
        refs = sorted({r.rstrip("/") for r in RE_ROTA_NO_TEXTO.findall(texto)})
        if not refs:
            saida.append({"item": it["id"], "estado_item": it["estado"], "ref": "", "veredito": "sem rota declarada"})
            continue
        for ref in refs:
            if ref.startswith("/api/"):
                ok = any(_casa(ref.replace("{id}", "{x}"), p) or p.startswith(ref) for p in caminhos_cobertos)
                veredito = "rota coberta" if ok else "rota sem tela"
            else:
                ok = ref in pags or any(p != "/" and (ref.startswith(p) or p.startswith(ref + "/")) for p in pags)
                veredito = "página existe" if ok else "página inexistente"
            saida.append({"item": it["id"], "estado_item": it["estado"], "ref": ref, "veredito": veredito})
    return saida


# ----------------------------------------------------------------------------------------------- saídas
def lacunas_de_escrita(resultado: dict) -> list[str]:
    return sorted(
        f"{r['metodo']} {r['caminho']}" for r in resultado["rotas"]
        if r["metodo"] in ESCRITA and r["estado"] not in ("coberto", "externo")
    )


def gerar_markdown(resultado: dict) -> str:
    rotas = resultado["rotas"]
    total = len(rotas)
    contagem = defaultdict(int)
    for r in rotas:
        contagem[r["estado"]] += 1
    sem_erro = sum(1 for r in rotas if r["estado_erro"] == "sem estado de erro")
    escrita_lacuna = lacunas_de_escrita(resultado)
    L = []
    L.append("# Cobertura da interface (gerado — não editar à mão)\n")
    L.append("Gerado por `docs/gerar_cobertura_ui.py` (item UX-00-mapa-de-cobertura-da-interface). Rotas lidas da "
             "aplicação; chamadas lidas de `web/`; telas de `app/paginas.py`. Heurísticas de texto declaradas no "
             "cabeçalho do gerador: o que elas não veem, o e2e vê. Regra da trilha: nenhuma rota fica só no backend.\n")
    L.append("## Placar\n")
    L.append("| medida | valor |\n|---|---|")
    L.append(f"| rotas (método × caminho) | {total} |")
    for est in ("coberto", "sem controle", "sem tela", "externo", "externo sem exposição"):
        L.append(f"| {est} | {contagem.get(est, 0)} |")
    L.append(f"| cobertas sem estado de erro perto da chamada | {sem_erro} |")
    L.append(f"| lacunas de ESCRITA (linha de base do teste) | {len(escrita_lacuna)} |")
    L.append(f"| URLs chamadas pela tela que não existem na API | {len(resultado['mortas'])} |\n")
    L.append("## Rotas → tela/controle → estado\n")
    L.append("| método | rota | grupo | tela | controle (arquivo:linha) | estado | erro |")
    L.append("|---|---|---|---|---|---|---|")
    for r in rotas:
        telas = ", ".join(f"`{t}`" for t in r["telas"]) or "—"
        controles = "<br>".join(f"`{c}`" for c in r["controles"]) or "—"
        L.append(f"| {r['metodo']} | `{r['caminho']}` | {r['grupo']} | {telas} | {controles} | **{r['estado']}** | "
                 f"{r['estado_erro']} |")
    L.append("\n## Telas → estados explícitos (heurística por texto dos módulos próprios da tela, fora web/js/base)\n")
    L.append("| página | arquivo | existe | vazio | carregando | erro | negado |\n|---|---|---|---|---|---|---|")
    for t in resultado["telas"]:
        s = lambda v: "sim" if v else "**não**"  # noqa: E731
        L.append(f"| `{t['pagina']}` | {t['arquivo']} | {s(t['existe'])} | {s(t['vazio'])} | {s(t['carregando'])} | "
                 f"{s(t['erro'])} | {s(t['negado'])} |")
    L.append("\n## Lacunas de escrita (cada grupo vira um item UX-<n> no backlog via `--registrar`)\n")
    if escrita_lacuna:
        por_grupo = defaultdict(list)
        for r in rotas:
            if f"{r['metodo']} {r['caminho']}" in escrita_lacuna:
                por_grupo[r["grupo"]].append(f"{r['metodo']} `{r['caminho']}` ({r['estado']})")
        for g in sorted(por_grupo):
            L.append(f"- **{g}**: " + "; ".join(por_grupo[g]))
    else:
        L.append("nenhuma.")
    L.append("\n## URLs chamadas pela tela sem rota correspondente na API\n")
    L.extend(f"- `{m}`" for m in resultado["mortas"]) if resultado["mortas"] else L.append("nenhuma.")
    L.append("\n## Backlog: hipóteses com efeito visível × páginas e rotas cobertas\n")
    if resultado["backlog"]:
        com_ref = [b for b in resultado["backlog"] if b["ref"]]
        sem_ref = sorted({b["item"] for b in resultado["backlog"] if not b["ref"]})
        L.append("| item | estado do item | referência no texto | veredito |\n|---|---|---|---|")
        for b in com_ref:
            L.append(f"| {b['item']} | {b['estado_item']} | `{b['ref']}` | {b['veredito']} |")
        L.append(f"\nItens com efeito visível que não citam página nem rota no texto ({len(sem_ref)}; a cobertura "
                 "deles é conferida pelo e2e do item, não por este cruzamento): " + ", ".join(sem_ref))
    else:
        L.append("backlog indisponível nesta máquina (PLAT_LACO_ESTADO).")
    return "\n".join(L) + "\n"


def escrever(resultado: dict) -> None:
    DESTINO.write_text(gerar_markdown(resultado), encoding="utf-8")
    LACUNAS.write_text(json.dumps({
        "descricao": "lacunas de ESCRITA conhecidas (linha de base de tests/unit/test_cobertura_ui.py); "
                     "encolhe conforme a trilha UX fecha itens; gerado por docs/gerar_cobertura_ui.py",
        "lacunas": lacunas_de_escrita(resultado),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def lacunas_conhecidas() -> set[str]:
    if not LACUNAS.exists():
        return set()
    return set(json.loads(LACUNAS.read_text(encoding="utf-8")).get("lacunas", []))


def conferir(resultado: dict) -> list[str]:
    """lacunas de escrita que NÃO estão na linha de base: é o que reprova."""
    return sorted(set(lacunas_de_escrita(resultado)) - lacunas_conhecidas())


# ----------------------------------------------------------------------------------------------- backlog
def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")


def registrar_itens(resultado: dict) -> list[str]:
    """um item UX-<n> por grupo com lacuna de escrita; idempotente por `origem`; mesma trava de marcar_item.py."""
    por_grupo = defaultdict(list)
    for r in resultado["rotas"]:
        if r["metodo"] in ESCRITA and r["estado"] not in ("coberto", "externo"):
            por_grupo[r["grupo"]].append(r)
    if not por_grupo:
        return []
    trava = open(TRAVA_ESTADO, "a+")  # noqa: SIM115 — vive até o fim do processo, como em marcar_item.py
    fcntl.flock(trava, fcntl.LOCK_EX)
    e = json.loads(ESTADO.read_text(encoding="utf-8"))
    backlog = e["backlog"]
    origens = {it.get("origem") for it in backlog}
    numeros = [int(m.group(1)) for it in backlog if (m := re.match(r"UX-(\d+)-", it["id"]))]
    proximo = max(numeros + [9]) + 1
    criados = []
    hoje = datetime.date.today().isoformat()
    for grupo in sorted(por_grupo):
        origem = f"UX-00 cobertura: {grupo}"
        if origem in origens:
            continue
        rotas = por_grupo[grupo]
        lista = "; ".join(f"{r['metodo']} {r['caminho']}" for r in rotas)
        estado = "sem tela" if all(r["estado"] == "sem tela" for r in rotas) else "sem controle"
        iid = f"UX-{proximo:02d}-{_slug(grupo)}-{_slug(estado)}"
        backlog.append({
            "id": iid, "linha": "L2 plataforma", "prioridade": 2, "estado": "pendente", "dependencias": [
                "UX-01-sistema-de-design"],
            "hipotese": f"lacuna de interface no grupo `{grupo}` ({estado}): as rotas de escrita {lista} ganham "
                        "controle em tela (botão, formulário ou ação de lista) com estados vazio, carregando, erro "
                        "e negado, textos por i18n e o mesmo sistema de design",
            "portao_de_pronto": "cada rota listada é chamada por um controle alcançável de uma tela de app/paginas.py; "
                                "e2e exercita o controle com captura; 0 erro de console; axe 0 violações sérias; "
                                "docs/COBERTURA_UI.md regenerado sem a lacuna e docs/cobertura_ui_lacunas.json encolhe",
            "refutacao": "erro da API (422/403/409) aparece nomeado no controle, nunca tela quebrada nem 422 cru",
            "papeis": ["construtor", "fila"], "tentativas": 0, "turno": None, "bloqueio": None, "tamanho": "M",
            "criado_em": hoje, "origem": origem,
        })
        criados.append(iid)
        proximo += 1
    if criados:
        b = e["backlog"]
        e["placar"] = {**e.get("placar", {}), "total": len(b),
                       "entregues": sum(x["estado"] == "entregue" for x in b),
                       "parciais": sum(x["estado"] == "parcial" for x in b),
                       "refutados": sum(x["estado"] == "refutado" for x in b)}
        tmp = ESTADO.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(e, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, ESTADO)
    fcntl.flock(trava, fcntl.LOCK_UN)
    return criados


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="só confere a linha de base de lacunas de escrita")
    ap.add_argument("--arquivo", action="store_true", help="lê docs/openapi.json em vez da aplicação viva")
    ap.add_argument("--registrar", action="store_true", help="acrescenta itens UX-<n> ao backlog por grupo com lacuna")
    a = ap.parse_args(argv)
    resultado = cruzar(vivo=not a.arquivo)
    if a.check:
        novas = conferir(resultado)
        if novas:
            print("lacunas de ESCRITA fora da linha de base (rota nova sem tela):", file=sys.stderr)
            for n in novas:
                print(f"  {n}", file=sys.stderr)
            print("saída: dê controle na tela, ou registre a lacuna com `python3 docs/gerar_cobertura_ui.py "
                  "--registrar` (cria o item UX-<n>) e comite docs/cobertura_ui_lacunas.json", file=sys.stderr)
            return 1
        print(f"cobertura ok: {len(lacunas_de_escrita(resultado))} lacunas de escrita, todas na linha de base")
        return 0
    escrever(resultado)
    print(f"{DESTINO.relative_to(RAIZ)} e {LACUNAS.relative_to(RAIZ)} escritos: {len(resultado['rotas'])} rotas, "
          f"{len(lacunas_de_escrita(resultado))} lacunas de escrita")
    if a.registrar:
        criados = registrar_itens(resultado)
        print("itens criados no backlog: " + (", ".join(criados) if criados else "nenhum novo"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
