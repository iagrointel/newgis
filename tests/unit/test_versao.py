import re

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
