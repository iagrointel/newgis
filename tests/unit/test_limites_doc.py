"""docs/LIMITES.md é gerado de app/limites.py (item L0-12; ADR 0002 seção 11, ADR 0004 seção 14): o número que
aparece no documento tem de ser o mesmo que o Python leu do módulo agora, nunca um número digitado de novo. Este
teste roda o gerador em memória (`gerar_markdown()`) e compara com o arquivo comitado — se alguém editar
`docs/LIMITES.md` à mão, ou acrescentar uma constante em `app/limites.py` sem rodar `make limites`, o teste
falha. `make check` roda isto antes da suíte pesada (também é o alvo `make limites`, mais rápido, para o CI)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docs"))

import gerar_limites  # noqa: E402 — módulo em docs/, fora do pacote app


def test_limites_md_bate_com_o_codigo_agora():
    gerado = gerar_limites.gerar_markdown()
    comitado = gerar_limites.DESTINO.read_text(encoding="utf-8")
    assert gerado == comitado, "docs/LIMITES.md desatualizado; rode `make limites` e comite o resultado"


def test_toda_constante_do_modulo_aparece_no_documento():
    """Nenhuma constante nova de app/limites.py escapa do documento (o inverso do teste acima: aqui a garantia
    é que o gerador não pulou silenciosamente uma linha que não bateu com a expressão regular)."""
    import app.limites as limites

    esperadas = {
        nome
        for nome in vars(limites)
        if nome.isupper() and not nome.startswith("_") and isinstance(getattr(limites, nome), (int, float, dict))
    }
    encontradas = {nome for _, nomes in gerar_limites._secoes_e_nomes() for nome, _ in nomes}
    faltando = esperadas - encontradas
    assert not faltando, f"constantes de app/limites.py fora de docs/LIMITES.md: {sorted(faltando)}"


def test_corpo_max_padrao_e_upload_documentados_com_o_numero_do_codigo():
    """Caso concreto do item: o limite de corpo (10 MiB padrão, 2 GiB upload) que a middleware realmente aplica
    é exatamente o número que o documento mostra — não uma cópia manual que pode divergir com o tempo."""
    import app.limites as limites

    md = gerar_limites.DESTINO.read_text(encoding="utf-8")
    assert f"`{limites.CORPO_MAX_PADRAO_BYTES!r}`" in md
    assert f"`{limites.CORPO_MAX_UPLOAD_BYTES!r}`" in md
