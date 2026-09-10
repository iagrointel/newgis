"""FURO no CAMINHO de fora do Python: quem aplica as migrações da trilha é um script de shell. Ele decide
sozinho de onde vêm as migrações, e a decisão silenciosa é a causa raiz das falhas 1 e 3 de 06-07/09/2026.
"""

from pathlib import Path

import pytest

SCRIPT = Path("/home/dev/plataforma/laco/trilha_ambiente.sh")
REESCREVER = Path("/home/dev/plataforma/laco/trilha_reescrever.py")


@pytest.mark.xfail(strict=True, reason="FURO F10: trilha_ambiente.sh acha a fonte das migracoes pelo NOME "
                                       "da trilha (`/home/dev/plataforma/wt/$T`) e, se nao achar, cai em "
                                       "`FONTE=$REPO` -- a arvore de PRODUCAO -- sem avisar. Medido em "
                                       "07/09/2026: wt/amcmodelo esta no ramo wt/tiles, wt/compart em "
                                       "wt/conteudo e wt/edicao em wt/upload; nesses tres a pasta nao tem o "
                                       "nome do ramo, entao `trilha_ambiente.sh tiles` aplica as migracoes "
                                       "de master e a trilha testa outro codigo do que o worktree tem. A "
                                       "mensagem do proprio db/migrar.sh ensina a chamada SEM o 2o argumento")
def test_trilha_ambiente_nao_cai_calado_na_arvore_de_producao():
    texto = SCRIPT.read_text(encoding="utf-8")
    assert '[ -z "$FONTE" ] && FONTE="$REPO"' not in texto, (
        "trilha_ambiente.sh volta para a arvore principal em silencio quando nao acha o worktree"
    )


def test_reescritor_da_trilha_le_a_regra_do_worktree():
    """COBERTO (falha 2 de 06/09, conferida): trilha_reescrever.py sobe do arquivo da migracao ate achar
    `app/schema_ambiente.py`, entao uma regra nova que so exista no ramo passa a valer na trilha."""
    texto = REESCREVER.read_text(encoding="utf-8")
    assert "_raiz_do_arquivo" in texto and "schema_ambiente.py" in texto


@pytest.mark.xfail(strict=True, reason="FURO F11: a copia versionada laco/trilha_reescrever.py do "
                                       "repositorio esta ATRASADA em relacao a /home/dev/plataforma/laco, "
                                       "que e a que o driver roda: falta o _raiz_do_arquivo (conserto da "
                                       "falha 2 de 06/09). Quem le o repositorio le a regra velha, e um "
                                       "`git checkout` da copia do repo desfaz o conserto sem aviso")
def test_copia_do_laco_no_repositorio_nao_diverge_da_viva():
    """A copia versionada `laco/trilha_reescrever.py` do repositorio esta ATRASADA em relacao a
    /home/dev/plataforma/laco (a que o driver roda). Quem ler o repositorio le a regra velha."""
    repo = Path(__file__).resolve().parents[3] / "laco" / "trilha_reescrever.py"
    if not repo.exists():
        pytest.skip("sem copia no repositorio")
    assert repo.read_text(encoding="utf-8") == REESCREVER.read_text(encoding="utf-8"), (
        "a copia versionada do reescritor de trilha diverge da que roda de verdade"
    )


@pytest.mark.xfail(strict=True, reason="FURO F12: sao DUAS listas-brancas de nome global, e so uma foi "
                                       "atualizada. laco/trilha_reescrever.py ganhou `_PAPEL_LEITOR` em "
                                       "06/09 (achado F2 do adversario anterior, commit c4f6e4b), mas "
                                       "db/reescrever_homolog.py nao: homologacao aplica GRANT no papel "
                                       "GLOBAL `plat_leitor`, o mesmo de producao. E o mesmo furo, no outro "
                                       "arquivo -- a prova de que lista-branca duplicada nao se mantem")
def test_reescritor_de_homologacao_cobre_os_mesmos_nomes_da_trilha():
    from db.reescrever_homolog import reescrever_homolog

    sql = "GRANT SELECT ON plat.tenant TO plat_leitor;"
    assert "plat_leitor" not in reescrever_homolog(sql), (
        "reescrever_homolog.py deixa `plat_leitor` global; trilha_reescrever.py ja o troca"
    )
