"""Item L7-14-instalacoes-apt-desta-linha (ADR 0007 seção 1): `deploy/pacotes_apt.txt` é a lista fechada
que o passo "e2" do `install.sh` instala de forma idempotente; este teste confere que a lista está bem
formada e que cada pacote nela listado está de fato instalado nesta máquina (dpkg -s), sem depender de
rodar `install.sh`/apt de novo (a suíte não tem sudo)."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARQUIVO = ROOT / "deploy" / "pacotes_apt.txt"
INSTALL_SH = ROOT / "install.sh"

ESPERADOS = {
    "python3-uvicorn",
    "python3-psycopg2",
    "python3-venv",
    "python3-cryptography",
    "gdal-bin",
    "python3-gdal",
    "python3-magic",
    "nginx",
    "certbot",
    "python3-certbot-nginx",
    "openssl",
    "curl",
    "postgresql-client-16",
}

# Comando externo (chamado de verdade por install.sh, fora de string/comentário) -> pacote apt que o
# fornece nesta distribuição. Checagem "simples por regex" de propósito (\b<comando>\b no texto inteiro,
# não um parser de shell): um parser completo de shell (aspas, heredoc, `if !`, subshell) foi tentado e
# TRAVOU (regex de aspas com backtracking catastrófico) — o risco de um teste que pendura é pior que o de
# um falso positivo aqui, e falso positivo (pedir pacote a mais) é o lado seguro de errar.
COMANDOS_EXTERNOS = {
    "nginx": "nginx",
    "certbot": "certbot",
    "openssl": "openssl",
    "curl": "curl",
    "psql": "postgresql-client-16",
}

# Chamados por install.sh mas DELIBERADAMENTE fora da lista fechada, com a decisão comentada em
# deploy/pacotes_apt.txt e/ou no próprio install.sh — não é lacuna, então este teste não cobra os dois.
FORA_DE_ESCOPO_DOCUMENTADO = {"docker", "node", "npm"}


def _pacotes() -> list[str]:
    linhas = ARQUIVO.read_text(encoding="utf-8").splitlines()
    return [linha.split()[0] for linha in linhas if linha.strip() and not linha.lstrip().startswith("#")]


def test_arquivo_existe_e_nao_esta_vazio():
    assert ARQUIVO.is_file(), ARQUIVO
    assert _pacotes(), "deploy/pacotes_apt.txt não tem nenhum pacote (só comentários?)"


def test_pacotes_esperados_estao_na_lista():
    pacotes = set(_pacotes())
    faltando = ESPERADOS - pacotes
    assert not faltando, f"pacotes esperados ausentes de deploy/pacotes_apt.txt: {faltando}"


def test_lista_sem_duplicata():
    pacotes = _pacotes()
    assert len(pacotes) == len(set(pacotes)), "pacote repetido em deploy/pacotes_apt.txt"


def test_extensoes_de_banco_ficam_fora_desta_lista():
    # pgRouting/pgstac são donas do item L7-14-extensoes-fdw (ADR próprio, dependente de
    # L7-01-a-compose-perfis); colisão de escopo entre os dois itens é o que este teste evita.
    pacotes = set(_pacotes())
    assert "postgresql-16-pgrouting" not in pacotes
    assert "postgresql-16-pgstac" not in pacotes


def test_cada_pacote_listado_esta_instalado_dpkg():
    pacotes = _pacotes()
    ausentes = []
    for pacote in pacotes:
        r = subprocess.run(["dpkg-query", "-W", "-f=${Status}", pacote], capture_output=True, text=True)
        if r.returncode != 0 or "install ok installed" not in r.stdout:
            ausentes.append(pacote)
    assert not ausentes, f"pacotes listados mas não instalados nesta máquina (rode: sudo bash install.sh …): {ausentes}"


def test_binarios_externos_chamados_por_install_sh_estao_na_lista_ou_documentados_fora():
    """Refutação literal do item (achado do adversário G6): install.sh chama nginx/certbot/openssl/curl/
    psql como comando de verdade, mas a lista se dizia "fechada" sem eles — numa máquina limpa o
    instalador quebrava depois de já ter criado role, segredo e venv. Este teste falha se um binário
    externo conhecido for chamado por install.sh e o pacote que o fornece não estiver nem na lista nem
    marcado como fora de escopo documentado (força quem adicionar um comando novo a classificar, em vez
    de deixar a lista ficar incompleta em silêncio de novo)."""
    texto = INSTALL_SH.read_text(encoding="utf-8")
    pacotes = set(_pacotes())
    faltando = sorted(
        f"{comando} -> {pacote}"
        for comando, pacote in COMANDOS_EXTERNOS.items()
        if re.search(rf"\b{re.escape(comando)}\b", texto) and pacote not in pacotes
    )
    assert not faltando, f"install.sh chama estes comandos sem o pacote correspondente na lista: {faltando}"


def test_fora_de_escopo_documentado_continua_chamado_por_install_sh():
    """Sanidade inversa: se um dia node/npm/docker deixarem de ser chamados por install.sh, o comentário
    de exclusão em deploy/pacotes_apt.txt vira lixo — aponta pra revisar, não deixa apodrecer sozinho."""
    texto = INSTALL_SH.read_text(encoding="utf-8")
    sumidos = [c for c in FORA_DE_ESCOPO_DOCUMENTADO if not re.search(rf"\b{re.escape(c)}\b", texto)]
    assert not sumidos, f"não são mais chamados por install.sh (revisar comentário de exclusão): {sumidos}"


def test_install_sh_le_o_arquivo_de_forma_idempotente():
    texto = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "deploy/pacotes_apt.txt" in texto
    assert "apt-get install -y" in texto
    # idempotência: só instala o que dpkg -s não confirmar antes (nunca apt-get em cima do que já está lá)
    trecho = texto[texto.index("== e2. pacotes apt") : texto.index("== f. venv")]
    assert "dpkg -s" in trecho
    assert "FALTAM" in trecho
