"""Item L7-19-segredos-e-certificados, cláusula 2 do portão: "`grep -r` do repositório e do journal por
qualquer segredo = 0 ocorrências". Lê os valores REAIS de `/etc/plat/segredos/` (via `sudo cat`, porque o
diretório é 0600 dono root) e varre o repositório (árvore de trabalho + histórico do git) e o journal das
duas unidades atrás desses valores exatos.

Nunca imprime o segredo nem o arquivo onde apareceria — só o NOME do segredo, que já é suficiente para o
operador ir direto ao ponto. Sem acesso a `/etc/plat/segredos/` (sudo indisponível, máquina sem instalação
completa) os testes pulam com o motivo — nunca fingem ter passado."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CRED_DIR = Path("/etc/plat/segredos")
NOMES = ["PLAT_SECRET", "PLAT_SECRET_ANTERIOR", "PLAT_DSN", "PLAT_DSN_WORKER", "PLAT_GARAGE_ADMIN_TOKEN"]
EXCLUDES = ["--exclude-dir=.git", "--exclude-dir=venv", "--exclude-dir=node_modules",
            "--exclude-dir=__pycache__", "--exclude-dir=.pytest_cache", "--exclude-dir=web/vendor"]


def _ler_credential_real(nome: str) -> str | None:
    r = subprocess.run(["sudo", "cat", str(CRED_DIR / nome)], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def _valores_reais() -> dict[str, str]:
    """Só os que existem e não são vazios (PLAT_SECRET_ANTERIOR normalmente é vazio fora de uma janela
    de rotação — settings.py trata isso como ausente, aqui é o mesmo critério)."""
    valores = {}
    for nome in NOMES:
        v = _ler_credential_real(nome)
        if v:
            valores[nome] = v
    return valores


def _pular_se_sem_acesso(valores: dict) -> None:
    if not valores:
        pytest.skip(
            "sem acesso a /etc/plat/segredos/ nesta execução (sudo indisponível ou máquina sem instalação "
            "completa) — a cláusula não foi checada, não foi 'aprovada por padrão'"
        )


def test_nenhum_segredo_real_aparece_na_arvore_de_trabalho_do_repositorio():
    valores = _valores_reais()
    _pular_se_sem_acesso(valores)
    achados = []
    for nome, valor in valores.items():
        r = subprocess.run(["grep", "-rIl", *EXCLUDES, valor, str(ROOT)], capture_output=True, text=True)
        if r.stdout.strip():
            achados.append(nome)
    assert achados == [], f"segredo(s) em claro na árvore de trabalho: {achados}"


def test_nenhum_segredo_real_aparece_no_historico_do_git():
    """`git log -S<string> --all`: acha commit onde a contagem daquela string mudou — a técnica padrão
    para achar segredo versionado em algum ponto do histórico, não só no HEAD atual."""
    valores = _valores_reais()
    _pular_se_sem_acesso(valores)
    if not (ROOT / ".git").exists():
        pytest.skip("sem .git nesta árvore (checkout por tarball)")
    achados = []
    for nome, valor in valores.items():
        r = subprocess.run(
            ["git", "-C", str(ROOT), "log", "--all", "--oneline", f"-S{valor}"],
            capture_output=True, text=True,
        )
        if r.stdout.strip():
            achados.append(nome)
    assert achados == [], f"segredo(s) no histórico do git: {achados}"


def test_nenhum_segredo_real_aparece_no_journal_da_api_e_do_worker():
    valores = _valores_reais()
    _pular_se_sem_acesso(valores)
    achados = []
    for nome, valor in valores.items():
        r = subprocess.run(
            ["sudo", "journalctl", "-u", "plat-api", "-u", "plat-worker", "--no-pager", "-g", valor],
            capture_output=True, text=True,
        )
        if r.returncode not in (0, 1):  # 1 = journalctl -g sem achado (comportamento normal); outro código é erro
            pytest.skip(f"journalctl indisponível para {nome} (código {r.returncode}): {r.stderr[:200]}")
        # achado do desenho deste teste: journalctl SEMPRE escreve algo em stdout, mesmo sem bater nada
        # ("-- No entries --" ou o cabeçalho de boot) — `stdout.strip()` sozinho dava falso positivo nos
        # 4 segredos de uma vez. "achou de verdade" é ter uma linha que NÃO é esse aviso.
        linhas_de_verdade = [
            li for li in r.stdout.splitlines()
            if li.strip() and not li.startswith("-- ") and "No entries" not in li
        ]
        if linhas_de_verdade:
            achados.append(nome)
    assert achados == [], f"segredo(s) no journal: {achados}"


def test_env_exemplo_e_docs_nunca_citam_um_segredo_sintetico_que_pareca_o_de_verdade():
    """Complemento estático: mesmo sem acesso a /etc/plat/segredos/, o repositório nunca deveria ter um
    valor de 64 (PLAT_SECRET) ou 32 (senha de banco) caracteres hexadecimais colado como exemplo — só
    `openssl rand -hex 32` (instrução), nunca o resultado congelado num arquivo comitado."""
    import re

    hex64 = re.compile(r"\b[0-9a-f]{64}\b")
    for nome_arquivo in (".env.exemplo",):
        texto = (ROOT / nome_arquivo).read_text(encoding="utf-8")
        achados = hex64.findall(texto)
        assert achados == [], f"{nome_arquivo} tem uma string de 64 hex colada (parece PLAT_SECRET real): {achados}"
