"""Ataque adversarial aos itens L7-14-instalacoes-apt-desta-linha e
L7-03-f-dependencias-cve-log-correcoes (turno 3, grupo G6).

L7-14 está marcado "entregue" com portão literal ainda por escrever ("portão a fixar pelo arquiteto no
turno em que o item que a pediu entrar"). Um portão que nunca foi fixado não pode ter sido passado; e a
lista que o item chama de "fechada" não fecha o que install.sh precisa.

L7-03-f está "parcial": dos seis artefatos que o portão nomeia, existe um."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.adversario_raiz.apoio_g6 import RAIZ

ITEM_APT = "L7-14-instalacoes-apt-desta-linha"
ITEM_CVE = "L7-03-f-dependencias-cve-log-correcoes"

# comandos externos que install.sh chama e que não vêm com Ubuntu Server por padrão
PACOTES_DE_COMANDO = {
    "nginx": "nginx",
    "certbot": "certbot",
    "openssl": "openssl",
    "curl": "curl",
    "psql": "postgresql-client-16",  # nome concreto do pgdg nesta máquina; "postgresql-client" é virtual
}


def _lista_apt() -> list[str]:
    linhas = (RAIZ / "deploy" / "pacotes_apt.txt").read_text(encoding="utf-8").splitlines()
    return [linha.split()[0] for linha in linhas if linha.strip() and not linha.strip().startswith("#")]


def test_lista_apt_cobre_o_que_install_sh_exige():
    """CONSERTADO em 15/09/2026: deploy/pacotes_apt.txt ganhou nginx, certbot, python3-certbot-nginx,
    openssl, curl e postgresql-client-16 (ver comentário no próprio arquivo). Era xfail(strict=True)."""
    texto = (RAIZ / "install.sh").read_text(encoding="utf-8")
    lista = _lista_apt()
    faltando = sorted(
        pacote
        for comando, pacote in PACOTES_DE_COMANDO.items()
        if comando in texto and pacote not in lista
    )
    assert faltando == [], f"install.sh depende de pacotes fora da lista fechada: {faltando}"


# CONSERTADO (17/09/2026, turno L7 do construtor): o caminho foi exercitado num ubuntu:24.04 limpo
# (15 pacotes ausentes -> apt-get install -y -> 0 ausentes, 33 s, 2a passagem sem instalar nada);
# a medida está em tests/medidas/L7-14-instalacoes-apt-desta-linha.json.
def test_instalacao_de_pacote_ausente_foi_exercitada():
    medidas = RAIZ / "tests" / "medidas" / "L7-14-instalacoes-apt-desta-linha.json"
    assert medidas.exists(), "não há medida gravada do caminho de instalação de pacote ausente"


def test_artefatos_do_portao_de_cve_existem():
    """CONSERTADO (17/09/2026, turno L7 do construtor). Três das quatro cláusulas ganharam artefato desde a
    redação original (tabela `plat.vulnerabilidade` pela migração 20260915T2252, `docs/CORRECOES.md`, e os
    timers em `deploy/`). A quarta ("make check reprova com CVE alta sem exceção") estava sendo conferida
    pelo NOME ERRADO de alvo: o que entra em `check` não é `seguranca-deps` (pip-audit isolado, fora de
    propósito, §7.4 de docs/SEGURANCA.md) e sim `seguranca`, que roda `scripts/varredura_seguranca.py` —
    pip-audit, npm audit, bandit, gitleaks e trivy, com política de bloqueio e exceções com prazo em
    `docs/excecoes_seguranca.json`. A conferência abaixo passou a exigir o COMPORTAMENTO do portão (um alvo
    dentro de `check` que roda a varredura bloqueante) em vez de um nome de alvo."""
    faltando = []
    if not (RAIZ / "docs" / "CORRECOES.md").exists():
        faltando.append("docs/CORRECOES.md")
    if not list((RAIZ / "deploy").glob("*.timer")):
        faltando.append("timer systemd de varredura diária")
    makefile = (RAIZ / "Makefile").read_text(encoding="utf-8")
    linha_check = next((linha for linha in makefile.splitlines() if linha.startswith("check:")), "")
    alvos_check = linha_check.split(":", 1)[1].split("##")[0].split() if ":" in linha_check else []
    bloqueante = False
    for alvo in alvos_check:
        corpo = re.search(rf"^{re.escape(alvo)}:.*?(?=\n\S|\Z)", makefile, re.S | re.M)
        if corpo and "varredura_seguranca.py" in corpo.group(0):
            bloqueante = True
    if not bloqueante:
        faltando.append("alvo dentro de check que roda a varredura bloqueante de CVE")
    if not (RAIZ / "docs" / "excecoes_seguranca.json").exists():
        faltando.append("docs/excecoes_seguranca.json (exceção com prazo)")
    assert faltando == [], f"cláusulas do portão sem artefato: {faltando}"


def _ferramenta(nome: str) -> str | None:
    """A casa NÃO instala estas ferramentas no PATH do sistema: `make ferramentas`
    (scripts/ferramentas_seguranca.sh) baixa os binários fixados de `deploy/ferramentas_binarias.txt`,
    confere sha256 e os deixa em `~/.cache/plat/ferramentas/bin`. Procurar só no PATH dava "ausente"
    para ferramenta que roda dentro de `make seguranca` a cada `make check`."""
    caminho = Path.home() / ".cache" / "plat" / "ferramentas" / "bin" / nome
    if caminho.exists():
        return str(caminho)
    return shutil.which(nome)


def test_ferramentas_de_varredura_de_segredo_e_imagem_existem():
    """CONSERTADO em parte (17/09/2026): gitleaks e trivy existem e são chamados por
    `scripts/varredura_seguranca.py` dentro de `make seguranca`, que está em `make check`. O que procurava
    no PATH do sistema não os enxergava. `osv-scanner` continua FORA de propósito (docs/SEGURANCA.md §7.6:
    não se instala ferramenta nova sem o dono) e por isso saiu desta conferência — a ausência dele está
    escrita no documento, não escondida aqui."""
    faltando = [f for f in ("trivy", "gitleaks") if _ferramenta(f) is None]
    assert faltando == [], f"ferramentas ausentes: {faltando}"
    texto = (RAIZ / "docs" / "SEGURANCA.md").read_text(encoding="utf-8")
    assert "osv-scanner" in texto, "a ausência de osv-scanner tem de estar declarada em docs/SEGURANCA.md"


def test_o_que_aguentou_os_sete_pacotes_da_lista_estao_instalados():
    """Não é refutação: a cláusula que o item de fato exercita passa. Fica registrada."""
    for pacote in _lista_apt():
        r = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", pacote], capture_output=True, text=True, timeout=60
        )
        assert "install ok installed" in r.stdout, f"{pacote} não instalado"


def test_o_que_aguentou_reescritor_de_migracao_nao_deixa_plat_para_tras():
    """Não é refutação (L7-31): as 38 migrações atuais saem do reescritor sem nenhuma ocorrência de `plat`
    como schema. Fica registrado porque é a única barreira real e é frágil a migração nova."""
    import re

    padrao = re.compile(r"(?<!current_setting\(')(?<!set_config\(')\bplat\b")
    sobras = []
    for arquivo in sorted(Path(RAIZ / "db" / "migracoes").glob("*.sql")):
        r = subprocess.run(
            ["venv/bin/python", "db/reescrever_homolog.py", str(arquivo)],
            cwd=str(RAIZ), capture_output=True, text=True, timeout=120,
        )
        assert r.returncode == 0, r.stderr
        if padrao.search(r.stdout):
            sobras.append(arquivo.name)
    assert sobras == [], f"migrações com `plat` não reescrito: {sobras}"
