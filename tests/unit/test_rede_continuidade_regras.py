"""Continuidade DEC/FEC (item L4-10): as regras que não dependem de banco.

Cláusulas do portão provadas aqui:

* "'dentro do limite' / 'acima do limite' calculado com o limite do ano" — a função `situacao` e as suas
  quatro saídas, inclusive a diferença entre "sem dado" e um valor zero;
* "⛔ a frase 'transgressão' nunca aparece" — varredura de todo o código, texto e tradução deste item.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.rede_utilidades import continuidade

RAIZ = Path(__file__).resolve().parents[2]

# arquivos que este item escreve; a proibição de vocabulário vale para todos eles
ARQUIVOS_DO_ITEM = [
    "app/rede_utilidades/continuidade.py",
    "app/rede_utilidades/rotas_continuidade.py",
    "app/rede_utilidades/tarefas_continuidade.py",
    "db/migracoes/20260908T1328_rede_continuidade.sql",
    "web/redes_continuidade.html",
    "web/js/rede/continuidade.js",
]


def test_situacao_compara_com_o_limite_do_ano():
    assert continuidade.situacao(29.77, 59.0) == continuidade.DENTRO
    assert continuidade.situacao(61.0, 59.0) == continuidade.ACIMA
    # o limite é teto: igualar não é passar
    assert continuidade.situacao(59.0, 59.0) == continuidade.DENTRO


def test_sem_apurado_e_sem_dado_nunca_zero():
    """Zero seria a MELHOR continuidade possível. Conjunto sem apurado não pode ser lido como zero."""
    assert continuidade.situacao(None, 59.0) == continuidade.SEM_DADO
    assert continuidade.situacao(None, None) == continuidade.SEM_DADO
    # um apurado que É zero continua sendo comparado, e fica dentro do limite
    assert continuidade.situacao(0.0, 59.0) == continuidade.DENTRO


def test_sem_limite_publicado_nao_vira_dentro_do_limite():
    assert continuidade.situacao(29.77, None) == continuidade.SEM_LIMITE


@pytest.mark.parametrize("arquivo", ARQUIVOS_DO_ITEM)
def test_vocabulario_proibido_nao_aparece(arquivo):
    """A palavra de acusação não é usada em nenhum arquivo deste item: quem decide o que é infração e a
    sua consequência é o processo da agência, não esta leitura. O que o produto diz é 'acima do limite
    regulatório', com o número e o limite ao lado."""
    texto = (RAIZ / arquivo).read_text(encoding="utf-8").lower()
    assert "transgress" not in texto, f"{arquivo} usa a palavra proibida pelo item"


def test_traducao_da_tela_nao_usa_a_palavra_proibida():
    import json

    d = json.loads((RAIZ / "web/js/i18n/pt-BR.json").read_text(encoding="utf-8"))
    for chave, valor in d.items():
        if chave.startswith("continuidade."):
            assert "transgress" not in valor.lower(), chave


def test_frases_da_comparacao_sao_exatamente_as_declaradas():
    """O painel e a API mostram este texto e nenhum outro — o teste trava a redação."""
    assert continuidade.DENTRO == "dentro do limite"
    assert continuidade.ACIMA == "acima do limite regulatório"
    assert continuidade.SEM_LIMITE == "sem limite publicado"
    assert continuidade.SEM_DADO == "sem dado"


def test_numero_do_arquivo_de_limites_tem_virgula_decimal():
    assert continuidade._numero_br("8,00") == 8.0
    assert continuidade._numero_br("1.234,50") == 1234.5
    assert continuidade._numero_br("") is None
    assert continuidade._numero_br("n/d") is None


def test_soma_dos_campos_presentes_devolve_nulo_quando_nenhum_existe():
    """A expressão de DIC/FIC soma o que existir; sem nenhum campo o resultado é NULL, não zero."""
    sql = continuidade._soma_presente(("DIC_01", "DIC"))
    assert "unnest" in sql and "WHERE v IS NOT NULL" in sql
    assert "DIC_01" in sql and "'DIC'" in sql


def test_job_de_importacao_esta_registrado():
    from app.jobs.tipos import REGISTRO

    assert "rede.importar_continuidade" in REGISTRO
