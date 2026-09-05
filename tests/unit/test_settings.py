import logging

import pytest

from app.settings import ErroConfiguracao, carregar

BASE = {
    "PLAT_DSN": "postgresql://plat_app:x@127.0.0.1:5432/iagro_sat",
    "PLAT_SECRET": "ab" * 32,
    "PLAT_AMBIENTE": "producao",
    "PLAT_URL_PUBLICA": "https://exemplo.invalido/",
}


@pytest.mark.parametrize("chave", ["PLAT_DSN", "PLAT_SECRET", "PLAT_AMBIENTE", "PLAT_URL_PUBLICA"])
def test_falha_nomeando_chave_ausente(chave):
    valores = {k: v for k, v in BASE.items() if k != chave}
    with pytest.raises(ErroConfiguracao) as erro:
        carregar(valores)
    assert chave in str(erro.value)


def test_segredo_curto_e_recusado():
    with pytest.raises(ErroConfiguracao, match="PLAT_SECRET"):
        carregar({**BASE, "PLAT_SECRET": "abc"})


def test_url_sem_https_e_recusada():
    with pytest.raises(ErroConfiguracao, match="PLAT_URL_PUBLICA"):
        carregar({**BASE, "PLAT_URL_PUBLICA": "http://exemplo.invalido"})


def test_ambiente_desconhecido_e_recusado():
    with pytest.raises(ErroConfiguracao, match="PLAT_AMBIENTE"):
        carregar({**BASE, "PLAT_AMBIENTE": "homolog"})


def test_rebaixa_debug_em_producao(caplog):
    with caplog.at_level(logging.WARNING, logger="plat.settings"):
        s = carregar({**BASE, "PLAT_LOG_NIVEL": "DEBUG"})
    assert s.PLAT_LOG_NIVEL == "INFO"
    assert any("DEBUG" in r.getMessage() for r in caplog.records)


def test_debug_permanece_em_dev():
    s = carregar({**BASE, "PLAT_AMBIENTE": "dev", "PLAT_LOG_NIVEL": "DEBUG"})
    assert s.PLAT_LOG_NIVEL == "DEBUG"
    assert s.producao is False


def test_opcionais_vazias_viram_none_e_url_sem_barra_final():
    s = carregar({**BASE, "PLAT_GARAGE_URL": "", "PLAT_MARTIN_URL": "  "})
    assert s.PLAT_GARAGE_URL is None and s.PLAT_MARTIN_URL is None
    assert s.PLAT_URL_PUBLICA == "https://exemplo.invalido"
    assert s.servicos() == {"martin": None, "titiler": None, "garage": None, "worker": None}
