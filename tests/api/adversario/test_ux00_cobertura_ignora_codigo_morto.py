"""Adversário L2/UX (linha, parte 3) — item `UX-00-mapa-de-cobertura-da-interface`, do qual TODOS os
`UX-10` .. `UX-23` desta rodada dependem para provar "0 rotas de escrita sem controle" (o portão
literal de cada um deles diz textualmente "docs/COBERTURA_UI.md regenerado sem a lacuna e
docs/cobertura_ui_lacunas.json encolhe" como PROVA da cláusula).

`docs/gerar_cobertura_ui.py::chamadas()` decide se uma rota está "coberta" varrendo `web/**/*.js` por
LITERAIS DE TEXTO que parecem URL da API (`literais()`/`RE_ASPAS`/`RE_APELIDO`), linha a linha — sem
NUNCA remover comentário de linha (`//...`) nem de bloco (`/* ... */`), sem checar se o trecho está
dentro de um `if (false)`/código mundo mesmo inalcançável, e sem confirmar que a chamada está de fato
ligada a um manipulador de evento (`addEventListener`/`onclick`) ou sequer dentro de uma função
chamada por alguém. Um literal de URL dentro de um COMENTÁRIO, ou dentro de uma função nunca invocada,
basta para a rota virar "coberto".

Isso significa que "docs/cobertura_ui_lacunas.json encolheu" (a prova que UX-10..UX-23 citam) pode ser
satisfeita por uma linha morta — comentário, código desativado, `console.log` de depuração — sem
NENHUM controle de verdade na tela. A garantia central da linha inteira ("nenhuma rota de escrita fica
sem controle alcançável") descansa numa heurística de texto que não distingue código executável de
código morto.

Prova mínima (arquivo `.js` sintético num diretório temporário, chamando `chamadas()` direto — não
precisa de servidor, banco nem navegador):

    set -a; source /home/dev/plataforma/laco/var/trilha/uniao.env; set +a
    bash /home/dev/plataforma/laco/roda_teste.sh \
        tests/api/adversario/test_ux00_cobertura_ignora_codigo_morto.py -q -rxX
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "docs"))

import gerar_cobertura_ui as cov  # noqa: E402


@pytest.mark.xfail(
    strict=True,
    reason=(
        "UX-00: docs/gerar_cobertura_ui.py::chamadas() não remove comentário de linha/bloco antes de "
        "procurar literais de URL — uma rota de escrita mencionada só num comentário (código morto, "
        "nunca executado, sem controle nenhum na tela) já basta para o gerador marcar a rota como "
        "'coberto', o que esvazia a prova que UX-10..UX-23 citam ('cobertura_ui_lacunas.json encolhe')"
    ),
)
def test_ux00_url_dentro_de_comentario_nao_deveria_contar_como_coberta(tmp_path):
    arquivo = tmp_path / "modulo_morto.js"
    arquivo.write_text(
        "// TODO: religar este botão um dia\n"
        "// function apagarArquivoMorto(sha) {\n"
        "//   return apagar(`/api/arquivos/${sha}`);\n"
        "// }\n"
        "export const nada = 1;\n"
    )
    achadas = cov.chamadas([arquivo])
    urls = {c["url"] for c in achadas}
    assert "/api/arquivos/{x}" not in urls, (
        "uma URL de escrita mencionada só dentro de um comentário (código morto, nunca executado) foi "
        f"contada como chamada real pelo gerador de cobertura: {achadas}"
    )
