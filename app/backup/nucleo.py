"""Núcleo puro do backup lógico por inquilino (sem banco, sem subprocesso — tudo testável em unidade): nome
do arquivo de dump, sha256 em fluxo, nome do schema de ensaio e a classificação das diferenças de COUNT(*)
entre a cópia restaurada e a produção. O caminho com efeito colateral (pg_dump/pg_restore/psql, upload ao
Garage) fica em `app/backup/tarefas.py`."""

from __future__ import annotations

import hashlib
import re
import secrets
from pathlib import Path

PEDACO_SHA = 8 * 1024 * 1024
PREFIXO_SCHEMA_ENSAIO = "plat_ensaio_"


def nome_arquivo(esquema: str, agora) -> str:
    return f"{esquema}_{agora.strftime('%Y%m%d_%H%M%S')}.dump"


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while True:
            pedaco = f.read(PEDACO_SHA)
            if not pedaco:
                break
            h.update(pedaco)
    return h.hexdigest()


def nome_schema_ensaio() -> str:
    """`plat_ensaio_<8 hex>` — nunca colide com um schema de produção (schema de dado de inquilino é sempre
    `d_<slug>`; nenhum começa com este prefixo) e é o que `_largar_schema_ensaio` exige antes de qualquer
    DROP SCHEMA, para nunca derrubar nada que não seja do próprio ensaio."""
    return f"{PREFIXO_SCHEMA_ENSAIO}{secrets.token_hex(4)}"


def reescrever_schema(sql: str, esquema_origem: str, schema_ensaio: str) -> str:
    """Troca toda ocorrência de palavra inteira do nome do schema de origem (ex. `d_demo`) pelo nome do
    schema de ensaio no SQL de texto que `pg_restore -f` gerou — é assim que o restore cai num schema
    temporário em vez de colidir com o schema de produção do próprio inquilino (pg_restore não tem opção
    de renomear o schema de destino)."""
    return re.sub(rf"\b{re.escape(esquema_origem)}\b", schema_ensaio, sql)


def classificar_contagens(contagens: list[dict]) -> tuple[list[dict], list[dict]]:
    """(divergencias, posteriores) a partir de `[{tabela, restaurado, producao}]`.

    A base de comparação é o INSTANTE DO DUMP, não "agora": entre o dump e o ensaio a produção continua
    recebendo escrita, então `producao > restaurado` é esperado e vai para `posteriores` (não reprova o
    ensaio) — só `restaurado is None` (tabela ausente na cópia restaurada) ou `restaurado > producao`
    (a cópia tem mais linhas que a produção — nunca deveria acontecer) são divergência de verdade."""
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
            posteriores.append({"tabela": linha["tabela"], "restaurado": restaurado, "producao": producao,
                                "delta": delta})
    return divergencias, posteriores
