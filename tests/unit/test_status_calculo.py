"""Item L0-06-e-status, parte que não precisa de banco: o filtro do log de correções e o agregado de disco
(que existe justamente para o caminho do volume não sair na resposta)."""

from app.status import _disco_agregado, correcoes

CHANGELOG_EXEMPLO = """# CHANGELOG

## turno 3

L0-06-a: dump lógico por inquilino com sha256 e retenção. Correção: o evento `backup/falha` não existia
e a notificação virava silêncio.

L2-01: mapa com camadas do catálogo, sem novidade a registrar.

| sha | mensagem |
|---|---|
| `abc1234` | Correção que veio na tabela de commits e não deve entrar na página |

## turno 2

Correção da ordem de montagem do middleware de corpo grande.
"""


def test_correcoes_pega_so_as_frases_de_correcao_com_a_secao():
    achadas = correcoes(CHANGELOG_EXEMPLO)
    assert [c["secao"] for c in achadas] == ["turno 3", "turno 2"]
    # o trecho em crase é omitido de propósito (higienização): a página é aberta
    assert achadas[0]["texto"] == "Correção: o evento … não existia e a notificação virava silêncio."
    assert achadas[1]["texto"] == "Correção da ordem de montagem do middleware de corpo grande."
    assert all("mapa com camadas" not in c["texto"] for c in achadas)


def test_correcoes_ignora_a_tabela_de_commits():
    assert all("tabela de commits" not in c["texto"] for c in correcoes(CHANGELOG_EXEMPLO))


def test_correcoes_respeita_o_limite():
    assert len(correcoes(CHANGELOG_EXEMPLO, limite=1)) == 1


def test_correcoes_de_changelog_sem_correcao_e_lista_vazia():
    assert correcoes("# CHANGELOG\n\n## turno 1\n\nprimeira entrega, nada a consertar\n") == []


def test_disco_agregado_nao_carrega_caminho_de_volume():
    entrada = {"estado": "ok", "volumes": {"/": {"estado": "ok", "livre_pct": 12.0},
                                           "/mnt/pgdata": {"estado": "degradado", "livre_pct": 4.5}}}
    saida = _disco_agregado(entrada)
    assert saida == {"estado": "ok", "volumes": 2, "menor_livre_pct": 4.5}
    assert "/" not in str(saida) and "pgdata" not in str(saida)


def test_disco_agregado_sem_volume_nao_inventa_percentual():
    saida = _disco_agregado({"estado": "ausente", "motivo": "nenhum volume declarado existe"})
    assert saida == {"estado": "ausente", "volumes": 0, "menor_livre_pct": None}


RELATORIO_GARAGE = """Storage nodes:
  ID                Hostname        Zone  Capacity  Part.  DataAvail
  39b93a03d62f349a  maquina-de-teste  dc1   27.9 GiB  256    31.6 GiB/468.3 GiB (6.8%)

Number of buckets:        269
Total number of objects:  1704
Total size of objects:    7.1 GiB

Estimated available storage space cluster-wide (might be lower in practice):
  data: 31.6 GiB
  metadata: 31.6 GiB
"""


def test_medir_bucket_le_os_numeros_do_relatorio_do_garage():
    from app.status import medir_bucket

    m = medir_bucket(RELATORIO_GARAGE)
    assert m["buckets"] == 269 and m["objetos"] == 1704
    assert m["bytes_aprox"] == int(7.1 * 1024**3)
    assert m["livre_bytes_aprox"] == int(31.6 * 1024**3)
    assert "maquina-de-teste" not in str(m)  # o nome da máquina de armazenamento nunca sai do relatório


def test_medir_bucket_com_relatorio_estranho_devolve_nulo_e_nao_zero():
    from app.status import medir_bucket

    m = medir_bucket("relatório em outro formato\n")
    assert m == {"buckets": None, "objetos": None, "bytes_aprox": None, "livre_bytes_aprox": None}


def test_higienizar_tira_pilha_caminho_versao_e_codigo():
    from app.status import higienizar

    frase = higienizar("Corrigido em `app/db.py`: o psycopg2 2.9.9 falhava em /etc/plat/segredos.")
    for proibido in ("psycopg2", "2.9.9", "/etc/plat", "app/db.py"):
        assert proibido not in frase, (proibido, frase)
    assert frase.startswith("Corrigido em")


def test_correcao_que_so_sobra_em_pedacos_nao_entra_na_pagina():
    from app.status import MAX_OMISSOES, correcoes

    texto = ("# c\n\n## turno 9\n\nCorrigido `a.py` com `b.py` em `c.py` e `d.py` mais `e.py`.\n\n"
             "Correção simples de ortografia na tela.\n")
    achadas = correcoes(texto)
    assert [c["texto"] for c in achadas] == ["Correção simples de ortografia na tela."]
    assert MAX_OMISSOES >= 1
