"""Endurecimento da cadeia de atualização (itens L7-16-assinatura-pacote e L7-15-processo-release),
escrito em 06/09/2026 em resposta ao ataque adversarial do grupo G6
(`laco/handoffs/T3/ataque-g6-ADVERSARIO.md`, achados 1, 2, 3, 5, 6 e 7).

Os testes do adversário provam que o buraco fechou; estes provam que ele NÃO REABRE pelas bordas que a
suíte dele não cobre:

  1. a lista de confiança do produto nunca fica sem chave (se ficar, a "âncora inicial" volta a permitir
     que quem assina se torne confiável sozinho);
  2. em produção `PLAT_CHAVES_CONFIAVEIS` é ignorada, e o log diz isso;
  3. em ambiente declarado de desenvolvimento ela só ACRESCENTA — as chaves do produto continuam valendo;
  4. `APP_DIR` não troca mais a lista de confiança da verificação;
  5. `publicar_release.sh` recusa versão repetida e regressão de versão, com registro em disco;
  6. os quatro scripts da linha de release não aceitam mais nenhuma variável que substitua uma decisão
     (verificador, script de assinatura).
"""

import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPTS = RAIZ / "scripts"
CONFIAVEIS_PRODUTO = RAIZ / "deploy" / "chaves_publicas_release.txt"
ITEM = "L7-16-assinatura-pacote"


def _chaves_do_arquivo(caminho: Path) -> dict[str, str]:
    chaves = {}
    if not caminho.exists():
        return chaves
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            partes = linha.split()
            if len(partes) >= 2:
                chaves[partes[0]] = partes[1]
    return chaves


def _rodar(argv, *, cwd=None, ambiente=None):
    env = dict(os.environ)
    env.update(ambiente or {})
    return subprocess.run(argv, cwd=str(cwd or RAIZ), env=env, capture_output=True, text=True, timeout=300)


def _pacote_assinado(tmp_path: Path, chave: Path, confiaveis: Path, nome="plat-1.2.3.tar.gz") -> Path:
    alvo = tmp_path / "carga.txt"
    alvo.write_bytes(b"conteudo\n")
    pacote = tmp_path / nome
    with tarfile.open(pacote, "w:gz") as t:
        t.add(alvo, arcname="carga.txt")
    r = _rodar(
        ["bash", str(SCRIPTS / "assinar_pacote.sh"), str(pacote)],
        ambiente={
            "PLAT_CHAVE_PRIVADA": str(chave),
            "PLAT_CHAVES_CONFIAVEIS": str(confiaveis),
            "PLAT_AMBIENTE": "dev",
        },
    )
    assert r.returncode == 0, r.stderr
    return pacote


def test_lista_de_confianca_do_produto_nunca_fica_vazia():
    """A âncora inicial (única situação em que a ferramenta de assinatura ainda escreve na lista) só
    existe para instalação nova. Se o arquivo do repositório voltar a ficar sem chave, qualquer pessoa
    que rode scripts/assinar_pacote.sh volta a se tornar confiável — o achado 1 do adversário."""
    chaves = _chaves_do_arquivo(CONFIAVEIS_PRODUTO)
    assert chaves, (
        f"{CONFIAVEIS_PRODUTO} está sem chave: o caminho de âncora inicial fica aberto em produção"
    )
    for chave_id, publica in chaves.items():
        assert chave_id.startswith("k") and len(chave_id) == 17, chave_id
        assert len(publica) == 44, f"chave {chave_id} não parece Ed25519 em base64"


def test_em_producao_a_variavel_de_ambiente_nao_troca_a_lista(tmp_path):
    """Achado 2: `PLAT_CHAVES_CONFIAVEIS` trocava a lista de confiança inteira. Em produção ela agora é
    ignorada — e o log diz que foi ignorada, para ninguém interpretar a recusa como erro de caminho."""
    chave = tmp_path / "atacante.pem"
    confiaveis_do_atacante = tmp_path / "confiaveis_do_atacante.txt"
    pacote = _pacote_assinado(tmp_path, chave, confiaveis_do_atacante)
    assert _chaves_do_arquivo(confiaveis_do_atacante), "a chave do atacante nem foi criada"

    r = _rodar(
        ["bash", str(SCRIPTS / "verificar_pacote.sh"), str(pacote)],
        ambiente={"PLAT_CHAVES_CONFIAVEIS": str(confiaveis_do_atacante), "PLAT_AMBIENTE": "producao"},
    )
    assert r.returncode == 3, (r.stdout, r.stderr)
    assert "IGNORADA" in r.stderr and "não é confiável" in r.stderr

    # ambiente NÃO declarado vale como produção (o padrão seguro)
    ambiente_sem_declaracao = dict(os.environ)
    ambiente_sem_declaracao.pop("PLAT_AMBIENTE", None)
    ambiente_sem_declaracao["PLAT_CHAVES_CONFIAVEIS"] = str(confiaveis_do_atacante)
    r2 = subprocess.run(
        ["bash", str(SCRIPTS / "verificar_pacote.sh"), str(pacote)],
        cwd=str(RAIZ), env=ambiente_sem_declaracao, capture_output=True, text=True, timeout=120,
    )
    assert r2.returncode == 3, (r2.stdout, r2.stderr)
    assert "IGNORADA" in r2.stderr


