"""Item L7-14-instalacoes-apt-desta-linha (ADR 0007 seção 1): `deploy/pacotes_apt.txt` é a lista fechada
que o passo "e2" do `install.sh` instala de forma idempotente; este teste confere que a lista está bem
formada e que cada pacote nela listado está de fato instalado nesta máquina (dpkg -s), sem depender de
rodar `install.sh`/apt de novo (a suíte não tem sudo)."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARQUIVO = ROOT / "deploy" / "pacotes_apt.txt"

ESPERADOS = {
    "python3-uvicorn",
    "python3-psycopg2",
    "python3-venv",
    "python3-cryptography",
    "gdal-bin",
    "python3-gdal",
    "python3-magic",
}


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


def test_install_sh_le_o_arquivo_de_forma_idempotente():
    texto = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "deploy/pacotes_apt.txt" in texto
    assert "apt-get install -y" in texto
    # idempotência: só instala o que dpkg -s não confirmar antes (nunca apt-get em cima do que já está lá)
    trecho = texto[texto.index("== e2. pacotes apt") : texto.index("== f. venv")]
    assert "dpkg -s" in trecho
    assert "FALTAM" in trecho
