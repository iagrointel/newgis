"""`docs/EXPRESSAO.md` TEM de ser a gramática que o código implementa — mesmo padrão de
`docs/gerar_limites.py` (que confere `docs/LIMITES.md` contra `app/limites.py`). Aqui a conferência
é: toda função de `TABELA_FUNCOES` (Python) aparece, com o nome exato, na tabela do documento; toda
função da tabela de `avaliador.js` também; e as duas tabelas (Python/JavaScript) têm o mesmo
vocabulário — uma função que existe só de um lado é exatamente a divergência que este item existe
para impedir (C6 do L2_CONCEITO.md)."""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "EXPRESSAO.md"
RUNNER_JS = ROOT / "tests" / "expressoes" / "executar_js.mjs"

import sys  # noqa: E402

sys.path.insert(0, str(ROOT))
from app.expressao.avaliador_py import TABELA_FUNCOES  # noqa: E402

NOME_FUNCAO_NA_TABELA_MD = re.compile(r"^\| `([A-Za-z]+)\(", re.MULTILINE)


def test_toda_funcao_python_esta_documentada():
    texto_doc = DOC.read_text(encoding="utf-8")
    nomes_doc = set(NOME_FUNCAO_NA_TABELA_MD.findall(texto_doc))
    faltando = set(TABELA_FUNCOES) - nomes_doc
    assert not faltando, f"função implementada mas não documentada em EXPRESSAO.md: {faltando}"


def test_documento_nao_promete_funcao_que_nao_existe():
    texto_doc = DOC.read_text(encoding="utf-8")
    nomes_doc = set(NOME_FUNCAO_NA_TABELA_MD.findall(texto_doc))
    a_mais = nomes_doc - set(TABELA_FUNCOES)
    assert not a_mais, f"função documentada mas não implementada: {a_mais}"


def test_python_e_javascript_documentam_a_mesma_lista_de_funcoes():
    r = subprocess.run(
        ["node", str(RUNNER_JS), "--nomes-funcoes"], capture_output=True, text=True, timeout=15, check=True
    )
    nomes_js = set(json.loads(r.stdout))
    assert nomes_js == set(TABELA_FUNCOES)


def test_portao_ao_menos_15_funcoes_documentadas():
    texto_doc = DOC.read_text(encoding="utf-8")
    nomes_doc = set(NOME_FUNCAO_NA_TABELA_MD.findall(texto_doc))
    assert len(nomes_doc) >= 15


def test_todos_os_codigos_de_erro_do_avaliador_estao_no_catalogo_do_documento():
    import ast
    import inspect

    import app.expressao.avaliador_py as modulo

    codigo_fonte = inspect.getsource(modulo)
    arvore = ast.parse(codigo_fonte)
    codigos_no_codigo = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "ErroExpressao":
            if no.args and isinstance(no.args[0], ast.Constant) and isinstance(no.args[0].value, str):
                codigos_no_codigo.add(no.args[0].value)
    texto_doc = DOC.read_text(encoding="utf-8")
    faltando = {c for c in codigos_no_codigo if f"`{c}`" not in texto_doc}
    assert not faltando, f"código de erro levantado no código mas ausente do catálogo do documento: {faltando}"
