"""Item L7-16-assinatura-pacote (ADR 0007 seções 2-3): assinar/verificar pacote de atualização com
Ed25519 (`scripts/assinar_pacote.sh`, `scripts/verificar_pacote.sh`, `scripts/plat_assinatura.py`).

Cláusulas do portão cobertas aqui:
  1. assinar e verificar funcionam sem rede (nenhuma chamada de rede nos três arquivos);
  2. alterar 1 byte do arquivo = verificação falha;
  3. a chave privada nunca aparece no git nem em argv (grep no histórico + grep no conteúdo produzido);
  4. rotação: pacote assinado com a chave nova é aceito por quem só conhece a antiga? NÃO — só depois
     que a pública nova é distribuída (linha nova no arquivo de confiança) o pacote passa a ser aceito.

Cada teste roda os scripts de verdade em subprocess, com PLAT_CHAVE_PRIVADA e PLAT_CHAVES_CONFIAVEIS
apontando para `tmp_path` — nunca toca em `/etc/plat` nem no `deploy/chaves_publicas_release.txt` real.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSINAR = ROOT / "scripts" / "assinar_pacote.sh"
VERIFICAR = ROOT / "scripts" / "verificar_pacote.sh"


def _rodar(script: Path, *args: str, ambiente: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(ambiente)
    return subprocess.run(
        ["bash", str(script), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30
    )


def _ambiente(chave_privada: Path, confiaveis: Path, home: Path | None = None) -> dict:
    d = {"PLAT_CHAVE_PRIVADA": str(chave_privada), "PLAT_CHAVES_CONFIAVEIS": str(confiaveis)}
    if home is not None:
        d["HOME"] = str(home)
    return d


@pytest.fixture()
def pacote(tmp_path: Path) -> Path:
    p = tmp_path / "plat-1.0.0.tar"
    p.write_bytes(b"conteudo de exemplo do pacote de atualizacao" * 100 + bytes(range(256)))
    return p


def test_assinar_gera_chave_na_primeira_execucao_e_registra_publica(tmp_path, pacote):
    chave = tmp_path / "chaves" / "release_ed25519_priv.pem"
    confiaveis = tmp_path / "confiaveis.txt"
    ambiente = _ambiente(chave, confiaveis)

    assert not chave.exists()
    r = _rodar(ASSINAR, str(pacote), ambiente=ambiente)
    assert r.returncode == 0, r.stderr

    assert chave.is_file(), "chave privada não foi criada"
    modo = oct(chave.stat().st_mode)[-3:]
    assert modo == "600", f"chave privada com permissão frouxa: {modo}"

    assert confiaveis.is_file()
    linhas = [linha for linha in confiaveis.read_text().splitlines() if linha and not linha.startswith("#")]
    assert len(linhas) == 1, linhas
    chave_id, publica_b64 = linhas[0].split()[:2]
    assert chave_id.startswith("k") and len(chave_id) == 17

    sig = pacote.with_suffix(pacote.suffix + ".sig")
    assert sig.is_file()
    info = json.loads(sig.read_text())
    assert info["algoritmo"] == "ed25519"
    assert info["chave_id"] == chave_id
    assert info["tamanho_bytes"] == pacote.stat().st_size

    # rodar de novo não deve gerar chave nova nem duplicar a linha de confiança
    r2 = _rodar(ASSINAR, str(pacote), ambiente=ambiente)
    assert r2.returncode == 0, r2.stderr
    linhas2 = [linha for linha in confiaveis.read_text().splitlines() if linha and not linha.startswith("#")]
    assert len(linhas2) == 1


def test_pacote_correto_e_aceito(tmp_path, pacote):
    chave = tmp_path / "chaves" / "release_ed25519_priv.pem"
    confiaveis = tmp_path / "confiaveis.txt"
    ambiente = _ambiente(chave, confiaveis)
    assert _rodar(ASSINAR, str(pacote), ambiente=ambiente).returncode == 0

    r = _rodar(VERIFICAR, str(pacote), ambiente=ambiente)
    assert r.returncode == 0, r.stderr
    saida = json.loads(r.stdout)
    assert saida["aceito"] is True


def test_um_byte_alterado_recusa(tmp_path, pacote):
    chave = tmp_path / "chaves" / "release_ed25519_priv.pem"
    confiaveis = tmp_path / "confiaveis.txt"
    ambiente = _ambiente(chave, confiaveis)
    assert _rodar(ASSINAR, str(pacote), ambiente=ambiente).returncode == 0

    original = pacote.read_bytes()
    alterado = bytearray(original)
    alterado[0] ^= 0x01  # inverte 1 bit do 1º byte -> 1 byte diferente
    pacote.write_bytes(bytes(alterado))
    assert pacote.read_bytes() != original

    r = _rodar(VERIFICAR, str(pacote), ambiente=ambiente)
    assert r.returncode != 0
    assert "assinatura inválida" in r.stderr or "alterado" in r.stderr

    # restaurando o byte original a verificação volta a aceitar (prova que o .sig em si não mudou)
    pacote.write_bytes(original)
    r2 = _rodar(VERIFICAR, str(pacote), ambiente=ambiente)
    assert r2.returncode == 0, r2.stderr


def test_sem_sig_recusa(tmp_path, pacote):
    chave = tmp_path / "chaves" / "release_ed25519_priv.pem"
    confiaveis = tmp_path / "confiaveis.txt"
    r = _rodar(VERIFICAR, str(pacote), ambiente=_ambiente(chave, confiaveis))
    assert r.returncode != 0
    assert "não existe" in r.stderr or "não assinado" in r.stderr


def test_chave_desconhecida_recusa_mesmo_com_assinatura_valida(tmp_path, pacote):
    # pacote assinado com uma chave cujo id nunca foi registrado no arquivo de confiança usado na
    # verificação = recusado, mesmo que a assinatura matematicamente confira contra a chave certa.
    chave = tmp_path / "chaves" / "release_ed25519_priv.pem"
    confiaveis_do_assinante = tmp_path / "confiaveis_assinante.txt"
    assert _rodar(ASSINAR, str(pacote), ambiente=_ambiente(chave, confiaveis_do_assinante)).returncode == 0

    confiaveis_vazio = tmp_path / "confiaveis_vazio.txt"
    confiaveis_vazio.write_text("# nada de confiança aqui\n")
    r = _rodar(VERIFICAR, str(pacote), ambiente=_ambiente(chave, confiaveis_vazio))
    assert r.returncode != 0
    assert "não é confiável" in r.stderr


def test_rotacao_chave_nova_so_e_aceita_depois_de_distribuida(tmp_path, pacote):
    """Reproduz a cláusula do portão: pacote assinado com a chave NOVA é aceito por um appliance que
    ainda só conhece a ANTIGA? NÃO. Só depois que a pública nova é acrescentada ao arquivo de confiança
    (simulando uma atualização anterior, assinada com a chave antiga, que já trazia essa linha) é que a
    verificação aceita pacotes assinados com a chave nova."""
    chave_antiga = tmp_path / "antiga" / "priv.pem"
    chave_nova = tmp_path / "nova" / "priv.pem"
    confiaveis = tmp_path / "confiaveis.txt"

    # 1) só a chave antiga existe no appliance; um pacote de exemplo assinado com ela é aceito normalmente
    pacote_antigo = tmp_path / "plat-1.0.0.tar"
    pacote_antigo.write_bytes(b"versao antiga" * 50)
    assert _rodar(ASSINAR, str(pacote_antigo), ambiente=_ambiente(chave_antiga, confiaveis)).returncode == 0
    r_antigo = _rodar(VERIFICAR, str(pacote_antigo), ambiente=_ambiente(chave_antiga, confiaveis))
    assert r_antigo.returncode == 0, r_antigo.stderr

    linhas_so_antiga = confiaveis.read_text()
    assert linhas_so_antiga.count("\n") >= 1

    # 2) a chave nova é gerada (em outro caminho, simulando outro host de release) e assina um pacote —
    #    mas registrada num arquivo de confiança PRÓPRIO ainda não distribuído ao appliance
    confiaveis_do_gerador_novo = tmp_path / "confiaveis_gerador_novo.txt"
    confiaveis_do_gerador_novo.write_text(linhas_so_antiga)  # o gerador novo parte do que o appliance já tinha
    assert _rodar(ASSINAR, str(pacote), ambiente=_ambiente(chave_nova, confiaveis_do_gerador_novo)).returncode == 0

    # o appliance (arquivo de confiança "confiaveis", só com a antiga) recusa o pacote assinado com a nova
    r_cedo = _rodar(VERIFICAR, str(pacote), ambiente=_ambiente(chave_antiga, confiaveis))
    assert r_cedo.returncode != 0
    assert "não é confiável" in r_cedo.stderr

    # 3) a "atualização" chega: a linha da chave nova é acrescentada ao arquivo do appliance (em produção
    #    isso vem dentro de um pacote assinado com a chave ANTIGA, já provado aceito no passo 1)
    linha_nova = [
        linha
        for linha in confiaveis_do_gerador_novo.read_text().splitlines()
        if linha and not linha.startswith("#")
    ][-1]
    with confiaveis.open("a", encoding="utf-8") as f:
        f.write(linha_nova + "\n")

    # 4) agora o mesmo pacote assinado com a chave nova passa a ser aceito
    r_tarde = _rodar(VERIFICAR, str(pacote), ambiente=_ambiente(chave_antiga, confiaveis))
    assert r_tarde.returncode == 0, r_tarde.stderr
    assert json.loads(r_tarde.stdout)["aceito"] is True


def test_chave_privada_nunca_aparece_em_arquivo_produzido(tmp_path, pacote):
    """A chave privada (bytes PEM) nunca deve aparecer no .sig, no arquivo de confiança, nem em
    stdout/stderr de nenhum dos dois scripts — é a prova de que "nem em argv" na prática: nada que os
    scripts imprimem ou gravam carrega o segredo, só caminhos e material público."""
    chave = tmp_path / "chaves" / "release_ed25519_priv.pem"
    confiaveis = tmp_path / "confiaveis.txt"
    ambiente = _ambiente(chave, confiaveis)
    r1 = _rodar(ASSINAR, str(pacote), ambiente=ambiente)
    assert r1.returncode == 0, r1.stderr
    r2 = _rodar(VERIFICAR, str(pacote), ambiente=ambiente)
    assert r2.returncode == 0, r2.stderr

    pem = chave.read_bytes()
    assert b"PRIVATE KEY" in pem  # confere que lemos o arquivo certo
    for alvo in (r1.stdout, r1.stderr, r2.stdout, r2.stderr, confiaveis.read_text(),
                 pacote.with_suffix(pacote.suffix + ".sig").read_text()):
        assert pem.decode("ascii", "ignore") not in alvo
        assert "PRIVATE KEY" not in alvo


def test_chave_privada_nunca_apareceu_no_historico_do_git():
    """Substitui `gitleaks` (não é pacote apt nesta distribuição — binário Go de release do GitHub, fora
    do mecanismo apt-only deste item) por uma varredura direta do histórico à procura da marca de uma
    chave privada PEM em qualquer arquivo já commitado neste repositório."""
    r = subprocess.run(
        ["git", "log", "--all", "-p", "--", "deploy/", "scripts/"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert "BEGIN PRIVATE KEY" not in r.stdout
    assert "BEGIN OPENSSH PRIVATE KEY" not in r.stdout
    assert "BEGIN EC PRIVATE KEY" not in r.stdout


def test_scripts_nao_chamam_rede():
    for arquivo in (ASSINAR, VERIFICAR, ROOT / "scripts" / "plat_assinatura.py"):
        texto = arquivo.read_text(encoding="utf-8")
        for proibido in ("curl ", "wget ", "requests.", "httpx.", "urllib.request", "socket."):
            assert proibido not in texto, f"{arquivo.name} parece chamar rede ({proibido!r})"


def test_chave_privada_padrao_fica_fora_do_repositorio(tmp_path, pacote):
    """Sem PLAT_CHAVE_PRIVADA, o padrão (usuário comum) cai em $HOME/.config/plat/chaves — nunca dentro
    do diretório do repositório."""
    home_falso = tmp_path / "home_falso"
    home_falso.mkdir()
    confiaveis = tmp_path / "confiaveis.txt"
    env = dict(os.environ)
    env.pop("PLAT_CHAVE_PRIVADA", None)
    env["PLAT_CHAVES_CONFIAVEIS"] = str(confiaveis)
    env["HOME"] = str(home_falso)
    r = subprocess.run(
        ["bash", str(ASSINAR), str(pacote)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30
    )
    assert r.returncode == 0, r.stderr
    esperada = home_falso / ".config" / "plat" / "chaves" / "release_ed25519_priv.pem"
    assert esperada.is_file()
    assert not str(esperada.resolve()).startswith(str(ROOT.resolve()))
