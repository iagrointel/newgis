"""Ataque adversarial ao item L7-15-processo-release (turno 3, grupo G6).

Refutação literal do item: "adversário tenta instalar em produção um pacote que não passou por
homologação (o script tem de recusar) e procura no CHANGELOG uma versão sem etiqueta git ou etiqueta sem
changelog". As duas passam: o pacote é aprovado sem que `make check`/`make homolog` tenham rodado, e o
conferidor de changelog é vazio de conteúdo (0 etiquetas × 0 seções) enquanto o arquivo VERSAO carrega
0.1.0 sem etiqueta nem seção."""

import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from tests.adversario.apoio_g6 import RAIZ, rodar

ITEM = "L7-15-processo-release"


def _arvore_sintetica(tmp_path: Path) -> Path:
    """Cópia mínima do produto num repositório git próprio: nunca cria etiqueta na árvore real."""
    raiz = tmp_path / "produto"
    (raiz / "scripts").mkdir(parents=True)
    for nome in (
        "preparar_release.sh",
        "publicar_release.sh",
        "release.sh",
        "conferir_changelog_releases.sh",
        "gerar_changelog_release.py",
        "assinar_pacote.sh",
        "verificar_pacote.sh",
        "plat_assinatura.py",
    ):
        shutil.copy2(RAIZ / "scripts" / nome, raiz / "scripts" / nome)
    (raiz / "deploy").mkdir()
    (raiz / "deploy" / "chaves_publicas_release.txt").write_text("# vazio\n", encoding="utf-8")
    (raiz / "venv").symlink_to(RAIZ / "venv")
    (raiz / "VERSAO").write_text("0.1.0\n", encoding="utf-8")
    (raiz / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    (raiz / "app").mkdir()
    (raiz / "app" / "conteudo.txt").write_text("produto\n", encoding="utf-8")
    for cmd in (
        ["git", "init", "-q", "."],
        ["git", "config", "user.email", "adversario@exemplo.invalido"],
        ["git", "config", "user.name", "adversario"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "base"],
    ):
        subprocess.run(cmd, cwd=raiz, check=True, capture_output=True)
    return raiz


# CONSERTADO em 06/09/2026 (turno 3, trilha `segur`): este teste era xfail(strict=True) e passou a
# PASSAR. A marca saiu; a asserção do adversário fica intacta. Motivo original registrado por ele:
# @pytest.mark.xfail(
#     strict=True,
#     reason="L7-15 (refutação literal): PLAT_RELEASE_CHECK_CMD/PLAT_RELEASE_HOMOLOG_CMD substituem `make check` "
#     "e `make homolog` por qualquer comando. O RELEASE_MANIFEST.json é escrito com make_check/make_homolog = "
#     "'passou' como texto fixo, sem olhar nada, e publicar_release.sh aprova. O manifesto não prova nada: "
#     "prova só que o próprio script o escreveu.",
# )
def test_release_sem_check_e_sem_homolog_precisa_ser_recusada(tmp_path):
    raiz = _arvore_sintetica(tmp_path)
    cod, saida, erro = rodar(
        ["bash", "scripts/preparar_release.sh", "9.9.9"],
        cwd=raiz,
        env={
            "HOME": str(tmp_path / "casa"),
            "PLAT_RELEASE_CHECK_CMD": "true",
            "PLAT_RELEASE_HOMOLOG_CMD": "true",
        },
    )
    if cod != 0:
        pytest.fail(f"preparar_release não deveria nem chegar a empacotar, mas falhou por outro motivo: {erro}")
    pacote = raiz / "var" / "releases" / "plat-9.9.9.tar.gz"
    with tarfile.open(pacote) as t:
        manifesto = t.extractfile("RELEASE_MANIFEST.json").read().decode()
    cod_pub, saida_pub, _ = rodar(["bash", "scripts/publicar_release.sh", str(pacote)], cwd=raiz)
    assert cod_pub != 0, (
        "pacote aprovado para produção sem ter rodado make check nem make homolog; "
        f"manifesto embutido: {manifesto}; saída: {saida_pub}"
    )


# CONSERTADO em 06/09/2026 (turno 3, trilha `segur`): este teste era xfail(strict=True) e passou a
# PASSAR. A marca saiu; a asserção do adversário fica intacta. Motivo original registrado por ele:
# @pytest.mark.xfail(
#     strict=True,
#     reason="L7-15: PLAT_VERIFICAR_SCRIPT troca o verificador de assinatura por qualquer executável. "
#     "`PLAT_VERIFICAR_SCRIPT=/bin/true` faz publicar_release.sh aprovar um pacote sem assinatura nenhuma.",
# )
def test_verificador_de_assinatura_nao_pode_ser_trocado_por_variavel(tmp_path):
    raiz = _arvore_sintetica(tmp_path)
    rodar(
        ["bash", "scripts/preparar_release.sh", "0.2.0"],
        cwd=raiz,
        env={"HOME": str(tmp_path / "casa"), "PLAT_RELEASE_CHECK_CMD": "true", "PLAT_RELEASE_HOMOLOG_CMD": "true"},
    )
    pacote = raiz / "var" / "releases" / "plat-0.2.0.tar.gz"
    Path(str(pacote) + ".sig").unlink(missing_ok=True)
    falso = tmp_path / "verificador_falso.sh"
    falso.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    falso.chmod(0o755)
    cod, saida, _ = rodar(
        ["bash", "scripts/publicar_release.sh", str(pacote)], cwd=raiz, env={"PLAT_VERIFICAR_SCRIPT": str(falso)}
    )
    assert cod != 0, f"pacote sem assinatura aprovado com verificador trocado por variável: {saida}"


@pytest.mark.xfail(
    strict=True,
    reason="L7-15: publicar_release.sh não guarda registro do que já foi publicado nem exige versão maior "
    "que a instalada. Um pacote antigo, legitimamente assinado, é aprovado depois de um novo (regressão de "
    "versão) e o mesmo pacote é aprovado quantas vezes se quiser (repetição).",
)
def test_publicar_precisa_recusar_regressao_de_versao(tmp_path):
    raiz = _arvore_sintetica(tmp_path)
    amb = {"HOME": str(tmp_path / "casa"), "PLAT_RELEASE_CHECK_CMD": "true", "PLAT_RELEASE_HOMOLOG_CMD": "true"}
    for versao in ("0.1.1", "0.2.0"):
        rodar(["bash", "scripts/preparar_release.sh", versao], cwd=raiz, env=amb)
    confiaveis = raiz / "deploy" / "chaves_publicas_release.txt"
    gerado = Path(amb["HOME"]) / ".config" / "plat" / "chaves" / "release_ed25519_priv.pem"
    assert gerado.exists()
    cod_novo, _, _ = rodar(["bash", "scripts/publicar_release.sh", "var/releases/plat-0.2.0.tar.gz"], cwd=raiz)
    assert cod_novo == 0, f"a chave de release deveria estar em {confiaveis}"
    cod_antigo, saida, _ = rodar(["bash", "scripts/publicar_release.sh", "var/releases/plat-0.1.1.tar.gz"], cwd=raiz)
    assert cod_antigo != 0, f"pacote ANTIGO aprovado depois do novo (regressão de versão): {saida}"


# CONSERTADO em 06/09/2026 (turno 3, trilha `segur`): este teste era xfail(strict=True) e passou a
# PASSAR. A marca saiu; a asserção do adversário fica intacta. Motivo original registrado por ele:
# @pytest.mark.xfail(
#     strict=True,
#     reason="L7-15 (hipótese do item): 'etiqueta git vX.Y.Z assinada'. preparar_release.sh roda `git tag -a` "
#     "(anotada, NÃO assinada); `git tag -v` responde 'no signature found'.",
# )
def test_etiqueta_de_release_precisa_ser_assinada(tmp_path):
    raiz = _arvore_sintetica(tmp_path)
    rodar(
        ["bash", "scripts/preparar_release.sh", "0.1.1"],
        cwd=raiz,
        env={"HOME": str(tmp_path / "casa"), "PLAT_RELEASE_CHECK_CMD": "true", "PLAT_RELEASE_HOMOLOG_CMD": "true"},
    )
    cod, _, erro = rodar(["git", "tag", "-v", "v0.1.1"], cwd=raiz)
    assert cod == 0 and "no signature found" not in erro, f"etiqueta sem assinatura: {erro.strip()}"


@pytest.mark.xfail(
    strict=True,
    reason="L7-15 (portão): a etiqueta é criada ANTES da conferência do changelog, e a divergência sai como "
    "AVISO com saída 0. Uma etiqueta sem seção no CHANGELOG é criada e a release segue.",
)
def test_etiqueta_sem_secao_no_changelog_precisa_reprovar_a_release(tmp_path):
    raiz = _arvore_sintetica(tmp_path)
    cod, _, _ = rodar(
        ["bash", "scripts/preparar_release.sh", "0.1.1"],
        cwd=raiz,
        env={"HOME": str(tmp_path / "casa"), "PLAT_RELEASE_CHECK_CMD": "true", "PLAT_RELEASE_HOMOLOG_CMD": "true"},
    )
    assert cod != 0, "release cortada com etiqueta v0.1.1 sem a seção [0.1.1] em CHANGELOG.md"


@pytest.mark.xfail(
    strict=True,
    reason="L7-15 (portão: 'semver 2.0.0 em VERSAO' e 'CHANGELOG.md tem a seção da versão com "
    "Adicionado/Alterado/Corrigido/Segurança'). Na árvore real: VERSAO=0.1.0, 0 etiquetas git, 0 seções "
    "'## [X.Y.Z]' e 0 rubricas keep-a-changelog. conferir_changelog_releases.sh passa por vacuidade "
    "(0 etiquetas × 0 seções) e nunca olha o arquivo VERSAO.",
)
def test_arvore_real_tem_versao_com_etiqueta_e_secao_de_changelog():
    versao = (RAIZ / "VERSAO").read_text(encoding="utf-8").strip()
    changelog = (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8")
    etiquetas = subprocess.run(
        ["git", "tag", "-l", "v*"], cwd=RAIZ, capture_output=True, text=True
    ).stdout.split()
    assert f"## [{versao}]" in changelog, f"VERSAO={versao} não tem seção no CHANGELOG"
    assert f"v{versao}" in etiquetas, f"VERSAO={versao} não tem etiqueta git"
