"""SDK JavaScript (item L7-08-c-sdk-js): corre os testes de unidade em Node (`tests/sdk_js/*.test.mjs`, `fetch`
falso, sem rede) dentro do pytest para entrarem no `make check`, e confere a forma dos 10 exemplos: exatamente 10,
cada um com CSP estrita (`default-src 'none'`) e sem endereço externo (o appliance não tem internet, L7-11-b),
sem script inline, e o módulo servido em /static/sdk/plat.js é o mesmo arquivo publicado em sdk/js/plat.js."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
EXEMPLOS = RAIZ / "web" / "sdk" / "exemplos"
NOMES = [
    "01_login", "02_listar_itens", "03_criar_atualizar_apagar", "04_paginacao", "05_tokens_de_servico", "06_jobs",
    "07_compartilhamento", "08_erros_e_escopo", "09_mapa_extensao", "10_catalogo_no_mapa",
]


def test_unidade_em_node_passa():
    node = shutil.which("node")
    if not node:
        pytest.skip("node ausente nesta máquina")
    r = subprocess.run(
        [node, "--test", "tests/sdk_js/plat.test.mjs"], cwd=RAIZ, capture_output=True, text=True, timeout=120
    )
    resumo = "\n".join(li for li in r.stdout.splitlines() if li.startswith(("# pass", "# fail", "not ok")))
    assert r.returncode == 0, f"{resumo}\n{r.stdout[-3000:]}\n{r.stderr[-1000:]}"
    m = re.search(r"^# pass (\d+)$", r.stdout, re.M)
    assert m and int(m.group(1)) >= 13, resumo


def test_modulo_publicado_e_o_servido():
    publicado = RAIZ / "sdk" / "js" / "plat.js"
    servido = RAIZ / "web" / "sdk" / "plat.js"
    assert servido.is_file() and not servido.is_symlink()
    assert publicado.is_symlink() and publicado.resolve() == servido.resolve()
    texto = servido.read_text(encoding="utf-8")
    for proibido in ("eval(", "new Function(", "innerHTML", "document.write"):
        assert proibido not in texto, proibido
    assert re.search(r"^\s*import\s", texto, re.M) is None, "módulo sem dependência: nenhum import"


def test_exatamente_dez_exemplos_com_csp_e_sem_rede_externa():
    htmls = sorted(p.stem for p in EXEMPLOS.glob("*.html"))
    assert htmls == NOMES, htmls
    for nome in NOMES:
        html = (EXEMPLOS / f"{nome}.html").read_text(encoding="utf-8")
        js = (EXEMPLOS / f"{nome}.js").read_text(encoding="utf-8")
        m = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html)
        assert m and "default-src 'none'" in m.group(1) and "'unsafe-inline'" not in m.group(1), nome
        assert "'unsafe-eval'" not in m.group(1)
        assert re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html) is None, f"{nome}: script inline"
        assert f'src="/static/sdk/exemplos/{nome}.js"' in html
        assert "preparar(" in js and "from './_comum.js'" in js
        for texto in (html, js):
            assert not re.search(r"https?://(?!plat\.exemplo)", texto), f"{nome}: endereço externo"
        assert "innerHTML" not in js and "eval(" not in js
    comum = (EXEMPLOS / "_comum.js").read_text(encoding="utf-8")
    assert "from '/static/sdk/plat.js'" in comum and "securitypolicyviolation" in comum
