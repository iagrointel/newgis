"""Migracao da folha antiga `web/style.css` para `estilo/base.css` + `estilo/componentes.css`, tela a tela.

Continuacao do item L0-14-identidade-visual, que zerou os literais de cor e deixou a catraca
`TELAS_NA_FOLHA_ANTIGA` em tests/unit/test_estilo_tokens.py sem migrar nenhuma tela. Aqui a catraca desce.

O que este modulo prova, por tela e por leva:
  (1) CAPTURA antes e depois, nos dois temas, em tests/e2e/capturas/MIG_<tela>_{antes_*,depois_*}.png;
  (2) MESMA ESTRUTURA: a impressao digital do DOM (caminho tag#id.classe de cada elemento, em ordem) tem de ser
      IGUAL antes e depois. Isto e troca de folha, nao redesenho: se a arvore muda, a tela reprova;
  (3) CONTRASTE AA de todo no de texto visivel, nos dois temas, com a mesma formula do L0-14 (WCAG 2, cor
      calculada sobre o fundo composto pelos ancestrais), medido ANTES e DEPOIS: o alvo e nao introduzir nenhuma;
  (4) axe-core (color-contrast + nomes + rotulos) antes e depois, pelo apoio_axe (rota interceptada, a CSP do
      produto recusa script inline).

Como rodar (as duas fases, a comparacao e as medidas de uma vez):

    bash tests/e2e/regerar_capturas_migracao.sh <leva>

O modulo sozinho roda uma fase de cada vez:

    PLAT_FASE=antes  PLAT_LEVA=1 venv/bin/pytest tests/e2e/test_migracao_folha.py --base-url http://127.0.0.1:8872
    PLAT_FASE=depois PLAT_LEVA=1 venv/bin/pytest tests/e2e/test_migracao_folha.py --base-url http://127.0.0.1:8871

Chromium: o do PLAYWRIGHT. O `google-chrome` do sistema quebra nesta maquina. E nunca `ulimit -v` para conter
memoria (o Chromium morre com SIGTRAP sob teto de enderecamento virtual): use
`systemd-run --scope -p MemoryMax=...`."""
# ruff: noqa: E501 -- o JS de medicao fica em uma linha por legibilidade do proprio JS

import json
import os
import re
from pathlib import Path

import pytest

from tests.e2e import apoio_axe
from tests.e2e.apoio import Tela, credenciais
from tests.e2e.test_estilo import JS_CONTRASTE

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "MIG"
ITEM_MEDIDA = "L0-14-b-migracao-folha"
AQUI = Path(__file__).resolve().parent
CAPTURAS = AQUI / "capturas"
MANIFESTO = AQUI / "telas_migracao.json"
SAIDA = AQUI / "migracao_saida"

# valor de parametro de rota que existe em qualquer instalacao: nao existe, e a tela tem de saber mostrar o
# vazio/erro dela. A foto do estado vazio serve ao par antes/depois tanto quanto a do estado cheio.
PARAMETRO = "00000000-0000-0000-0000-000000000000"

# teto da foto de pagina inteira, em pixels de altura (ver o comentario no ponto da captura)
ALTURA_MAXIMA_DA_FOTO = 30000

# impressao digital da ARVORE: tag, id e classes de cada elemento, em ordem de documento. Nao entra estilo
# nenhum - o que muda de proposito na migracao e a folha, nao a arvore.
JS_ESTRUTURA = r"""
() => {
  const saida = [];
  const andar = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_ELEMENT);
  for (let e = document.documentElement; e; e = andar.nextNode()) {
    if (e.closest('script, style, noscript')) continue;
    // <link> fica FORA da impressao digital: trocar a folha que a tela liga e exatamente o que esta
    // migracao faz (uma linha de style.css vira duas, base.css + componentes.css). Medir o <link>
    // faria a prova acusar como "arvore mudou" a unica mudanca deliberada, e nenhuma leva passaria.
    // O que tem de ficar igual, e fica medido, e a arvore que o usuario ve: head sem link, e o body
    // inteiro com tag, id e classes de cada elemento em ordem de documento.
    if (e.tagName === 'LINK') continue;
    const cls = (e.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean).sort().join('.');
    saida.push(e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (cls ? '.' + cls : ''));
  }
  return saida;
}
"""