def test_em_dev_a_variavel_so_acrescenta(tmp_path):
    """Em ambiente declarado de desenvolvimento a variável ACRESCENTA: as chaves do produto continuam
    valendo (se substituísse, um pacote assinado pela âncora do produto passaria a ser recusado)."""
    chave = tmp_path / "de_teste.pem"
    confiaveis_de_teste = tmp_path / "confiaveis_de_teste.txt"
    pacote = _pacote_assinado(tmp_path, chave, confiaveis_de_teste)
    r = _rodar(
        ["bash", str(SCRIPTS / "verificar_pacote.sh"), str(pacote)],
        ambiente={"PLAT_CHAVES_CONFIAVEIS": str(confiaveis_de_teste), "PLAT_AMBIENTE": "dev"},
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "acrescentando 1 chave" in r.stderr
    assert f"{len(_chaves_do_arquivo(CONFIAVEIS_PRODUTO))} chave(s)" in r.stderr


def test_app_dir_nao_troca_mais_a_lista_de_confianca(tmp_path):
    """Achado 2 (segunda via): apontar APP_DIR para uma árvore do atacante trocava `deploy/` inteiro,
    inclusive a lista de confiança. Hoje a raiz vem do próprio arquivo de script."""
    arvore_falsa = tmp_path / "arvore_falsa"
    (arvore_falsa / "deploy").mkdir(parents=True)
    (arvore_falsa / "venv").symlink_to(RAIZ / "venv")
    (arvore_falsa / "scripts").symlink_to(SCRIPTS)
    chave = tmp_path / "atacante.pem"
    confiaveis_falsos = arvore_falsa / "deploy" / "chaves_publicas_release.txt"
    pacote = _pacote_assinado(tmp_path, chave, confiaveis_falsos)
    r = _rodar(
        ["bash", str(SCRIPTS / "verificar_pacote.sh"), str(pacote)],
        ambiente={"APP_DIR": str(arvore_falsa), "PLAT_AMBIENTE": "producao"},
    )
    assert r.returncode == 3, (r.stdout, r.stderr)


def test_scripts_da_linha_nao_aceitam_mais_variavel_que_substitui_decisao():
    """Achado 6: `PLAT_VERIFICAR_SCRIPT=/bin/true` desligava a verificação de assinatura; havia também
    `PLAT_ASSINAR_SCRIPT`. As duas saíram do código."""
    for nome in ("publicar_release.sh", "preparar_release.sh"):
        texto = (SCRIPTS / nome).read_text(encoding="utf-8")
        for variavel in ("${PLAT_VERIFICAR_SCRIPT", "${PLAT_ASSINAR_SCRIPT"):
            assert variavel not in texto, f"{nome} ainda lê {variavel}"


# ---------------------------------------------------------------------------------------------------
# Registro de publicação: repetição e regressão de versão (achado 7)
# ---------------------------------------------------------------------------------------------------


def _arvore_de_release(tmp_path: Path) -> Path:
    """Árvore git sintética com Makefile que IMPRIME contagem de teste (é o que o manifesto passou a
    exigir). Nunca cria etiqueta na árvore real do produto."""
    raiz = tmp_path / "produto"
    (raiz / "scripts").mkdir(parents=True)
    for nome in (
        "preparar_release.sh", "publicar_release.sh", "conferir_changelog_releases.sh",
        "gerar_changelog_release.py", "assinar_pacote.sh", "verificar_pacote.sh",
        "confiar_chave_release.sh", "plat_assinatura.py",
    ):
        (raiz / "scripts" / nome).write_bytes((SCRIPTS / nome).read_bytes())
    (raiz / "deploy").mkdir()
    (raiz / "deploy" / "chaves_publicas_release.txt").write_text("# vazio\n", encoding="utf-8")
    (raiz / "venv").symlink_to(RAIZ / "venv")
    (raiz / "VERSAO").write_text("0.1.0\n", encoding="utf-8")
    (raiz / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    (raiz / "Makefile").write_text(
        "check:\n\t@echo '11 passed in 1.0s'\n\nhomolog:\n\t@echo '4 passed in 2.0s'\n", encoding="utf-8"
    )
    (raiz / "app").mkdir()
    (raiz / "app" / "conteudo.txt").write_text("produto\n", encoding="utf-8")
    for cmd in (
        ["git", "init", "-q", "."],
        ["git", "config", "user.email", "release@exemplo.invalido"],
        ["git", "config", "user.name", "release"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "base"],
    ):
        subprocess.run(cmd, cwd=raiz, check=True, capture_output=True)
    return raiz


@pytest.mark.parametrize("versao", ["0.1.1", "0.2.0"])
def test_manifesto_registra_o_que_realmente_rodou(tmp_path, versao):
    """Achado 5: o manifesto dizia 'passou' sem olhar nada. Agora carrega comando, código de saída e
    contagem de teste lida da saída real do comando."""
    raiz = _arvore_de_release(tmp_path)
    amb = {"HOME": str(tmp_path / "casa"), "PLAT_AMBIENTE": "dev"}
    r = _rodar(["bash", "scripts/preparar_release.sh", versao], cwd=raiz, ambiente=amb)
    assert r.returncode == 0, (r.stdout, r.stderr)
    with tarfile.open(raiz / "var" / "releases" / f"plat-{versao}.tar.gz") as t:
        m = json.loads(t.extractfile("RELEASE_MANIFEST.json").read())
        versao_no_pacote = t.extractfile("VERSAO").read().decode().strip()
    assert m["formato"] == "plat-release-manifest-2"
    assert m["etapas"]["check"] == {
        **m["etapas"]["check"],
        "comando": "make check",
        "codigo_saida": 0,
        "testes_contados": 11,
        "substituido": False,
    }
    assert m["etapas"]["homolog"]["testes_contados"] == 4
    assert versao_no_pacote == versao, "o pacote viajava com o VERSAO antigo dentro (achado 9)"


def test_publicar_recusa_repeticao_e_regressao_de_versao(tmp_path):
    """Achado 7: um pacote antigo legitimamente assinado era aprovado depois de um novo, e o mesmo
    pacote era aprovado quantas vezes se quisesse — sem registro nenhum do que já tinha entrado."""
    raiz = _arvore_de_release(tmp_path)
    amb = {"HOME": str(tmp_path / "casa"), "PLAT_AMBIENTE": "dev"}
    for versao in ("0.1.1", "0.2.0"):
        assert _rodar(["bash", "scripts/preparar_release.sh", versao], cwd=raiz, ambiente=amb).returncode == 0

    novo = _rodar(["bash", "scripts/publicar_release.sh", "var/releases/plat-0.2.0.tar.gz"], cwd=raiz, ambiente=amb)
    assert novo.returncode == 0, (novo.stdout, novo.stderr)

    antigo = _rodar(["bash", "scripts/publicar_release.sh", "var/releases/plat-0.1.1.tar.gz"], cwd=raiz, ambiente=amb)
    assert antigo.returncode == 7, (antigo.stdout, antigo.stderr)
    assert "não é maior que a última publicada" in antigo.stderr

    repetido = _rodar(["bash", "scripts/publicar_release.sh", "var/releases/plat-0.2.0.tar.gz"], cwd=raiz, ambiente=amb)
    assert repetido.returncode == 7, (repetido.stdout, repetido.stderr)

    registro = [
        json.loads(linha)
        for linha in (raiz / "var" / "releases_publicados.jsonl").read_text(encoding="utf-8").splitlines()
        if linha.strip()
    ]
    assert [r["versao"] for r in registro] == ["0.2.0"], registro


def test_publicar_recusa_manifesto_de_formato_antigo(tmp_path):
    """Um pacote cortado antes deste conserto (manifesto com o texto fixo 'passou') não pode continuar
    valendo: sem evidência, não há prova de que a linha de teste rodou."""
    raiz = _arvore_de_release(tmp_path)
    amb = {"HOME": str(tmp_path / "casa"), "PLAT_AMBIENTE": "dev"}
    assert _rodar(["bash", "scripts/preparar_release.sh", "0.1.1"], cwd=raiz, ambiente=amb).returncode == 0
    pacote = raiz / "var" / "releases" / "plat-0.1.1.tar.gz"

    # reempacota com o manifesto antigo e reassina com a MESMA chave (o atacante do achado 5 tinha a
    # chave: o que ele não tem é como fabricar evidência que o publicador aceite)
    extraido = tmp_path / "extraido"
    extraido.mkdir()
    with tarfile.open(pacote) as t:
        t.extractall(extraido, filter="data")
    (extraido / "RELEASE_MANIFEST.json").write_text(
        json.dumps({"versao": "0.1.1", "commit": "x", "make_check": "passou", "make_homolog": "passou"}),
        encoding="utf-8",
    )
    pacote_antigo = raiz / "var" / "releases" / "plat-0.1.2.tar.gz"
    with tarfile.open(pacote_antigo, "w:gz") as t:
        for item in sorted(extraido.iterdir()):
            t.add(item, arcname=item.name)
    assinar = _rodar(
        ["bash", "scripts/assinar_pacote.sh", str(pacote_antigo)],
        cwd=raiz,
        ambiente={**amb, "PLAT_CHAVE_PRIVADA": str(
            tmp_path / "casa" / ".config" / "plat" / "chaves" / "release_ed25519_priv.pem"
        )},
    )
    assert assinar.returncode == 0, assinar.stderr
    r = _rodar(["bash", "scripts/publicar_release.sh", str(pacote_antigo)], cwd=raiz, ambiente=amb)
    assert r.returncode == 6, (r.stdout, r.stderr)
    assert "formato antigo" in r.stderr
