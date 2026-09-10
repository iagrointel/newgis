"""Gerador do manual (item L7-04-a-manual-capturas-geradas).

Uma seção por tela do aplicativo: o texto do cronista vive em docs/manual/<tela>.md (front matter
+ corpo Markdown); a captura é produzida pelo e2e da própria tela e INSERIDA daqui, nunca à mão.
Este script:

1. valida o conjunto (ids únicos, e2e existe, o e2e produz a captura citada, a página do app
   declara data-ajuda=<id>);
2. copia a captura base para tests/e2e/capturas/<tela>@<versao>.png — captura de versão diferente
   da atual REPROVA o build;
3. monta o site interno docs/manual/index.html (HTML estático, noindex, capturas copiadas ao lado);
4. monta web/dados/manual.json (seções para o painel de ajuda por contexto do aplicativo);
5. monta docs/manual/manual.pdf pelo mesmo HTML de impressão (weasyprint).

Nada aqui roda pytest: a regeneração de capturas é o alvo `make manual`, que chama o semáforo
`laco/roda_teste.sh` com os arquivos devolvidos por `--arquivos-e2e` e DEPOIS chama este script
com `--pular-e2e`. Uso direto em base de trilha:

    set -a; source laco/var/trilha/<trilha>.env; set +a
    venv/bin/python docs/gerar_manual.py --validar
    venv/bin/python docs/gerar_manual.py --pular-e2e
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DIR_MANUAL = RAIZ / "docs" / "manual"
DIR_CAPTURAS = RAIZ / "tests" / "e2e" / "capturas"
DIR_WEB_DADOS = RAIZ / "web" / "dados"
FRONTE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
CAMPOS_OBRIGATORIOS = [
    "id", "titulo", "titulo_en", "titulo_es", "resumo", "resumo_en", "resumo_es",
    "classe", "caminho", "e2e", "captura", "e2e_captura",
]
CAMPOS_LISTA = ["palavras", "palavras_en", "palavras_es"]


def versao_atual() -> str:
    sys.path.insert(0, str(RAIZ))
    from app.versao import versao
    return versao()


def _valor_lista(texto: str) -> list[str]:
    texto = texto.strip()
    if not texto:
        return []
    if texto.startswith("["):
        return [p.strip().strip("'\"") for p in texto[1:-1].split(",") if p.strip()]
    return [texto]


def _parse_front(caminho: Path) -> tuple[dict, str]:
    """front matter mínimo (chave: valor e chave: [a, b]) sem dependência de yaml no leitor de docs."""
    texto = caminho.read_text(encoding="utf-8")
    m = FRONTE.match(texto)
    if not m:
        raise SystemExit(f"{caminho.name}: sem front matter (--- em cima e embaixo)")
    meta: dict = {}
    for linha in m.group(1).splitlines():
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        chave, _, valor = linha.partition(":")
        chave = chave.strip()
        valor = valor.strip()
        if not chave or valor == "":
            raise SystemExit(f"{caminho.name}: linha de front matter sem valor: {linha!r}")
        meta[chave] = _valor_lista(valor) if chave in CAMPOS_LISTA else valor.strip("'\"")
    corpo = texto[m.end():].strip()
    return meta, corpo


def carregar_secoes() -> list[dict]:
    """todas as seções do manual, validadas; ordem alfabética por título (o sumário segue a ordem)."""
    if not DIR_MANUAL.is_dir():
        raise SystemExit(f"{DIR_MANUAL} não existe")
    secoes = []
    for caminho in sorted(DIR_MANUAL.glob("*.md")):
        if caminho.name == "LEIA.md":
            continue
        meta, corpo = _parse_front(caminho)
        faltando = [c for c in CAMPOS_OBRIGATORIOS if c not in meta]
        if faltando:
            raise SystemExit(f"{caminho.name}: front matter sem {faltando}")
        if meta["classe"] not in ("tela", "administrador"):
            raise SystemExit(f"{caminho.name}: classe desconhecida {meta['classe']!r}")
        for campo in CAMPOS_LISTA:
            meta.setdefault(campo, [])
        secoes.append({"arquivo": caminho.name, **meta, "_corpo": corpo})
    if not secoes:
        raise SystemExit("nenhuma seção em docs/manual")
    ids = [s["id"] for s in secoes]
    duplicados = {i for i in ids if ids.count(i) > 1}
    if duplicados:
        raise SystemExit(f"ids repetidos em docs/manual: {sorted(duplicados)}")
    return secoes


def validar(secoes: list[dict]) -> None:
    """cláusulas estruturais: e2e existe e produz a captura citada; página declara data-ajuda."""
    for s in secoes:
        if s["classe"] != "tela":
            continue
        e2e = RAIZ / s["e2e"]
        if not e2e.is_file():
            raise SystemExit(f"{s['arquivo']}: e2e {s['e2e']} não existe")
        # e2e_captura = trecho literal que o e2e usa para gravar (Tela.capturar("x") ou
        # "{ITEM}_x.png"); captura = nome final do arquivo em tests/e2e/capturas
        if s["e2e_captura"] not in e2e.read_text(encoding="utf-8"):
            raise SystemExit(f"{s['arquivo']}: {e2e.name} não contém {s['e2e_captura']!r}")
        pagina = RAIZ / "web" / s["pagina"]
        if not pagina.is_file():
            raise SystemExit(f"{s['arquivo']}: página {s['pagina']} não existe")
        if f'data-ajuda="{s["id"]}"' not in pagina.read_text(encoding="utf-8"):
            raise SystemExit(f"{s['arquivo']}: {s['pagina']} sem data-ajuda=\"{s['id']}\"")
    # toda chave de ajuda declarada numa página tem seção
    chaves = {s["id"] for s in secoes}
    for pagina in RAIZ.joinpath("web").rglob("*.html"):
        for m in re.finditer(r'data-ajuda="([^"]+)"', pagina.read_text(encoding="utf-8")):
            if m.group(1) not in chaves:
                raise SystemExit(f"{os.path.relpath(pagina, RAIZ)}: data-ajuda={m.group(1)!r} sem seção no manual")


def desatualizadas(versao: str, secoes: list[dict]) -> list[str]:
    """capturas <tela>@<versao-antiga>.png que não batem com a versão dada (o build reprova)."""
    velhas = []
    for s in secoes:
        for captura in DIR_CAPTURAS.glob(f"{s['id']}@*.png"):
            if captura.name != f"{s['id']}@{versao}.png":
                velhas.append(captura.name)
    return sorted(velhas)


def copiar_capturas(versao: str, secoes: list[dict]) -> list[str]:
    """captura base (produzida pelo e2e) -> <tela>@<versao>.png; devolve as que ficaram sem base."""
    sem_base = []
    for s in secoes:
        if s["classe"] != "tela":
            continue
        base = DIR_CAPTURAS / s["captura"]
        destino = DIR_CAPTURAS / f"{s['id']}@{versao}.png"
        if base.is_file():
            shutil.copyfile(base, destino)
        elif not destino.is_file():
            sem_base.append(s["captura"])
    return sem_base


def _corpo_html(corpo_md: str) -> str:
    import markdown
    return markdown.markdown(corpo_md, extensions=["tables", "fenced_code"])


def _texto_puro(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def montar_json(versao: str, secoes: list[dict]) -> Path:
    """web/dados/manual.json: o que o painel de ajuda por contexto carrega (/static/dados/manual.json)."""
    saida = {
        "versao": versao,
        "secoes": [
            {
                "id": s["id"],
                "titulo": s["titulo"],
                "titulo_en": s["titulo_en"],
                "titulo_es": s["titulo_es"],
                "resumo": s["resumo"],
                "resumo_en": s["resumo_en"],
                "resumo_es": s["resumo_es"],
                "palavras": s["palavras"],
                "palavras_en": s["palavras_en"],
                "palavras_es": s["palavras_es"],
                "caminho": s["caminho"],
                "corpo": _corpo_html(s["_corpo"]),
            }
            for s in secoes
        ],
    }
    DIR_WEB_DADOS.mkdir(parents=True, exist_ok=True)
    destino = DIR_WEB_DADOS / "manual.json"
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return destino


ESTILO_SITIO = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0 auto; max-width: 56rem; padding: 1.5rem; font: 15px/1.55 system-ui, sans-serif; color: #1c2430; background: #f4f5f2; }
a { color: #23527c; }
.cabecalho { border-bottom: 2px solid #1c2430; padding-bottom: .75rem; margin-bottom: 1.5rem; }
.cabecalho h1 { margin: 0; font-size: 1.6rem; }
.cabecalho p { margin: .25rem 0 0; color: #55606e; }
nav.sumario { background: #fff; border: 1px solid #d7dad3; border-radius: 6px; padding: .75rem 1rem; margin-bottom: 1.5rem; }
nav.sumario li { margin: .15rem 0; }
section { background: #fff; border: 1px solid #d7dad3; border-radius: 6px; padding: 1rem 1.25rem; margin-bottom: 1.5rem; }
section img { max-width: 100%; border: 1px solid #d7dad3; border-radius: 4px; }
.fraco { color: #55606e; font-size: .85rem; }
"""


