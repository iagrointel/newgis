"""Invariantes do item L2-13-b que não precisam de banco: validade × retenção do rastreio, vocabulário de
política de conflito, nome de tabela no GeoPackage e a montagem do SELECT que o ogr2ogr executa."""

import re

import pytest

from app import limites
from app.replica import modelos, servico


def test_validade_da_replica_e_menor_que_a_retencao_do_rastreio():
    """Se a réplica pudesse viver mais do que o rastreio é retido, a sincronização devolveria um conjunto de
    mudanças INCOMPLETO sem erro nenhum — o pior desfecho possível, porque o campo não teria como perceber."""
    assert limites.REPLICA_VALIDADE_DIAS < limites.REPLICA_RASTREIO_RETENCAO_DIAS


def test_politica_de_conflito_tem_exatamente_tres_casos():
    assert modelos.POLITICAS == ("servidor_vence", "cliente_vence", "pergunta")


@pytest.mark.parametrize(
    "titulo,esperado",
    [("Pontos de Coleta", "pontos_de_coleta"), ("  ", "camada"), ("123 talhões", "c_123_talh_es"),
     ("Área/Uso", "rea_uso")],
)
def test_nome_no_gpkg_sai_no_padrao_da_migracao(titulo, esperado):
    nome = servico._nome_gpkg(titulo, set())
    assert nome == esperado, nome
    assert re.match(r"^[a-z][a-z0-9_]{0,58}$", nome), nome


def test_nome_no_gpkg_nao_repete_no_mesmo_pacote():
    usados: set[str] = set()
    nomes = [servico._nome_gpkg("Talhões", usados) for _ in range(3)]
    assert len(set(nomes)) == 3, nomes


def test_teto_do_lote_de_sincronizacao_bate_com_o_da_edicao():
    """A sincronização escreve pela porta do L2-03-a: um lote maior do que aquela porta aceita seria
    recusado lá dentro, depois de o corpo inteiro ter sido lido."""
    assert limites.REPLICA_SINCRONIZAR_LOTE_MAX <= limites.EDICAO_LOTE_MAX
