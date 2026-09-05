"""Leitura estática do install.sh e dos modelos de deploy: segredo nunca em argv (ADR 0001 seção 8),
PYTHONNOUSERSITE=1 na unidade, HSTS em todo add_header do bloco 443 e removido do bloco :80."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALL = (ROOT / "install.sh").read_text(encoding="utf-8")
NGINX = (ROOT / "deploy" / "nginx.conf").read_text(encoding="utf-8")
UNIDADE = (ROOT / "deploy" / "plat-api.service").read_text(encoding="utf-8")


def test_senha_de_demonstracao_entra_por_stdin_nunca_por_argv():
    assert "gerar_hash(sys.stdin.read())" in INSTALL
    assert "gerar_hash(sys.argv" not in INSTALL
    linha = next(li for li in INSTALL.splitlines() if "gerar_hash(sys.stdin.read())" in li)
    assert linha.strip().startswith('HASH=$(printf \'%s\' "$senha" |'), linha
    assert '"$senha")' not in INSTALL


def test_senha_do_banco_vai_ao_psql_por_stdin():
    padrao = r"printf \"ALTER ROLE plat_app PASSWORD '%s';\\n\" \"\$SENHA\" \| \"\$\{PSQL\[@\]\}\" -f -"
    assert re.search(padrao, INSTALL)


def test_python_do_instalador_roda_sem_site_do_usuario():
    assert 'PY=(sudo -u "$APP_USER" env PYTHONNOUSERSITE=1 venv/bin/python)' in INSTALL
    assert 'PIP=(sudo -u "$APP_USER" env PYTHONNOUSERSITE=1 venv/bin/pip)' in INSTALL
    assert "Environment=PYTHONNOUSERSITE=1" in UNIDADE.splitlines()


def test_instalador_grava_plat_git_sha_e_confere_hsts():
    assert 'sed -i "s/^PLAT_GIT_SHA=.*/PLAT_GIT_SHA=$SHA/" .env' in INSTALL
    assert "grep -v 'Strict-Transport-Security'" in INSTALL  # bloco :80 sem HSTS
    assert "grep -q 'max-age=31536000'" in INSTALL  # conferência pública


def test_hsts_em_todo_bloco_de_add_header_do_modelo():
    locais = NGINX.count("location ")
    hsts = NGINX.count('add_header Strict-Transport-Security "max-age=31536000" always;')
    assert locais == 2 and hsts == locais + 1, (locais, hsts)
