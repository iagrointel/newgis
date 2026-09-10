"""Conferência ESTRUTURAL da tela /amc/criterios-feicao (item L3-06-criterios-de-feicao).

Por que estrutural e não navegador: o e2e do item (tests/e2e/test_amc_criterios_feicao.py) precisa do nginx
que serve `/static`, e a base de trilha não tem nginx — lá o e2e salta e só corre em homologação/CI. Este
teste garante o que dá para garantir sem navegador: a página existe, está registrada, aponta para o script
certo, e todo identificador que o script procura no documento existe no documento (e o contrário, para não
sobrar caixa vazia na tela).
"""

import re
from pathlib import Path

from app.paginas import PAGINAS, WEB

RAIZ = Path(__file__).resolve().parents[2]
PAGINA = WEB / "amc_criterios_feicao.html"
SCRIPT = WEB / "js" / "amc" / "criterios_feicao_pagina.js"


def test_pagina_registrada_e_no_disco():
    assert PAGINAS["/amc/criterios-feicao"] == "amc_criterios_feicao.html"
    assert PAGINA.is_file() and SCRIPT.is_file()
    assert '/static/js/amc/criterios_feicao_pagina.js' in PAGINA.read_text(encoding="utf-8")


def test_todo_id_procurado_pelo_script_existe_no_documento():
    html = PAGINA.read_text(encoding="utf-8")
    js = SCRIPT.read_text(encoding="utf-8")
    ids_no_html = set(re.findall(r'\bid="([^"]+)"', html))
    procurados = set(re.findall(r"getElementById\('([^']+)'\)", js)) | set(
        re.findall(r"querySelector\('#([A-Za-z0-9_-]+)'\)", js))
    faltando = sorted(procurados - ids_no_html)
    assert faltando == [], f"o script procura elementos que a página não tem: {faltando}"


def test_cada_cartao_da_tela_e_preenchido_pelo_script():
    """Nenhum cartão fica escondido para sempre: todo `hidden` da página é desligado em algum ponto do script."""
    html = PAGINA.read_text(encoding="utf-8")
    js = SCRIPT.read_text(encoding="utf-8")
    escondidos = re.findall(r'id="([^"]+)"[^>]*\shidden', html)
    assert escondidos, "os cartões de resultado nascem escondidos"
    for cartao in escondidos:
        assert f"getElementById('{cartao}').hidden = false" in js, f"{cartao} nunca é mostrado"


def test_a_tela_nao_promete_peso_medido():
    """Regra da casa: os pesos são escolha do usuário, nunca medida nossa."""
    html = PAGINA.read_text(encoding="utf-8")
    assert "escolheu" in html and "não uma medida" in html
