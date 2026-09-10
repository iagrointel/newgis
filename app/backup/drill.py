"""Núcleo puro do ensaio de restauração (item L0-06-c): nome do banco temporário, classificação das
diferenças de COUNT(*) e escolha dos objetos do bucket a conferir contra o manifesto. Sem banco e sem
rede — o caminho com efeito colateral fica em `app/backup/tarefas.py::backup_restore_drill`.

A base de comparação é o INSTANTE DO DUMP, não 'agora'. Entre o dump e o ensaio a produção continua
escrevendo, então:

- `restaurado > producao` (ou tabela ausente na cópia restaurada) é DIVERGÊNCIA: o que estava no backup
  não está mais na produção, ou o backup não devolve o que registrou. Falha o ensaio e notifica.
- `producao > restaurado` é diferença POSTERIOR ao dump: registrada e mostrada com a tabela e o delta,
  nunca escondida, mas não reprova o ensaio.

Limite honesto: uma remoção legítima de linhas na produção depois do dump aparece como divergência. É
deliberado — o ensaio prefere um alarme para conferir a um silêncio; a linha de `plat.backup_drill` traz
o instante do dump ao lado do número para quem confere.
"""

import re
from pathlib import Path

OBJETOS_POR_INQUILINO = 3
# Extensões que o banco de ensaio precisa ter ANTES do pg_restore, senão a restauração perde tabela em
# silêncio. Achado do 1º ensaio de verdade, 07/09: sem unaccent no banco de ensaio, a configuração de
# busca pt_sem_acento não nasce, a tabela `item` não é criada e o ensaio acusa "tabela ausente na cópia
# restaurada" — isto é, um dump do schema da plataforma só é restaurável numa base que já tenha todas.
# A lista NÃO mora mais aqui: mora em db/extensoes.txt (item L7-01-d), lida também pelo install.sh e
# pelo laco/trilha_ambiente.sh. Duplicá-la foi o defeito que o arquivo único fecha.
ARQUIVO_EXTENSOES = Path(__file__).resolve().parents[2] / "db" / "extensoes.txt"
_SEGURO = re.compile(r"[^a-z0-9_]+")
_NOME_EXTENSAO = re.compile(r"^[a-z0-9_]+$")


def extensoes_do_ensaio(arquivo: Path | None = None) -> tuple[str, ...]:
    """Nomes de db/extensoes.txt, na ordem do arquivo. Mesmo formato que o par grep/awk do bash lê: um
    nome por linha, `#` começa comentário, linha em branco ignorada."""
    caminho = arquivo or ARQUIVO_EXTENSOES
    nomes: list[str] = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        nome = linha.split("#", 1)[0].split()
        if not nome:
            continue
        if not _NOME_EXTENSAO.match(nome[0]):
            raise ValueError(f"nome de extensão inválido em {caminho}: {nome[0]}")
        nomes.append(nome[0])
    if not nomes:
        raise ValueError(f"lista de extensões vazia: {caminho}")
    return tuple(nomes)


def nome_banco_temporario(marca: str, limite: int = 63) -> str:
    """Identificador do banco de ensaio, sempre com o prefixo `plat_drill_` (o expurgo do runbook procura
    por ele) e sem nada que precise de aspas. Um banco por instalação (a marca é o schema da instalação):
    ele é criado uma vez, com PostGIS, e cada ensaio cria e derruba DENTRO dele o schema restaurado.
    Criar e derrubar um banco a cada ensaio custava 32 a 92 s só de `dropdb` nesta máquina (medido em
    07/09, carga 12); derrubar um schema dentro de um banco que já existe não paga esse preço."""
    limpo = _SEGURO.sub("_", marca.lower()).strip("_") or "sem_marca"
    return f"plat_drill_{limpo}"[:limite]


def classificar_contagens(contagens: list[dict]) -> tuple[list[dict], list[dict]]:
    """(divergencias, posteriores) a partir de [{tabela, restaurado, producao}]; `restaurado` None = a
    tabela existe na produção e não veio na cópia restaurada."""
    divergencias: list[dict] = []
    posteriores: list[dict] = []
    for linha in sorted(contagens, key=lambda c: c["tabela"]):
        restaurado, producao = linha["restaurado"], linha["producao"]
        if restaurado is None:
            divergencias.append({"tabela": linha["tabela"], "motivo": "tabela ausente na cópia restaurada",
                                 "restaurado": None, "producao": producao})
            continue
        delta = producao - restaurado
        if delta < 0:
            divergencias.append({"tabela": linha["tabela"],
                                 "motivo": "a cópia restaurada tem mais linhas que a produção",
                                 "restaurado": restaurado, "producao": producao, "delta": delta})
        elif delta > 0:
            posteriores.append({"tabela": linha["tabela"], "restaurado": restaurado,
                                "producao": producao, "delta": delta})
    return divergencias, posteriores


def escolher_objetos(objetos: list[dict], limite: int = OBJETOS_POR_INQUILINO) -> list[dict]:
    """Até `limite` objetos do manifesto, em ordem de chave (escolha determinística: o ensaio de hoje e o
    de amanhã conferem os mesmos objetos do mesmo manifesto)."""
    return sorted(objetos, key=lambda o: o["chave"])[:max(0, limite)]
