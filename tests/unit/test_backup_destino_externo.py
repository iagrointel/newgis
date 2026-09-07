"""Unidade do destino externo configurável do backup lógico (item L0-06-a, cláusula "cópia para destino
externo configurável"): sem nenhuma das variáveis o destino simplesmente não existe (o backup segue só com
o Garage); com as quatro obrigatórias nasce um cliente S3 apontado ao bucket externo; com um subconjunto a
configuração é RECUSADA nomeando o que falta, em vez de mandar o dump para metade de um endereço."""

import dataclasses

import pytest

from app.backup import destino

CHAVES = {
    "PLAT_BACKUP_EXTERNO_URL": "http://127.0.0.1:3999",
    "PLAT_BACKUP_EXTERNO_BUCKET": "backup-externo",
    "PLAT_BACKUP_EXTERNO_CHAVE": "chave-de-teste",
    "PLAT_BACKUP_EXTERNO_SEGREDO": "segredo-de-teste",
}


def _configurar(monkeypatch, valores: dict) -> None:
    """Settings é dataclass congelada: troca-se o objeto inteiro no módulo (mesmo padrão de
    tests/unit/test_seguranca_rotacao.py), nunca um campo dela."""
    campos = {nome: valores.get(nome)
              for nome in list(CHAVES) + ["PLAT_BACKUP_EXTERNO_REGIAO"]}
    monkeypatch.setattr(destino, "settings", dataclasses.replace(destino.settings, **campos))


def test_sem_variavel_nenhuma_o_destino_externo_nao_existe(monkeypatch):
    _configurar(monkeypatch, {})
    assert destino.cliente_externo() is None


def test_com_as_quatro_obrigatorias_devolve_cliente_e_bucket(monkeypatch):
    _configurar(monkeypatch, CHAVES)
    cliente, bucket = destino.cliente_externo()
    assert bucket == "backup-externo"
    assert cliente.endpoint == CHAVES["PLAT_BACKUP_EXTERNO_URL"]
    assert cliente.regiao == "garage"  # padrão quando PLAT_BACKUP_EXTERNO_REGIAO não é dada


def test_regiao_declarada_e_respeitada(monkeypatch):
    _configurar(monkeypatch, {**CHAVES, "PLAT_BACKUP_EXTERNO_REGIAO": "sa-east-1"})
    cliente, _ = destino.cliente_externo()
    assert cliente.regiao == "sa-east-1"


@pytest.mark.parametrize("ausente", sorted(CHAVES))
def test_configuracao_pela_metade_e_recusada_nomeando_o_que_falta(monkeypatch, ausente):
    _configurar(monkeypatch, {k: v for k, v in CHAVES.items() if k != ausente})
    with pytest.raises(destino.ConfiguracaoAusente) as erro:
        destino.cliente_externo()
    assert ausente in str(erro.value)
