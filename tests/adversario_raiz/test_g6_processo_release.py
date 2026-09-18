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

from tests.adversario_raiz.apoio_g6 import RAIZ, rodar

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
    # `make check` e `make homolog` de mentira, mas com a FORMA da saída real: publicar_release.sh exige
    # que o manifesto traga o comando CANÔNICO ("make check", "make homolog") e uma contagem de testes
    # maior que zero, e é isso que impede trocar a linha de teste por `true` via variável de ambiente.
    # Sem estes alvos, nenhuma release sintética consegue ser publicada e o teste de regressão de versão
    # não chega nem a exercitar o piso de versão (medido em 18/09/2026: saída 6, "nenhum teste contado").
    (raiz / "Makefile").write_text(
        "check:\n\t@echo '7 passed in 0.10s'\nhomolog:\n\t@echo '3 passed in 0.10s'\n", encoding="utf-8"
    )
    for cmd in (
        ["git", "init", "-q", "."],
        ["git", "config", "user.email", "adversario@exemplo.invalido"],
        ["git", "config", "user.name", "adversario"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "base"],
    ):
        subprocess.run(cmd, cwd=raiz, check=True, capture_output=True)
    return raiz


def _secao_changelog(raiz: Path, versao: str) -> None:
    """Acrescenta a seção da versão ao CHANGELOG da árvore sintética.

    Desde 18/09/2026 `preparar_release.sh` RECUSA cortar release cuja versão não tenha seção
    `## [X.Y.Z]` no CHANGELOG, e a rede de trás reprova seção órfã de etiqueta — por isso a seção é
    escrita imediatamente antes de cada corte, nunca todas de uma vez."""
    caminho = raiz / "CHANGELOG.md"
    caminho.write_text(
        caminho.read_text(encoding="utf-8")
        + f"\n## [{versao}] - 2026-09-18\n### Adicionado\n- release sintética de teste\n",
        encoding="utf-8",
    )


def test_release_sem_check_e_sem_homolog_precisa_ser_recusada(tmp_path):
    """CONSERTADO em 06/09/2026 (docs/RELEASE.md): o manifesto grava comando/código de saída/testes
    contados/sha do log; publicar_release.sh recusa pacote cujo comando não seja o canônico. Este teste
    era xfail(strict) até 15/09/2026 — a mesma técnica que ele denunciava (afirmar 'passou' sem checar)."""
    raiz = _arvore_sintetica(tmp_path)
    _secao_changelog(raiz, "9.9.9")
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


def test_verificador_de_assinatura_nao_pode_ser_trocado_por_variavel(tmp_path):
    """CONSERTADO em 06/09/2026: PLAT_VERIFICAR_SCRIPT não existe mais; publicar_release.sh sempre chama
    scripts/verificar_pacote.sh ao lado dele, então setar a variável não troca mais nada."""
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


# CONSERTADO (18/09/2026). O piso de versão EXISTE em publicar_release.sh (registro append-only em
# var/releases/publicados.jsonl mais a comparação semver), e a refutação do laudo já não se reproduz. O
# teste continuava vermelho por outro motivo, e o motivo é um conserto ANTERIOR: ele trocava a linha de
# teste por `true` com PLAT_RELEASE_CHECK_CMD, e publicar_release.sh passou a recusar manifesto cujo
# comando não seja o canônico e cuja contagem de testes seja zero — saída 6, "nenhum teste contado". Ou
# seja: a release sintética nunca chegava a ser publicada e o piso de versão jamais era exercitado.
# Agora a árvore sintética tem um `make check`/`make homolog` próprio (ver _arvore_sintetica) que imprime
# a FORMA da saída real, e o teste atravessa o caminho de verdade: publica a 0.2.0, tenta a 0.1.1 e a
# repetição da própria 0.2.0.
def test_publicar_precisa_recusar_regressao_de_versao(tmp_path):
    raiz = _arvore_sintetica(tmp_path)
    amb = {"HOME": str(tmp_path / "casa")}
    for versao in ("0.1.1", "0.2.0"):
        _secao_changelog(raiz, versao)
        cod, _, erro = rodar(["bash", "scripts/preparar_release.sh", versao], cwd=raiz, env=amb)
        assert cod == 0, f"preparar_release {versao} falhou: {erro[-800:]}"
    gerado = Path(amb["HOME"]) / ".config" / "plat" / "chaves" / "release_ed25519_priv.pem"
    assert gerado.exists()
    cod_novo, _, erro = rodar(["bash", "scripts/publicar_release.sh", "var/releases/plat-0.2.0.tar.gz"], cwd=raiz)
    assert cod_novo == 0, f"a release legítima mais nova devia ser aprovada: {erro[-800:]}"
    cod_antigo, saida, _ = rodar(["bash", "scripts/publicar_release.sh", "var/releases/plat-0.1.1.tar.gz"], cwd=raiz)
    assert cod_antigo != 0, f"pacote ANTIGO aprovado depois do novo (regressão de versão): {saida}"
    cod_repetido, saida2, _ = rodar(
        ["bash", "scripts/publicar_release.sh", "var/releases/plat-0.2.0.tar.gz"], cwd=raiz
    )
    assert cod_repetido != 0, f"a MESMA versão foi aprovada duas vezes (repetição de pacote): {saida2}"


def test_etiqueta_de_release_precisa_ser_assinada(tmp_path):
    """CONSERTADO em 06/09/2026: preparar_release.sh roda `git tag -s` com assinatura SSH derivada da
    chave Ed25519 do release; `git tag -v` confere contra var/releases/allowed_signers."""
    raiz = _arvore_sintetica(tmp_path)
    _secao_changelog(raiz, "0.1.1")
    rodar(["bash", "scripts/preparar_release.sh", "0.1.1"], cwd=raiz, env={"HOME": str(tmp_path / "casa")})
    cod, _, erro = rodar(["git", "tag", "-v", "v0.1.1"], cwd=raiz)
    assert cod == 0 and "no signature found" not in erro, f"etiqueta sem assinatura: {erro.strip()}"


# CONSERTADO (18/09/2026): preparar_release.sh confere a seção do CHANGELOG ANTES de `git tag -s`, e a
# rede de trás (conferir_changelog_releases.sh) deixou de ser aviso com saída 0 — reprova e apaga a
# etiqueta recém-criada. Etiqueta assinada é fato público difícil de desfazer; seção de changelog é texto
# que o autor ainda pode escrever, então a ordem certa é conferir primeiro.
def test_etiqueta_sem_secao_no_changelog_precisa_reprovar_a_release(tmp_path):
    raiz = _arvore_sintetica(tmp_path)
    cod, _, _ = rodar(
        ["bash", "scripts/preparar_release.sh", "0.1.1"],
        cwd=raiz,
        env={"HOME": str(tmp_path / "casa")},
    )
    assert cod != 0, "release cortada com etiqueta v0.1.1 sem a seção [0.1.1] em CHANGELOG.md"
    etiquetas = subprocess.run(["git", "tag", "-l"], cwd=raiz, capture_output=True, text=True).stdout.split()
    assert "v0.1.1" not in etiquetas, f"a etiqueta ficou criada mesmo com a release recusada: {etiquetas}"


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
