import logging

import pytest

import app.settings as settings_mod
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


# item L7-19-segredos-e-certificados: PLAT_SECRET e PLAT_DSN_WORKER saem do .env para o LoadCredential=
# do systemd (docs/SEGURANCA.md). `_credenciais_systemd` é o único ponto que lê $CREDENTIALS_DIRECTORY.


def test_credenciais_systemd_vazio_sem_credentials_directory(monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    assert settings_mod._credenciais_systemd() == {}


def test_credenciais_systemd_le_so_arquivo_que_bate_com_campo_de_settings(tmp_path, monkeypatch):
    (tmp_path / "PLAT_SECRET").write_text("cd" * 32 + "\n")  # \n é aparado (arquivo de credential comum)
    (tmp_path / "nome_que_nao_e_campo").write_text("ignorado")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    assert settings_mod._credenciais_systemd() == {"PLAT_SECRET": "cd" * 32}


def test_valores_do_ambiente_credential_vence_env_mas_perde_para_o_processo(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "PLAT_DSN=postgresql://plat_app:x@127.0.0.1:5432/iagro_sat\n"
        "PLAT_SECRET=" + "11" * 32 + "\n"
        "PLAT_AMBIENTE=producao\n"
        "PLAT_URL_PUBLICA=https://exemplo.invalido\n"
    )
    cred = tmp_path / "cred"
    cred.mkdir()
    (cred / "PLAT_SECRET").write_text("22" * 32)
    monkeypatch.setattr(settings_mod, "ROOT", tmp_path)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(cred))
    monkeypatch.delenv("PLAT_SECRET", raising=False)

    valores = settings_mod.valores_do_ambiente()
    assert valores["PLAT_SECRET"] == "22" * 32  # credential do systemd vence o .env

    monkeypatch.setenv("PLAT_SECRET", "33" * 32)
    valores = settings_mod.valores_do_ambiente()
    assert valores["PLAT_SECRET"] == "33" * 32  # ambiente do processo (suíte/Makefile) vence tudo


def test_sem_credentials_directory_env_continua_mandando_sozinho(tmp_path, monkeypatch):
    """Retrocompatibilidade (P5): instalação sem systemd (dev, teste, CLI) — sem $CREDENTIALS_DIRECTORY
    o comportamento é idêntico ao de antes do L7-19, tudo do .env/ambiente do processo."""
    (tmp_path / ".env").write_text(
        "PLAT_DSN=postgresql://plat_app:x@127.0.0.1:5432/iagro_sat\n"
        "PLAT_SECRET=" + "44" * 32 + "\n"
        "PLAT_AMBIENTE=dev\n"
        "PLAT_URL_PUBLICA=https://exemplo.invalido\n"
    )
    monkeypatch.setattr(settings_mod, "ROOT", tmp_path)
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.delenv("PLAT_SECRET", raising=False)

    valores = settings_mod.valores_do_ambiente()
    assert valores["PLAT_SECRET"] == "44" * 32


# item L7-19-segredos-e-certificados: PLAT_SECRET_ANTERIOR (dupla-chave de rotação, janela de 24h).


def test_sem_plat_secret_anterior_fica_none():
    assert carregar(BASE).PLAT_SECRET_ANTERIOR is None


def test_plat_secret_anterior_formato_invalido_e_recusado():
    with pytest.raises(ErroConfiguracao, match="PLAT_SECRET_ANTERIOR"):
        carregar({**BASE, "PLAT_SECRET_ANTERIOR": "nao-e-hex"})


def test_plat_secret_anterior_valido_e_aceito():
    s = carregar({**BASE, "PLAT_SECRET_ANTERIOR": "cd" * 32})
    assert s.PLAT_SECRET_ANTERIOR == "cd" * 32
    assert s.PLAT_SECRET == "ab" * 32


def test_plat_secret_anterior_igual_ao_atual_vira_none():
    """Rotação que já passou das 24h: o operador esqueceu de apagar o credential ANTERIOR, ou ele nunca
    foi diferente do atual. Tratar como 'sem anterior' em vez de aceitar (o item exige que os dois nomes
    sempre possam coexistir sem um mascarar auditoria do outro)."""
    s = carregar({**BASE, "PLAT_SECRET_ANTERIOR": "ab" * 32})
    assert s.PLAT_SECRET_ANTERIOR is None


def test_plat_secret_anterior_vazio_vira_none():
    s = carregar({**BASE, "PLAT_SECRET_ANTERIOR": ""})
    assert s.PLAT_SECRET_ANTERIOR is None


def test_credenciais_systemd_le_plat_secret_anterior_tambem(tmp_path, monkeypatch):
    (tmp_path / "PLAT_SECRET").write_text("ab" * 32)
    (tmp_path / "PLAT_SECRET_ANTERIOR").write_text("cd" * 32 + "\n")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    valores = settings_mod._credenciais_systemd()
    assert valores["PLAT_SECRET"] == "ab" * 32
    assert valores["PLAT_SECRET_ANTERIOR"] == "cd" * 32
