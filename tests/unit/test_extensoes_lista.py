"""Lista única de extensões (item L7-01-d): db/extensoes.txt e os três consumidores que a leem —
install.sh, laco/trilha_ambiente.sh e o ensaio de restauração (app/backup/drill.py). Sem banco: o que
se prova aqui é que a lista tem uma fonte só e que ninguém guarda uma segunda cópia dela."""

import subprocess
from pathlib import Path

import pytest

from app.backup import drill

RAIZ = Path(__file__).resolve().parents[2]
ARQUIVO = RAIZ / "db" / "extensoes.txt"
LEITOR_BASH = RAIZ / "db" / "extensoes.sh"
EXIGIDAS = ("postgis", "pgcrypto", "pg_trgm", "unaccent")


def _lista_pelo_bash(arquivo: Path) -> list[str]:
    r = subprocess.run(["bash", "-c", f'. "{LEITOR_BASH}"; plat_extensoes_lista "{arquivo}"'],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout.split()


def test_o_arquivo_traz_as_quatro_extensoes_que_o_schema_exige():
    assert drill.extensoes_do_ensaio(ARQUIVO) == EXIGIDAS


def test_o_leitor_bash_e_o_leitor_python_leem_a_mesma_lista():
    """Os dois formatos de leitura (grep/awk no bash, split no Python) têm de concordar linha a linha —
    senão o install.sh criaria um conjunto e o ensaio de restauração exigiria outro."""
    assert _lista_pelo_bash(ARQUIVO) == list(drill.extensoes_do_ensaio(ARQUIVO))


def test_comentario_de_fim_de_linha_e_linha_em_branco_nao_viram_extensao(tmp_path):
    arquivo = tmp_path / "extensoes.txt"
    arquivo.write_text("# cabeçalho\n\npostgis   # geometria\n   # continuação recuada\nunaccent\n",
                       encoding="utf-8")
    assert drill.extensoes_do_ensaio(arquivo) == ("postgis", "unaccent")
    assert _lista_pelo_bash(arquivo) == ["postgis", "unaccent"]


def test_nome_invalido_e_lista_vazia_param_com_erro_nomeado(tmp_path):
    """O nome entra num comando SQL; um nome que não seja identificador simples para o leitor, não o banco."""
    ruim = tmp_path / "ruim.txt"
    ruim.write_text('postgis\nunaccent; DROP SCHEMA plat\n', encoding="utf-8")
    with pytest.raises(ValueError, match="nome de extensão inválido"):
        drill.extensoes_do_ensaio(ruim)
    vazio = tmp_path / "vazio.txt"
    vazio.write_text("# só comentário\n", encoding="utf-8")
    with pytest.raises(ValueError, match="lista de extensões vazia"):
        drill.extensoes_do_ensaio(vazio)


@pytest.mark.parametrize("consumidor", ["install.sh", "laco/trilha_ambiente.sh"])
def test_os_consumidores_de_bash_leem_o_arquivo_e_nao_uma_copia(consumidor):
    texto = (RAIZ / consumidor).read_text(encoding="utf-8")
    assert "db/extensoes.txt" in texto
    assert "plat_extensoes_garantir" in texto
    # nenhum CREATE EXTENSION escrito à mão: era assim que a lista se duplicava
    assert "CREATE EXTENSION" not in texto.replace("CREATE EXTENSION IF NOT EXISTS $ext", "")


def test_o_ensaio_de_restauracao_le_o_mesmo_arquivo():
    assert drill.ARQUIVO_EXTENSOES == ARQUIVO
    tarefas = (RAIZ / "app" / "backup" / "tarefas.py").read_text(encoding="utf-8")
    assert "drill.extensoes_do_ensaio()" in tarefas
    # a tupla literal antiga não pode voltar a existir em lugar nenhum do produto
    assert "EXTENSOES_DO_ENSAIO" not in drill.__file__ or not hasattr(drill, "EXTENSOES_DO_ENSAIO")
