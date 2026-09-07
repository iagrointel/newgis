"""Item L2-02-e-simbolos-sprites-glifos: `docs/LICENCAS_SIMBOLOS.md` tem que existir, ser gerado do
manifesto vivo (nunca escrito à mão) e listar licença para cada ícone/padrão e para cada fonte."""
from pathlib import Path

from app.simbolos import biblioteca
from scripts.gerar_licencas_simbolos import gerar

ROOT = Path(__file__).resolve().parents[2]
DESTINO = ROOT / "docs" / "LICENCAS_SIMBOLOS.md"


def test_arquivo_existe_e_esta_em_dia_com_o_manifesto():
    assert DESTINO.exists(), "rode scripts/gerar_licencas_simbolos.py"
    atual = DESTINO.read_text(encoding="utf-8")
    esperado = gerar()
    assert atual == esperado, "docs/LICENCAS_SIMBOLOS.md está desatualizado; rode o gerador de novo"


def test_todo_icone_do_manifesto_tem_licenca_no_documento():
    texto = DESTINO.read_text(encoding="utf-8")
    for registro in biblioteca.manifesto():
        assert registro["arquivo"] in texto
        assert registro["licenca"] in texto


def test_documento_cita_as_duas_fontes_embutidas():
    texto = DESTINO.read_text(encoding="utf-8")
    assert "noto-sans-regular-2.004.ttf" in texto and "OFL-1.1" in texto
    assert "open-sans-regular-1.10.ttf" in texto and "Apache-2.0" in texto
