"""Varredura estática: TODA conexão psycopg2 do produto que executa SQL com `plat.` escrito na mão tem
de nascer com `cursor_factory=CursorSchemaAmbiente`. Sem isso o módulo inteiro ignora PLAT_SCHEMA e fala
com o `plat` de produção, por mais correto que o reescritor esteja.

Esta é a guarda que faltava: em vez de descobrir um caminho por vez quando um agente tropeça, ela
enumera os caminhos.
"""

import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
DIRS = ("app", "scripts", "docs", "db")
FABRICA = "CursorSchemaAmbiente"


def _conexoes_sem_fabrica() -> list[str]:
    achados = []
    for d in DIRS:
        for arq in sorted((RAIZ / d).rglob("*.py")):
            fonte = arq.read_text(encoding="utf-8")
            if "psycopg2" not in fonte:
                continue
            try:
                arvore = ast.parse(fonte)
            except SyntaxError:  # pragma: no cover
                continue
            usa_plat = "plat." in fonte
            for no in ast.walk(arvore):
                if not isinstance(no, ast.Call):
                    continue
                alvo = ast.unparse(no.func)
                if not alvo.endswith("psycopg2.connect") and alvo != "connect":
                    continue
                fabrica = next((k for k in no.keywords if k.arg == "cursor_factory"), None)
                ok = fabrica is not None and FABRICA in ast.unparse(fabrica.value)
                if not ok and usa_plat:
                    achados.append(f"{arq.relative_to(RAIZ)}:{no.lineno}  cursor_factory="
                                   f"{ast.unparse(fabrica.value) if fabrica else 'ausente'}")
    return achados


@pytest.mark.xfail(strict=True, reason="FURO F9: modulos que escrevem `plat.` na mao e abrem a conexao sem "
                                       "CursorSchemaAmbiente ignoram PLAT_SCHEMA por inteiro. Achados em "
                                       "07/09/2026: scripts/geocodificador_instalar_uf.py:148 (e o "
                                       "copy_expert de plat.geo_endereco na :278), docs/gerar_privilegios.py:38, "
                                       "scripts/acervo_sync.py:134, scripts/acervo_licenca_sync.py:340, "
                                       "app/jobs/eventos.py:46")
def test_toda_conexao_com_sql_plat_usa_o_cursor_do_ambiente():
    achados = _conexoes_sem_fabrica()
    assert not achados, "conexões que falam `plat.` sem o cursor do ambiente:\n  " + "\n  ".join(achados)


if __name__ == "__main__":  # varredura solta, para o laudo
    for linha in _conexoes_sem_fabrica():
        print(linha)
