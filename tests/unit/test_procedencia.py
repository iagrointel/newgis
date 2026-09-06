"""Bloco de procedência — regras que não dependem de banco (item L0-09-a-procedencia).

Cobre as três regras do módulo: vazio vira NULL (nunca string vazia), origem só aceita declarado|medido em
campo conhecido e com valor presente, e a pontuação 0-10 é a mesma fórmula da `acervo.v_completude`
(round(campos / campos_possiveis * 10, 1) sobre os MESMOS 10 campos).
"""

import pytest

from app.catalogo import procedencia
from app.erros import ErroAPI

ITEM = "L0-09-a-procedencia"


def test_texto_vazio_vira_nulo_nunca_string_vazia():
    """Refutação do adversário: preencher 'licença' com texto vazio vira NULL, não string vazia."""
    b = procedencia.normalizar({"licenca": "", "fonte": "   ", "metodo": " ogr2ogr ", "sha256": "ab"})
    assert b["licenca"] is None
    assert b["fonte"] is None
    assert b["metodo"] == "ogr2ogr"  # espaço das pontas some, o valor fica
    assert b["sha256"] == "ab"
    assert procedencia.campos_preenchidos(b) == 2  # metodo e sha256; licenca vazia NÃO conta


def test_limites_lista_vazia_nao_conta_como_campo():
    assert procedencia.campos_preenchidos({"limites": []}) == 0
    assert procedencia.campos_preenchidos({"limites": ["", "  "]}) == 0
    assert procedencia.campos_preenchidos({"limites": ["CRS ausente"]}) == 1


def test_apelido_do_acervo_vira_nome_canonico():
    """Um bloco copiado da ficha de uma fonte do acervo entra sem edição: data_dado/script_gerador/fonte_url."""
    b = procedencia.normalizar({"data_dado": "2024", "script_gerador": "carga.py", "fonte_url": "https://x.gov.br"})
    assert b["data_do_dado"] == "2024"
    assert b["gerador"] == "carga.py"
    assert b["url"] == "https://x.gov.br"
    assert procedencia.campos_preenchidos(b) == 3


def test_pontuacao_usa_os_dez_campos_da_v_completude():
    assert procedencia.CAMPOS_POSSIVEIS == 10
    cheio = {c: "x" for c in procedencia.CAMPOS_PONTUADOS}
    assert procedencia.pontuacao(cheio) == 10.0
    assert procedencia.completude_texto(cheio) == "10,0/10"
    meio = {c: "x" for c in procedencia.CAMPOS_PONTUADOS[:5]}
    assert procedencia.pontuacao(meio) == 5.0
    tres = {c: "x" for c in procedencia.CAMPOS_PONTUADOS[:3]}
    assert procedencia.pontuacao(tres) == 3.0
    assert procedencia.completude_texto(tres) == "3,0/10"


def test_item_sem_bloco_tem_pontuacao_nula_nunca_zero():
    """Ausência de registro não é medida de zero — a mesma escolha da ficha do acervo."""
    assert procedencia.pontuacao(None) is None
    assert procedencia.pontuacao({}) is None
    assert procedencia.resumo({})["pontuacao"] is None
    assert procedencia.resumo({})["campos"] == 0


def test_origem_so_aceita_declarado_ou_medido_em_campo_conhecido():
    b = procedencia.normalizar({"sha256": "ab", "origem": {"sha256": "medido"}})
    assert b["origem"] == {"sha256": "medido"}
    with pytest.raises(ErroAPI) as e:
        procedencia.normalizar({"sha256": "ab", "origem": {"sha256": "chutado"}})
    assert e.value.erro == "procedencia_invalida"
    with pytest.raises(ErroAPI) as e2:
        procedencia.normalizar({"origem": {"campo_que_nao_existe": "medido"}})
    assert e2.value.erro == "procedencia_invalida"


def test_origem_de_campo_vazio_e_descartada():
    """Origem sem valor é procedência inventada: some junto com o campo."""
    b = procedencia.normalizar({"licenca": "", "origem": {"licenca": "declarado"}})
    assert b["licenca"] is None
    assert b["origem"] is None


def test_bloco_nao_objeto_e_422():
    with pytest.raises(ErroAPI) as e:
        procedencia.normalizar("CC BY 4.0")
    assert e.value.status_code == 422 and e.value.erro == "procedencia_invalida"


def test_equivalencia_com_o_vocabulario_do_acervo_esta_documentada():
    """docs/PROCEDENCIA.md cita cada campo canônico e o nome equivalente em acervo.fonte."""
    from pathlib import Path

    doc = Path(__file__).resolve().parents[2] / "docs" / "PROCEDENCIA.md"
    texto = doc.read_text(encoding="utf-8")
    for campo, no_acervo in procedencia.EQUIVALENCIA_ACERVO.items():
        assert f"`{campo}`" in texto, f"campo {campo} sem descrição em docs/PROCEDENCIA.md"
        if no_acervo:
            assert f"`acervo.fonte.{no_acervo}`" in texto, f"equivalência de {campo} ausente em PROCEDENCIA.md"
