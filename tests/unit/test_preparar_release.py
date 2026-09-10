"""Processo de release (item L7-15-processo-release; docs/RELEASE.md). Roda scripts/preparar_release.sh,
scripts/publicar_release.sh e scripts/conferir_changelog_releases.sh contra uma árvore git SINTÉTICA e
isolada (nunca a árvore real do produto — evita marcar etiqueta na árvore de verdade a cada rodada de teste);
a assinatura usa o script REAL de L7-16 (scripts/assinar_pacote.sh / verificar_pacote.sh) com um par de chaves
e um arquivo de confiança isolados em tmp_path (nunca toca deploy/chaves_publicas_release.txt do repositório).
`make check`/`make homolog` DE VERDADE (contra esta árvore) são o padrão do script; a árvore sintética tem seu
próprio Makefile mínimo, controlado por arquivos-gatilho, para provar a chamada real do comando sem pagar o
custo de minutos + disputa do `.pytest.lock` compartilhado com outras trilhas do laço."""

import json
import subprocess
import tarfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPTS = RAIZ / "scripts"


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env={"HOME": str(repo)}
    )
    assert r.returncode == 0, (args, r.stdout, r.stderr)
    return r.stdout.strip()


def _commit(repo: Path, msg: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", msg, "--allow-empty")


@pytest.fixture
def repo(tmp_path) -> Path:
    """Árvore sintética: git, VERSAO, CHANGELOG.md, Makefile mínimo (check/homolog controláveis por arquivo)."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "VERSAO").write_text("0.1.0\n", encoding="utf-8")
    (r / "CHANGELOG.md").write_text("# Changelog\n\n", encoding="utf-8")
    (r / "app").mkdir()
    (r / "app" / "principal.py").write_text("VERSAO = '0.1.0'\n", encoding="utf-8")
    # o Makefile sintético imprime um resumo no formato do pytest ("N passed"): desde o endurecimento de
    # 06/09/2026 o manifesto registra quantos testes o comando contou, e publicar_release.sh recusa
    # release cujo comando não tenha contado teste nenhum (achado 5 do adversário).
    (r / "Makefile").write_text(
        "check:\n\ttest ! -f .falhar_check\n\ttouch .check_rodou\n\t@echo '7 passed in 0.10s'\n\n"
        "homolog:\n\ttest ! -f .falhar_homolog\n\ttouch .homolog_rodou\n\t@echo '3 passed in 0.20s'\n",
        encoding="utf-8",
    )
    _git(r, "config", "user.email", "t@t.t")
    _git(r, "config", "user.name", "t")
    _commit(r, "estado inicial")
    _git(r, "-c", "user.email=t@t.t", "-c", "user.name=t", "tag", "-a", "v0.1.0", "-m", "release 0.1.0")
    return r


def _rodar_preparar(repo: Path, versao: str, *, hotfix: bool = False, env_extra: dict | None = None):
    env = {
        "APP_DIR": str(repo),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "PLAT_CHAVE_PRIVADA": str(repo / ".chaves" / "priv.pem"),
        "PLAT_CHAVES_CONFIAVEIS": str(repo / ".chaves" / "confiaveis.txt"),
        "PLAT_AMBIENTE": "dev",
        "HOME": str(repo),
    }
    if env_extra:
        env.update(env_extra)
    args = ["bash", str(SCRIPTS / "preparar_release.sh"), versao]
    if hotfix:
        args.append("--hotfix")
    return subprocess.run(args, capture_output=True, text=True, cwd=str(repo), env=env)


def _rodar_publicar(repo: Path, pacote: Path):
    env = {
        "APP_DIR": str(repo),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "PLAT_CHAVES_CONFIAVEIS": str(repo / ".chaves" / "confiaveis.txt"),
        "PLAT_AMBIENTE": "dev",
        "HOME": str(repo),
    }
    return subprocess.run(
        ["bash", str(SCRIPTS / "publicar_release.sh"), str(pacote)],
        capture_output=True, text=True, cwd=str(repo), env=env,
    )


def _manifesto_do_pacote(pacote: Path) -> dict:
    with tarfile.open(pacote) as tf:
        return json.loads(tf.extractfile("RELEASE_MANIFEST.json").read())


def test_versao_fora_do_semver_e_recusada(repo):
    r = _rodar_preparar(repo, "1.2")
    assert r.returncode == 1 and "semver" in (r.stdout + r.stderr)
    assert _git(repo, "tag", "-l") == "v0.1.0"  # nenhuma etiqueta nova


def test_recusa_release_se_make_check_falhar(repo):
    (repo / ".falhar_check").touch()
    r = _rodar_preparar(repo, "0.1.1")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "RELEASE RECUSADA" in r.stderr and "make check" in r.stderr
    assert not (repo / "var" / "releases" / "plat-0.1.1.tar.gz").exists()
    assert not (repo / ".homolog_rodou").exists()  # nem chegou a tentar homolog
    assert _git(repo, "tag", "-l") == "v0.1.0"


def test_recusa_release_se_make_homolog_falhar(repo):
    (repo / ".falhar_homolog").touch()
    r = _rodar_preparar(repo, "0.1.1")
    assert r.returncode == 3, (r.stdout, r.stderr)
    assert "RELEASE RECUSADA" in r.stderr and "make homolog" in r.stderr
    assert (repo / ".check_rodou").exists()  # o check chegou a rodar (e passou)
    assert not (repo / "var" / "releases" / "plat-0.1.1.tar.gz").exists()
    assert _git(repo, "tag", "-l") == "v0.1.0"


def test_release_patch_minor_e_hotfix_sinteticas_com_evidencia(repo):
    # ---- PATCH: 0.1.1 sobre 0.1.0
    _commit(repo, "corrige bug de paginação na listagem de itens")
    r = _rodar_preparar(repo, "0.1.1")
    assert r.returncode == 0, (r.stdout, r.stderr)
    pacote_patch = repo / "var" / "releases" / "plat-0.1.1.tar.gz"
    assert pacote_patch.exists()
    assert Path(str(pacote_patch) + ".sig").exists()
    m = _manifesto_do_pacote(pacote_patch)
    assert m["versao"] == "0.1.1"
    # evidência, não texto fixo: comando canônico, código 0 e testes contados de verdade
    assert m["etapas"]["check"]["comando"] == "make check"
    assert m["etapas"]["check"]["codigo_saida"] == 0
    assert m["etapas"]["check"]["testes_contados"] == 7
    assert m["etapas"]["homolog"]["comando"] == "make homolog"
    assert m["etapas"]["homolog"]["testes_contados"] == 3
    assert _git(repo, "tag", "-l", "v0.1.1") == "v0.1.1"
    changelog_patch = (repo / "var" / "releases" / "0.1.1.changelog.md").read_text(encoding="utf-8")
    assert "## [0.1.1]" in changelog_patch and "### Corrigido" in changelog_patch
    assert "corrige bug de paginação" in changelog_patch

    # ---- MINOR: 0.2.0 (commit "adiciona" cai em Adicionado)
    _commit(repo, "adiciona endpoint de exportação em lote")
    r = _rodar_preparar(repo, "0.2.0")
    assert r.returncode == 0, (r.stdout, r.stderr)
    pacote_minor = repo / "var" / "releases" / "plat-0.2.0.tar.gz"
    assert pacote_minor.exists()
    changelog_minor = (repo / "var" / "releases" / "0.2.0.changelog.md").read_text(encoding="utf-8")
    assert "## [0.2.0]" in changelog_minor and "### Adicionado" in changelog_minor
    assert "endpoint de exportação em lote" in changelog_minor
    assert _git(repo, "tag", "-l", "v0.2.0") == "v0.2.0"

    # ---- HOTFIX: 0.2.1 no ramo hotfix/0.2.1 a partir de v0.2.0
    _git(repo, "checkout", "-q", "-b", "hotfix/0.2.1", "v0.2.0")
    (repo / ".falhar_check").unlink(missing_ok=True)
    (repo / ".falhar_homolog").unlink(missing_ok=True)
    _commit(repo, "corrige vulnerabilidade de escalonamento de privilégio")
    # sem --hotfix, no ramo errado por definição de nome (é hotfix/0.2.1, mas exigimos a flag): sem a flag
    # o script nem checa o ramo — a flag é que ativa a exigência. Confirma a exigência primeiro:
    r_sem_flag_ramo_errado = _rodar_preparar(repo, "9.9.9", hotfix=True)
    assert r_sem_flag_ramo_errado.returncode == 1 and "ramo" in r_sem_flag_ramo_errado.stderr
    r = _rodar_preparar(repo, "0.2.1", hotfix=True)
    assert r.returncode == 0, (r.stdout, r.stderr)
    pacote_hotfix = repo / "var" / "releases" / "plat-0.2.1.tar.gz"
    assert pacote_hotfix.exists()
    changelog_hotfix = (repo / "var" / "releases" / "0.2.1.changelog.md").read_text(encoding="utf-8")
    assert "## [0.2.1]" in changelog_hotfix and "### Segurança" in changelog_hotfix
    assert _git(repo, "tag", "-l", "v0.2.1") == "v0.2.1"

    # as 3 etiquetas + as 3 seções de changelog nascidas nas 3 releases: nenhuma órfã (etiqueta sem changelog
    # já teria disparado o AVISO durante o próprio preparar_release.sh; aqui confere pelo auditor dedicado)
    conferencia = subprocess.run(
        ["bash", str(SCRIPTS / "conferir_changelog_releases.sh")],
        capture_output=True, text=True, cwd=str(repo), env={"APP_DIR": str(repo), "PATH": "/usr/bin:/bin"},
    )
    # o CHANGELOG.md real do repo sintético nunca recebeu as seções coladas (isso é decisão humana, fora do
    # script) — então a auditoria DEVE apontar as 3 etiquetas órfãs, provando que ela realmente audita algo
    assert conferencia.returncode == 1
    assert "v0.1.1" in conferencia.stderr and "v0.2.0" in conferencia.stderr and "v0.2.1" in conferencia.stderr


def test_hotfix_fora_do_ramo_certo_e_recusado(repo):
    r = _rodar_preparar(repo, "0.1.1", hotfix=True)
    assert r.returncode == 1 and "ramo" in r.stderr
    assert not (repo / "var" / "releases" / "plat-0.1.1.tar.gz").exists()


def test_conferir_changelog_detecta_etiqueta_sem_secao_e_secao_sem_etiqueta(repo):
    _git(repo, "-c", "user.email=t@t.t", "-c", "user.name=t", "tag", "-a", "v0.9.0", "-m", "x")
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.9.1] - 2026-01-01\n\n### Alterado\n- x\n", encoding="utf-8"
    )
    r = subprocess.run(
        ["bash", str(SCRIPTS / "conferir_changelog_releases.sh")],
        capture_output=True, text=True, cwd=str(repo), env={"APP_DIR": str(repo), "PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 1
    assert "v0.9.0 sem seção" in r.stderr
    assert "[0.9.1] no CHANGELOG sem etiqueta" in r.stderr


def test_publicar_aceita_pacote_preparado_corretamente(repo):
    _commit(repo, "adiciona teste de release")
    assert _rodar_preparar(repo, "0.1.1").returncode == 0
    pacote = repo / "var" / "releases" / "plat-0.1.1.tar.gz"
    r = _rodar_publicar(repo, pacote)
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "aprovado para produção" in r.stdout


def test_publicar_recusa_pacote_sem_manifesto_mesmo_assinado_de_verdade(repo, tmp_path):
    """Alguém assina um tar qualquer com scripts/assinar_pacote.sh (fora da linha de preparar_release.sh,
    sem nunca ter rodado make check/homolog) — a assinatura é matematicamente válida, mas sem o manifesto
    publicar_release.sh recusa mesmo assim (refutação literal do portão)."""
    pacote = tmp_path / "solto.tar.gz"
    with tarfile.open(pacote, "w:gz") as tf:
        info = tarfile.TarInfo("arquivo_qualquer.txt")
        dados = b"nao passou por homologacao nenhuma"
        info.size = len(dados)
        import io

        tf.addfile(info, io.BytesIO(dados))
    env = {
        # SEM APP_DIR=repo aqui de propósito: assinar_pacote.sh precisa da SUA PRÓPRIA venv (a do repositório
        # real, RAIZ), não da árvore sintética — mesmo cuidado corrigido dentro de preparar_release.sh.
        "APP_DIR": str(RAIZ), "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(repo),
        "PLAT_CHAVE_PRIVADA": str(repo / ".chaves" / "priv.pem"),
        "PLAT_CHAVES_CONFIAVEIS": str(repo / ".chaves" / "confiaveis.txt"),
        "PLAT_AMBIENTE": "dev",
    }
    assinar = subprocess.run(
        ["bash", str(SCRIPTS / "assinar_pacote.sh"), str(pacote)],
        capture_output=True, text=True, cwd=str(repo), env=env,
    )
    assert assinar.returncode == 0, (assinar.stdout, assinar.stderr)

    r = _rodar_publicar(repo, pacote)
    assert r.returncode == 5, (r.stdout, r.stderr)
    assert "não tem RELEASE_MANIFEST.json" in r.stderr


def test_publicar_recusa_pacote_adulterado_depois_de_assinado(repo):
    assert _rodar_preparar(repo, "0.1.1").returncode == 0
    pacote = repo / "var" / "releases" / "plat-0.1.1.tar.gz"
    with pacote.open("r+b") as f:
        f.seek(0)
        primeiro = f.read(1)
        f.seek(0)
        f.write(bytes([primeiro[0] ^ 0xFF]))

    r = _rodar_publicar(repo, pacote)
    assert r.returncode == 4, (r.stdout, r.stderr)
    assert "assinatura não confere" in r.stderr
