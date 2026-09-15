"""Refutação da regressão "schema de dado sem prefixo de instalação" (mesma classe de `CursorSchemaAmbiente`
e da migração `20260911T1440_prefixo_schema_de_dado_nas_funcoes.sql`): todo nome de schema de dado do
inquilino tem de nascer de `app.esquema_dado.esquema()` (Python) ou de `plat.camada_schema_prefixo() || slug`
(SQL) — nunca de `'d_' + slug` escrito à mão, que em produção coincide com o schema prefixado e numa trilha
isolada aponta para o `d_<slug>` de PRODUÇÃO (`permission denied for schema d_demo`, medido 11-15/09/2026 em
`tests/api/ferramentas/apoio.py::criar_camada`).

Este teste varre o CÓDIGO (estático, sem banco): app/**/*.py inteiro e as migrações SQL de carimbo
POSTERIORES a `20260911T1440` (a que já fez a varredura e o conserto genérico; migração anterior a ela,
inclusive as que definem `camada_schema_prefixo()`, são histórico e ficam de fora — não é para reescrever
o passado, é para não deixar voltar)."""

import re
from pathlib import Path

from app.migracoes import chave_migracao, listar

RAIZ = Path(__file__).resolve().parents[2]
DIR_APP = RAIZ / "app"
DIR_MIGRACOES = RAIZ / "db" / "migracoes"

# app/esquema_dado.py é a própria função central: o docstring dela CITA o literal proibido (entre crases,
# como exemplo do que não fazer) de propósito — fica fora da varredura por nome, não por conteúdo.
ARQUIVO_CENTRAL_PY = DIR_APP / "esquema_dado.py"
MARCO = "20260911T1440_prefixo_schema_de_dado_nas_funcoes"

# `f"d_{...}"` / `f'd_{...}'` / `"d_" + ...` / `'d_' + ...`: as quatro formas de montar `d_<slug>` à mão em
# Python fora de app/esquema_dado.py.
RE_PY = re.compile(r'''f"d_\{|f'd_\{|"d_"\s*\+|'d_'\s*\+''')
# `'d_' ||` em SQL: a mesma montagem à mão, do lado do banco (é o padrão que 20260911T1440 varreu e reescreveu).
RE_SQL = re.compile(r"'d_'\s*\|\|")


def _arquivos_py():
    for p in sorted(DIR_APP.rglob("*.py")):
        if p == ARQUIVO_CENTRAL_PY:
            continue
        yield p


def test_nenhum_arquivo_python_monta_d_menos_slug_a_mao():
    achados = []
    for p in _arquivos_py():
        texto = p.read_text(encoding="utf-8")
        for i, linha in enumerate(texto.splitlines(), start=1):
            if RE_PY.search(linha):
                achados.append(f"{p.relative_to(RAIZ)}:{i}: {linha.strip()}")
    assert not achados, (
        "schema de dado montado sem app.esquema_dado.esquema() (só \"d_\" + slug, sem o prefixo de "
        "instalação) em:\n" + "\n".join(achados)
    )


def test_nenhuma_migracao_posterior_ao_marco_concatena_d_menos_slug_a_mao():
    nomes = [n for n in listar(DIR_MIGRACOES) if chave_migracao(n) > chave_migracao(MARCO)]
    assert nomes, "nenhuma migração posterior ao marco encontrada — o filtro de data está errado?"
    achados = []
    for nome in nomes:
        texto = (DIR_MIGRACOES / f"{nome}.sql").read_text(encoding="utf-8")
        for i, linha in enumerate(texto.splitlines(), start=1):
            if RE_SQL.search(linha):
                achados.append(f"{nome}.sql:{i}: {linha.strip()}")
    assert not achados, (
        "migração posterior a 20260911T1440 volta a concatenar 'd_' || slug sem "
        "plat.camada_schema_prefixo() em:\n" + "\n".join(achados)
    )