def _cabecalho(versao: str, titulo: str) -> str:
    return (
        f'<div class="cabecalho"><h1>{titulo}</h1>'
        f"<p>plat {versao} · análise / beta privado · gerado de docs/manual e das capturas do e2e</p></div>"
    )


def montar_sitio(versao: str, secoes: list[dict]) -> Path:
    """docs/manual/index.html: site estático interno, noindex, capturas copiadas para docs/manual/capturas."""
    destino_capturas = DIR_MANUAL / "capturas"
    destino_capturas.mkdir(parents=True, exist_ok=True)
    itens_sumario = []
    secoes_html = []
    for s in secoes:
        ancora = s["id"]
        itens_sumario.append(f'<li><a href="#{ancora}">{s["titulo"]}</a></li>')
        figura = ""
        if s["classe"] == "tela":
            origem = DIR_CAPTURAS / f"{s['id']}@{versao}.png"
            if not origem.is_file():
                raise SystemExit(f"{s['arquivo']}: falta a captura {origem.name} (rode o e2e antes)")
            shutil.copyfile(origem, destino_capturas / origem.name)
            figura = (
                f'<figure><img src="capturas/{origem.name}" alt="captura da tela {s["titulo"]} na versão {versao}">'
                f"<figcaption class=\"fraco\">captura {origem.name} · versão {versao}</figcaption></figure>"
            )
        corpo = _corpo_html(s["_corpo"])
        secoes_html.append(
            f'<section id="{ancora}" data-ajuda="{s["id"]}"><h2>{s["titulo"]}</h2>'
            f"<p class=\"fraco\">{s['caminho']}</p>{figura}{corpo}</section>"
        )
    html = (
        "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n"
        '<meta name="robots" content="noindex, nofollow">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>Manual do plat · {versao}</title>\n"
        f"<style>{ESTILO_SITIO}</style>\n</head>\n<body>\n"
        + _cabecalho(versao, "Manual do plat")
        + '<nav class="sumario"><strong>Sumário</strong><ul>' + "".join(itens_sumario) + "</ul></nav>\n"
        + "\n".join(secoes_html)
        + "\n</body>\n</html>\n"
    )
    destino = DIR_MANUAL / "index.html"
    destino.write_text(html, encoding="utf-8")
    return destino


