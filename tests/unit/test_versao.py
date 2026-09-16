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


def test_git_de_worktree_arquivo_apontador_e_lido(monkeypatch, tmp_path):
    """Em worktree, .git é um ARQUIVO ('gitdir: …') e não um diretório; o HEAD vem do gitdir do
    worktree, mas a ref do ramo vive no diretório comum, indicado pelo arquivo 'commondir'."""
    import app.versao as v

    gitdir = tmp_path / "repo" / ".git" / "worktrees" / "wt"
    comum = tmp_path / "repo" / ".git"
    (comum / "refs" / "heads" / "wt").mkdir(parents=True)
    (gitdir / "refs" / "heads").mkdir(parents=True)
    (gitdir / "HEAD").write_text("ref: refs/heads/wt/ramo\n", encoding="ascii")
    (gitdir / "commondir").write_text("../..\n", encoding="ascii")
    (comum / "refs" / "heads" / "wt" / "ramo").write_text(
        "fedcba9876543210fedcba9876543210fedcba98\n", encoding="ascii")
    (tmp_path / ".git").write_text(f"gitdir: {gitdir}\n", encoding="ascii")
    monkeypatch.setattr(v, "ROOT", tmp_path)
    v.git_sha.cache_clear()
    try:
        assert v.git_sha() == "fedcba9876543210fedcba9876543210fedcba98"
    finally:
        v.git_sha.cache_clear()
