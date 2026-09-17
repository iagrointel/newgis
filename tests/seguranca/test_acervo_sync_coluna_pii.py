"""Furo 6 — filtro de coluna de dado pessoal no registro do acervo (achado `L6-01-a`).

ACHADO (adversário de linha L6, turno 9, `laco/handoffs/T9/linha-L6-laudo-adversario.md`):
`scripts/acervo_sync.py::_COLUNA_NEGADA` era um conjunto fixo de 34 nomes comparados por igualdade EXATA
contra o nome INTEIRO da coluna. Grafias correntes de cadastro público brasileiro ficavam de fora e saíam
como EXPOSTAS: `cpf_titular`, `nr_cpf`, `proprietario_nome`, `nome_do_proprietario`.

CONSERTO: a comparação passa a ser por TERMO. O nome da coluna é quebrado em palavras (por separador e na
fronteira letra-dígito, sem acento); termo que é documento ou contato de pessoa (`cpf`, `cnpj`, `rg`,
`telefone`, ...) bloqueia sozinho; `nome`/`nom` bloqueia quando vem junto de um termo de pessoa
(`titular`, `proprietario`, `socio`, ...). Continua sendo rede GROSSA por nome — a fina, por CONTEÚDO, é
o item L6-01-f.

Par de provas:
  ATAQUE   — as quatro variações do laudo (e outras do mesmo formato) saem BLOQUEADAS;
  LEGÍTIMO — coluna de nome geográfico/administrativo (`nom_tema`, `nome_municipio`, `nome_fantasia`) e
             os 29 nomes da lista antiga continuam com o mesmo veredito de antes, ou seja: nada de útil
             deixou de ser exposto e nada que era bloqueado passou a vazar.

Offline: chama só `_colunas_da_tabela`/`_e_pii_por_nome` com um cursor de mentira, sem banco.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


def _acervo_sync():
    """`scripts/acervo_sync.py` roda fora do venv e não é pacote importável: carrega pelo caminho."""
    spec = importlib.util.spec_from_file_location("acervo_sync", RAIZ / "scripts" / "acervo_sync.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class _CursorColunasFalso:
    """Mesmo dublê do teste do adversário (`tests/adversario_raiz/test_advl6_linha_l6_conectores.py`)."""

    def __init__(self, colunas: list[str]) -> None:
        self._colunas = colunas

    def execute(self, *_a, **_k) -> None:
        return None

    def fetchall(self) -> list[dict]:
        return [{"column_name": c} for c in self._colunas]


ATAQUE = [
    "cpf_titular", "nr_cpf", "proprietario_nome", "nome_do_proprietario",
    "num_cpf", "cpf1", "CPF_TITULAR", "cnpj_do_socio", "nome_da_mae",
    "telefone_contato", "e_mail_responsavel", "nome_completo_paciente",
]
LEGITIMO = [
    "ogc_fid", "area_ha", "codigo_ibge", "municipio", "nom_tema", "nom_munic",
    "nome_municipio", "nome_fantasia", "nome_da_unidade_conservacao", "denominacao",
    "data_emissao", "situacao", "sigla_uf", "nome_do_bioma",
]
# os 29 nomes da lista fixa antiga: nenhum pode ter deixado de ser bloqueado
ANTIGOS = [
    "cpf", "cnpj", "nome", "nome_completo", "nome_pessoa", "nome_titular", "nome_proprietario",
    "nome_socio", "nome_responsavel", "nome_paciente", "nome_mae", "nome_pai", "razao_social_pf",
    "email", "e_mail", "telefone", "celular", "fone", "rg", "identidade", "passaporte",
    "pis", "nis", "nit", "cns", "titular_cpf", "titular_nome", "proprietario_cpf", "endereco_residencial",
]


@pytest.fixture(scope="module")
def modulo():
    return _acervo_sync()


@pytest.mark.parametrize("coluna", ATAQUE)
def test_ataque_variacao_de_nome_de_coluna_pii_e_bloqueada(modulo, coluna: str):
    cur = _CursorColunasFalso(["ogc_fid", coluna, "geom"])
    expostas, bloqueadas = modulo._colunas_da_tabela(cur, "public", "tabela_teste", "geom")
    assert coluna in bloqueadas, f"{coluna} saiu exposta"
    assert coluna not in expostas


@pytest.mark.parametrize("coluna", LEGITIMO)
def test_legitimo_coluna_sem_pessoa_continua_exposta(modulo, coluna: str):
    """CONTROLE POSITIVO: a regra nova não pode engolir coluna geográfica/administrativa."""
    cur = _CursorColunasFalso(["ogc_fid", coluna, "geom"])
    expostas, bloqueadas = modulo._colunas_da_tabela(cur, "public", "tabela_teste", "geom")
    assert coluna in expostas, f"{coluna} passou a ser bloqueada sem ser dado pessoal"
    assert coluna not in bloqueadas


@pytest.mark.parametrize("coluna", ANTIGOS)
def test_legitimo_lista_antiga_continua_bloqueada(modulo, coluna: str):
    """CONTROLE POSITIVO (no outro sentido): nada que a lista fixa já pegava pode ter escapado."""
    assert modulo._e_pii_por_nome(coluna)


def test_a_coluna_de_geometria_nunca_entra_em_nenhuma_das_duas_listas(modulo):
    cur = _CursorColunasFalso(["ogc_fid", "geom", "cpf_titular"])
    expostas, bloqueadas = modulo._colunas_da_tabela(cur, "public", "tabela_teste", "geom")
    assert "geom" not in expostas and "geom" not in bloqueadas
