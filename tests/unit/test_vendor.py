"""web/vendor: uma cópia por versão, versão no nome do arquivo, sha256 e licença em VERSOES.txt
(ADR 0001 seção 11.2 regra 3). Regra 3 estendida no item L0-14-identidade-visual (06/09/2026) para
admitir fontes .woff2: versão Major.Minor (fontes não seguem semver de 3 dígitos como as libs JS) e
licença OFL-1.1 (SIL Open Font License, padrão de toda fonte aberta do Google Fonts — ver VERSOES.txt)."""

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "web" / "vendor"
LICENCAS = {"BSD-3-Clause", "MIT", "Apache-2.0", "ISC", "OFL-1.1"}
NOME = re.compile(r"^(?P<nome>[a-z][a-z0-9-]*)-(?P<versao>\d+\.\d+(?:\.\d+)?)\.(js|css|woff2)$")


def _linhas():
    for linha in (VENDOR / "VERSOES.txt").read_text(encoding="utf-8").splitlines():
        if linha and not linha.startswith("#"):
            yield linha.split(maxsplit=4)


def test_todo_arquivo_do_vendor_esta_em_versoes_com_sha_e_licenca():
    declarados = {}
    for nome, versao, sha, licenca, origem in _linhas():
        m = NOME.match(nome)
        assert m and m["versao"] == versao, f"nome fora da convenção <nome>-<versão>.js|css: {nome}"
        assert licenca in LICENCAS, (nome, licenca)
        assert origem.startswith("https://"), (nome, origem)
        declarados[nome] = sha
    arquivos = {p.name for p in VENDOR.iterdir() if p.name != "VERSOES.txt"}
    assert arquivos == set(declarados), arquivos ^ set(declarados)
    for nome, sha in declarados.items():
        assert hashlib.sha256((VENDOR / nome).read_bytes()).hexdigest() == sha, nome


def test_swagger_referenciado_pela_api_existe_no_vendor():
    from app import main

    for rota in (main.SWAGGER_JS, main.SWAGGER_CSS):
        assert rota.startswith("/static/vendor/")
        assert (VENDOR / rota.removeprefix("/static/vendor/")).is_file(), rota
    assert (ROOT / "web" / main.FAVICON.removeprefix("/static/")).is_file()
