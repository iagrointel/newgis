import re

import pytest

from app.versao import git_sha, git_sha_curto, versao

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
HEX = re.compile(r"^[0-9a-f]{7,40}$")


def test_versao_e_semver():
    assert SEMVER.match(versao()), versao()


def test_git_sha_hexadecimal_7_a_40():
    assert HEX.match(git_sha()), git_sha()


def test_git_sha_curto_prefixo_do_completo():
    curto = git_sha_curto()
    assert 7 <= len(curto) <= 12
    assert git_sha().startswith(curto)


def _sem_git(monkeypatch, tmp_path):
    import app.versao as v

    monkeypatch.setattr(v, "ROOT", tmp_path)  # diretório sem .git: instalação por tarball
    v.git_sha.cache_clear()
    return v


def test_sem_git_usa_plat_git_sha_do_ambiente(monkeypatch, tmp_path):
    v = _sem_git(monkeypatch, tmp_path)
    monkeypatch.setenv("PLAT_GIT_SHA", "ABCDEF0123456789")
    assert v.git_sha() == "abcdef0123456789"
    v.git_sha.cache_clear()


def test_sem_git_usa_plat_git_sha_do_env(monkeypatch, tmp_path):
    import app.settings as configuracao

    v = _sem_git(monkeypatch, tmp_path)
    monkeypatch.delenv("PLAT_GIT_SHA", raising=False)
    base = {"PLAT_DSN": "postgresql://x", "PLAT_SECRET": "ab" * 32, "PLAT_AMBIENTE": "dev",
            "PLAT_URL_PUBLICA": "https://exemplo.invalido", "PLAT_GIT_SHA": "0123456789abcdef0123"}
    monkeypatch.setattr(configuracao, "obter", lambda: configuracao.carregar(base))
    assert v.git_sha() == "0123456789abcdef0123"
    v.git_sha.cache_clear()


def test_sem_git_e_sem_plat_git_sha_falha_nomeando(monkeypatch, tmp_path):
    import app.settings as configuracao

    v = _sem_git(monkeypatch, tmp_path)
    monkeypatch.delenv("PLAT_GIT_SHA", raising=False)
    monkeypatch.setattr(configuracao, "obter", lambda: (_ for _ in ()).throw(configuracao.ErroConfiguracao("sem .env")))
    with pytest.raises(RuntimeError, match="PLAT_GIT_SHA"):
        v.git_sha()
    v.git_sha.cache_clear()