ESTILO_PDF = """
@page { size: A4; margin: 18mm 16mm; @bottom-right { content: counter(page) " / " counter(pages); font: 9px sans-serif; color: #55606e; } }
body { font: 10.5px/1.5 "DejaVu Sans", sans-serif; color: #1c2430; }
h1 { font-size: 20px; border-bottom: 1.5px solid #1c2430; padding-bottom: 4px; }
h2 { font-size: 15px; margin: 0 0 4px; }
section { page-break-inside: avoid; margin: 0 0 14px; }
section > h2 { border-bottom: 1px solid #d7dad3; padding-bottom: 2px; }
img { max-width: 100%; max-height: 150mm; border: 0.5px solid #d7dad3; }
figcaption { font-size: 8px; color: #55606e; }
figure { margin: 6px 0; }
.fraco { font-size: 8.5px; color: #55606e; margin: 2px 0 6px; }
nav.sumario { column-count: 2; font-size: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 9.5px; }
th, td { border: 0.5px solid #d7dad3; padding: 3px 5px; text-align: left; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 9px; }
pre { white-space: pre-wrap; word-break: break-all; }
"""


def montar_pdf(versao: str, secoes: list[dict]) -> Path:
    """docs/manual/manual.pdf: o mesmo conteúdo, página A4; weasyprint do HTML de impressão."""
    import html as modulo_html
    secoes_pdf = []
    itens_sumario = []
    for s in secoes:
        itens_sumario.append(f"<li>{modulo_html.escape(s['titulo'])}</li>")
        figura = ""
        if s["classe"] == "tela":
            origem = DIR_MANUAL / "capturas" / f"{s['id']}@{versao}.png"
            if origem.is_file():
                figura = (
                    f'<figure><img src="capturas/{origem.name}" alt="captura da tela {modulo_html.escape(s["titulo"])}">'
                    f'<figcaption>captura {modulo_html.escape(origem.name)} · versão {versao}</figcaption></figure>'
                )
        secoes_pdf.append(
            f'<section><h2>{modulo_html.escape(s["titulo"])}</h2>'
            f'<p class="fraco">{modulo_html.escape(s["caminho"])}</p>{figura}{_corpo_html(s["_corpo"])}</section>'
        )
    html = (
        "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>Manual do plat · {versao}</title>\n<style>{ESTILO_PDF}</style>\n</head>\n<body>\n"
        + _cabecalho(versao, "Manual do plat")
        + "<p class=\"fraco\">análise / beta privado · documento interno · gerado de docs/manual e das capturas do e2e</p>"
        + '<nav class="sumario"><strong>Sumário</strong><ol>' + "".join(itens_sumario) + "</ol></nav>\n"
        + "\n".join(secoes_pdf)
        + "\n</body>\n</html>\n"
    )
    html_temp = DIR_MANUAL / "impressao.html"
    html_temp.write_text(html, encoding="utf-8")
    destino = DIR_MANUAL / "manual.pdf"
    # o weasyprint mora no ~/.local do usuário (fora da venv): tirar PYTHONNOUSERSITE do ambiente
    # do filho, senão o make (que o exporta) esconde o módulo e o PDF morre
    ambiente = {k: v for k, v in os.environ.items() if k != "PYTHONNOUSERSITE"}
    pronto = subprocess.run(
        ["weasyprint", str(html_temp), str(destino)], cwd=str(DIR_MANUAL),
        capture_output=True, text=True, env=ambiente,
    )
    if pronto.returncode != 0:
        raise SystemExit(f"weasyprint falhou ({pronto.returncode}): {pronto.stderr[-800:]}")
    html_temp.unlink()
    return destino