# A tela monta sozinha (busca a API, desenha lista, formulario). Fotografar e medir a arvore no
# primeiro instante em que body[data-pronto=1] aparece pega a tela em pontos DIFERENTES do desenho a
# cada corrida -- na leva 1 a mesma tela deu 72 elementos numa fase e 247 na outra, sem nenhuma relacao
# com a folha. Antes de medir, espera-se a arvore PARAR: duas leituras iguais separadas por um intervalo,
# ate um teto. Nao e conserto de tela nenhuma; e tirar o relogio de dentro da medida.
def _esperar_assentar(page, intervalo_ms: int = 400, teto_ms: int = 12000) -> None:
    anterior, gasto = None, 0
    while gasto < teto_ms:
        atual = page.evaluate("() => document.documentElement.getElementsByTagName('*').length")
        if atual == anterior:
            return
        anterior = atual
        page.wait_for_timeout(intervalo_ms)
        gasto += intervalo_ms


def seletores_da_folha(caminho: Path) -> list[str]:
    """seletores de uma folha, sem comentario e sem regra @ (o navegador testa cada um contra o DOM)."""
    texto = re.sub(r"/\*[\s\S]*?\*/", "", caminho.read_text(encoding="utf-8"))
    fora = []
    for bloco in re.findall(r"([^{}]+)\{[^{}]*\}", texto):
        bloco = bloco.strip()
        if not bloco or bloco.startswith("@") or bloco.startswith("%"):
            continue
        for parte in bloco.split(","):
            parte = re.sub(r"::?[a-z-]+(\([^)]*\))?", "", parte).strip()
            if parte and not parte.startswith("@") and "{" not in parte:
                fora.append(parte)
    return sorted(set(fora))


JS_SELETORES_QUE_PEGAM = r"""
(lista) => lista.filter((s) => { try { return document.querySelector(s) !== null; } catch { return false; } })
"""


def _telas_da_leva() -> list[dict]:
    leva = int(os.environ.get("PLAT_LEVA", "1"))
    todas = json.loads(MANIFESTO.read_text(encoding="utf-8"))["telas"]
    return [t for t in todas if t["leva"] == leva and t.get("estado") != "deixada_para_tras"]


def _caminho(rota: str) -> str:
    fora = rota
    while "{" in fora:
        i, j = fora.index("{"), fora.index("}")
        fora = fora[:i] + PARAMETRO + fora[j + 1:]
    return fora


@pytest.fixture(scope="module")
def sessao(playwright, base_url):
    cred = credenciais()
    if "demo" not in cred:
        pytest.skip("sem credenciais do inquilino demo (PLAT_CREDENCIAIS_ARQUIVO)")
    navegador = playwright.chromium.launch()
    ctx = navegador.new_context(base_url=base_url, locale="pt-BR", viewport={"width": 1280, "height": 800},
                                color_scheme="dark", ignore_https_errors=True)
    page = ctx.new_page()
    tela = Tela(page, base_url, item=ITEM)
    tela.entrar("demo", *cred["demo"], "/")
    yield tela
    ctx.close()
    navegador.close()


