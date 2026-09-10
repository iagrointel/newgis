"""FURO por CAMINHO: nomes que identificam o ambiente mas NÃO viajam como texto de consulta, ou que o
texto do reescritor não alcança. Nenhum destes testes toca o banco: são unidade sobre `reescrever_schema`
e sobre constantes do produto.
"""

import pytest

from app.schema_ambiente import reescrever_schema

TRILHA = "plat_tadversario"


@pytest.mark.xfail(strict=True, reason="FURO F5: a chave do advisory lock viaja como PARAMETRO "
                                       "(app/jobs/worker.py:310 `pg_try_advisory_lock(hashtext(%s))` com "
                                       "LOCK_PESADO='plat.job.pesado', worker.py:47). Parametro nunca entra "
                                       "no texto da consulta, logo o reescritor nao o alcanca por construcao: "
                                       "o lock e do CLUSTER, e producao, homologacao e toda trilha disputam o "
                                       "MESMO 'um job pesado por vez'")
def test_chave_do_advisory_lock_depende_do_ambiente(schema):
    from app.jobs.worker import LOCK_PESADO

    # a chave nao entra no texto da consulta (vai como %s), entao o unico jeito de ela ser por ambiente
    # e o proprio produto monta-la com o schema corrente.
    assert schema in LOCK_PESADO, (
        f"a chave do lock pesado e {LOCK_PESADO!r} em todo ambiente: producao, homologacao e cada "
        f"trilha disputam o mesmo 'um job pesado por vez' do CLUSTER"
    )


@pytest.mark.xfail(strict=True, reason="FURO F6: a regex e `\\bplat\\b`; `_` e caractere de palavra, entao "
                                       "qualquer NOVO objeto global chamado plat_<algo> passa intacto. Ja "
                                       "aconteceu: o schema `plat_acervo` e o papel `plat_acervo_publicador` "
                                       "do L6-01-b exigiram 4 linhas novas a mao em app/schema_ambiente.py "
                                       "(laco/handoffs/T3/L6-01-b-view-so-leitura.md:18) e outra regra em "
                                       "laco/trilha_reescrever.py. O padrao e lista-branca: o que ninguem "
                                       "lembrou de acrescentar vaza para producao em silencio")
def test_schema_irmao_plat_algo_e_reescrito():
    sql = "SELECT 1 FROM plat_acervo.assinatura"
    assert reescrever_schema(sql, TRILHA) != sql, "plat_acervo ficou apontando para o objeto global"


@pytest.mark.xfail(strict=True, reason="FURO F7: a reescrita e cega ao contexto -- troca `plat` tambem dentro "
                                       "de LITERAL de texto. db/migracoes/029_ingestao_vetor.sql:184 e "
                                       "003_identidade_acesso.sql:792 reservam os slugs "
                                       "IN ('plataforma','plat','public',...); em trilha/homologacao a lista "
                                       "vira ('plataforma','plat_t<x>',...), ou seja o ambiente de teste "
                                       "NAO testa a mesma regra que producao aplica")
def test_literal_de_texto_nao_e_reescrito():
    sql = "IF p_slug IN ('plataforma','plat','public') THEN"
    assert "'plat'" in reescrever_schema(sql, TRILHA), "o literal 'plat' foi reescrito junto com o schema"