def montar(secoes: list[dict], com_pdf: bool = True) -> None:
    versao = versao_atual()
    velhas = desatualizadas(versao, secoes)
    if velhas:
        raise SystemExit(
            "capturas desatualizadas (versão diferente da atual): reprova o build — regenere com make manual: "
            + ", ".join(velhas)
        )
    sem_base = copiar_capturas(versao, secoes)
    if sem_base:
        raise SystemExit(
            "capturas base ausentes em tests/e2e/capturas (rode o e2e da tela): " + ", ".join(sem_base)
        )
    sitio = montar_sitio(versao, secoes)
    json_manual = montar_json(versao, secoes)
    print(f"manual {versao}: {len(secoes)} seções -> {os.path.relpath(sitio, RAIZ)}, {os.path.relpath(json_manual, RAIZ)}")
    if com_pdf:
        pdf = montar_pdf(versao, secoes)
        print(f"pdf: {os.path.relpath(pdf, RAIZ)} ({pdf.stat().st_size} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validar", action="store_true", help="só valida o conjunto (barato, sem captura)")
    parser.add_argument("--arquivos-e2e", action="store_true", help="imprime os arquivos de e2e que produzem as capturas")
    parser.add_argument("--pular-e2e", action="store_true", help="usa as capturas já existentes (o e2e rodou antes)")
    parser.add_argument("--so-json", action="store_true", help="só regenera web/dados/manual.json (não exige captura)")
    parser.add_argument("--sem-pdf", action="store_true", help="não monta o PDF")
    opcoes = parser.parse_args()
    secoes = carregar_secoes()
    if opcoes.arquivos_e2e:
        arquivos = sorted({s["e2e"] for s in secoes if s["classe"] == "tela"})
        print(" ".join(arquivos))
        return
    validar(secoes)
    if opcoes.validar:
        print(f"valido: {len(secoes)} seções, {len({s['e2e'] for s in secoes if s['classe'] == 'tela'})} arquivos de e2e")
        return
    if opcoes.so_json:
        destino = montar_json(versao_atual(), secoes)
        print(f"json: {os.path.relpath(destino, RAIZ)}")
        return
    montar(secoes, com_pdf=not opcoes.sem_pdf)


if __name__ == "__main__":
    main()