def test_migracao_mede_a_leva(sessao: Tela):
    """uma fase (antes OU depois) da leva: navega cada tela, fotografa nos dois temas, grava a impressao
    digital da arvore e mede contraste e axe. A comparacao das duas fases e do script."""
    fase = os.environ.get("PLAT_FASE", "depois")
    assert fase in ("antes", "depois"), fase
    telas = _telas_da_leva()
    assert telas, "leva vazia: confira PLAT_LEVA e tests/e2e/telas_migracao.json"
    SAIDA.mkdir(parents=True, exist_ok=True)
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page = sessao.page
    sessao.esperar_status(400, 401, 403, 404, 422, 500)  # tela com parametro inexistente: o vazio dela e o alvo
    relatorio: dict[str, dict] = {}
    for t in telas:
        nome, caminho = t["nome"], _caminho(t["rota"])
        registro: dict = {"rota": caminho, "montou": False, "temas": {}}
        for tema in ("escuro", "claro"):
            page.emulate_media(color_scheme="dark" if tema == "escuro" else "light")
            page.evaluate("() => { try { localStorage.removeItem('plat_tema'); } catch {} document.documentElement.removeAttribute('data-theme'); }")
            page.goto(caminho, wait_until="domcontentloaded")
            try:
                page.wait_for_selector("body[data-pronto='1']", timeout=20000)
                registro["montou"] = True
            except Exception:  # noqa: BLE001 - tela que nao chega a pronto ainda vale foto e medida; fica registrado
                page.wait_for_timeout(2000)
            page.wait_for_timeout(250)
            _esperar_assentar(page)
            contraste = page.evaluate(JS_CONTRASTE)
            axe_viol = []
            if apoio_axe.AXE.is_file():
                apoio_axe.injetar(page)
                res = page.evaluate("async () => await axe.run(document, { runOnly: ['color-contrast', 'aria-allowed-attr', 'button-name', 'link-name', 'label'] })")
                axe_viol = [{"regra": v["id"], "impacto": v.get("impact"), "nos": len(v.get("nodes", []))} for v in res.get("violations", [])]
            registro["temas"][tema] = {
                "nos_medidos": contraste["medidos"],
                "violacoes_contraste": contraste["violacoes"],
                "axe": axe_viol,
            }
            if tema == "escuro":
                registro["estrutura"] = page.evaluate(JS_ESTRUTURA)
                if fase == "antes":
                    # o que a folha ANTIGA de fato pega nesta tela, e o que a folha NOVA pegaria no lugar:
                    # e esta a lista que diz se a troca de folha perde regra ou nao.
                    web = Path(__file__).resolve().parents[2] / "web"
                    antiga = seletores_da_folha(web / "style.css")
                    nova = seletores_da_folha(web / "estilo" / "base.css") + seletores_da_folha(web / "estilo" / "componentes.css")
                    pega_antiga = page.evaluate(JS_SELETORES_QUE_PEGAM, antiga)
                    pega_nova = page.evaluate(JS_SELETORES_QUE_PEGAM, sorted(set(nova)))
                    registro["seletores_da_antiga_que_pegam"] = pega_antiga
                    registro["so_na_antiga_e_pegam"] = sorted(set(pega_antiga) - set(pega_nova))
            # Foto da pagina inteira so ate uma altura que o Chromium aguenta. Medido na leva 6: /crs
            # desenha a lista de sistemas de coordenadas com 47.049 elementos e 439.805 px de altura --
            # um bitmap de 1280 x 439.805 nao cabe, e a tentativa nao levanta excecao: derruba o processo
            # do navegador (TargetClosedError na chamada seguinte) e leva a leva inteira junto. Acima do
            # teto fica a foto da area visivel, registrada no relatorio. O que reprova a leva e a arvore,
            # o contraste e o axe; nenhum deles depende da foto.
            caminho_png = CAPTURAS / f"{ITEM}_{nome}_{fase}_{tema}.png"
            altura = page.evaluate("() => document.documentElement.scrollHeight")
            if altura <= ALTURA_MAXIMA_DA_FOTO:
                page.screenshot(path=str(caminho_png), full_page=True)
            else:
                page.screenshot(path=str(caminho_png))
                registro.setdefault("captura_so_da_area_visivel", {})[tema] = altura
        relatorio[nome] = registro
    leva = int(os.environ.get("PLAT_LEVA", "1"))
    (SAIDA / f"leva{leva}_{fase}.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    # nesta fase so reprova o que e erro da propria fase: violacao de contraste introduzida aparece na
    # comparacao das duas fases (o script), porque tela que ja vinha com violacao nao e regressao desta migracao.
    assert relatorio, "nenhuma tela medida"
