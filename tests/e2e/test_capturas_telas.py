"""Capturas de TODAS as telas do produto em 1280 e 390 px, com rótulo (PLAT_CAPTURA_ROTULO=antes|depois; padrão
"depois"), para a cláusula "capturas das telas antes/depois" do item UX-01-sistema-de-design e para qualquer item de
tela que precise do estado inteiro do produto numa olhada. Arquivos:
tests/e2e/capturas/UX-01_<rotulo>_<tela>_<largura>.png.
Também confere, tela a tela, 0 erro de console e nenhuma resposta >= 400 fora das esperadas (as públicas sem token
respondem 4xx de propósito). A lista de telas vem de app/paginas.py (as com parâmetro de caminho ficam de fora: não
há dado fixo para elas aqui; os e2e dos itens de tela as cobrem com dado criado na hora)."""

import os
import re
from pathlib import Path

import pytest

from tests.e2e.apoio import CAPTURAS, RAIZ, Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "UX-01"
LARGURAS = (1280, 390)
RE_PAGINA = re.compile(r'^\s*"(/[^"{]*)":\s*"([^"]+)",', re.MULTILINE)
# públicas: abrem sem sessão e, sem token, mostram o estado de erro (é o que se quer ver)
PUBLICAS = {"/entrar", "/aceitar-convite", "/redefinir-senha"}
# páginas que precisam de parâmetro de consulta para ter conteúdo (sem ele mostram o estado vazio/erro, que também vale)
SEM_SESSAO_OK = PUBLICAS


def telas() -> list[str]:
    texto = (RAIZ / "app" / "paginas.py").read_text(encoding="utf-8")
    lista = ["/"] + [c for c, _ in RE_PAGINA.findall(texto)]
    lista.append("/tarefas")
    return sorted(set(lista))


def _nome(caminho: str) -> str:
    return "raiz" if caminho == "/" else caminho.strip("/").replace("/", "-")


def test_captura_todas_as_telas(page, base_url, credenciais_demo):
    rotulo = os.environ.get("PLAT_CAPTURA_ROTULO", "depois")
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    # sem sessão, as páginas protegidas redirecionam para /entrar (esperado)
    tela.esperar_status(401, 404, 410, 422)
    tela.entrar(slug, login, senha, proximo="/conta")
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    feitas: list[Path] = []
    nao_prontas: list[str] = []
    for caminho in telas():
        for largura in LARGURAS:
            page.set_viewport_size({"width": largura, "height": 900 if largura > 400 else 844})
            page.goto(caminho, wait_until="domcontentloaded")
            try:
                page.wait_for_selector("body[data-pronto='1']", timeout=8000)
            except Exception:  # noqa: BLE001 — a captura do estado quebrado é o que se quer ver no "antes"
                nao_prontas.append(f"{caminho}@{largura}")
            alvo = CAPTURAS / f"{ITEM}_{rotulo}_{_nome(caminho)}_{largura}.png"
            page.screenshot(path=str(alvo), full_page=True)
            feitas.append(alvo)
    page.set_viewport_size({"width": 1280, "height": 800})
    assert len(feitas) == len(telas()) * len(LARGURAS)
    assert all(p.stat().st_size > 1000 for p in feitas), "captura vazia"
    print(f"telas sem body[data-pronto] ({rotulo}): {nao_prontas}")
    if rotulo == "antes":
        return  # o estado anterior pode estar quebrado; o "depois" tem de estar limpo
    assert nao_prontas == [], f"telas que não ficaram prontas (sem body[data-pronto]): {nao_prontas}"
    tela.verificar()
