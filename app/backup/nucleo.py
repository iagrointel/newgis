"""Núcleo puro do backup lógico (sem banco, sem Garage/subprocesso — tudo testável em unidade): duas frentes.

L0-06-a-dump-logico (global, `app/backup/tarefas.py::backup_dump_logico`/`backup_verificar`): nome de
arquivo, sha256 em fluxo, checagem de espaço, seleção da retenção (14 diários + 8 semanais por schema) e o
manifesto por inquilino gravado no bucket junto com os dumps.

L0-06-backup-status (por inquilino, `app/backup/tarefas.py::backup_executar`/`backup_ensaio_restauracao`):
o mesmo nome de arquivo e sha256 em fluxo (funções compartilhadas — implementação idêntica nos dois
desenhos), mais o nome do schema de ensaio e a classificação das diferenças de COUNT(*) entre a cópia
restaurada e a produção. O caminho com efeito colateral (pg_dump/pg_restore/psql, upload ao Garage) fica em
`app/backup/tarefas.py`."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path

MANTER_DIARIOS = 14
MANTER_SEMANAIS = 8
MIN_LIVRE_GB = 10
PEDACO_SHA = 8 * 1024 * 1024
PREFIXO_SCHEMA_ENSAIO = "plat_ensaio_"


class EspacoInsuficiente(RuntimeError):
    """Livre abaixo do mínimo ANTES de escrever qualquer byte; a mensagem traz os dois números."""

    def __init__(self, livre_bytes: int, minimo_bytes: int, caminho: Path):
        self.livre_bytes = livre_bytes
        self.minimo_bytes = minimo_bytes
        super().__init__(
            f"espaço insuficiente para backup em {caminho}: livre {livre_bytes / 1e9:.1f} GB < "
            f"mínimo {minimo_bytes / 1e9:.1f} GB — nenhum dump foi escrito"
        )


def nome_arquivo(esquema: str, agora: datetime) -> str:
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


# ---------------------------------------------------------------------- L0-06-a-dump-logico (global)
def espaco_livre_bytes(caminho: Path) -> int:
    return shutil.disk_usage(caminho).free


def conferir_espaco(caminho: Path, min_livre_gb: int) -> int:
    """Devolve o livre em bytes; levanta EspacoInsuficiente ANTES de qualquer escrita quando abaixo do mínimo."""
    livre = espaco_livre_bytes(caminho)
    minimo = int(min_livre_gb) * 1_000_000_000
    if livre < minimo:
        raise EspacoInsuficiente(livre, minimo, caminho)
    return livre


def e_semanal(agora: datetime) -> bool:
    """O dump de domingo é também o semanal (retenção separada de 8 cópias)."""
    return agora.weekday() == 6


def selecao_retencao(linhas: list[dict], manter_diarios: int = MANTER_DIARIOS,
                     manter_semanais: int = MANTER_SEMANAIS) -> list[int]:
    """Ids a APAGAR. `linhas` = dicts com id/esquema/semanal/criado_em (qualquer ordem). Por schema, ficam os
    `manter_diarios` diários mais novos e os `manter_semanais` semanais mais novos; um dump semanal nunca
    conta como diário (senão os 14 diários seriam engolidos pelos domingos)."""
    por_esquema: dict[str, list[dict]] = {}
    for linha in linhas:
        por_esquema.setdefault(linha["esquema"], []).append(linha)
    apagar: list[int] = []
    for grupo in por_esquema.values():
        grupo.sort(key=lambda linha: (linha["criado_em"], linha["id"]), reverse=True)
        diarios = [linha for linha in grupo if not linha["semanal"]]
        semanais = [linha for linha in grupo if linha["semanal"]]
        apagar.extend(linha["id"] for linha in diarios[manter_diarios:])
        apagar.extend(linha["id"] for linha in semanais[manter_semanais:])
    return apagar


def manifesto_inquilino(slug: str, objetos: list[dict], agora: datetime) -> bytes:
    """Manifesto dos objetos do bucket por inquilino (chave, sha256, bytes), gravado junto no bucket."""
    doc = {
        "inquilino": slug,
        "gerado_em": agora.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "objetos": [
            {"chave": o["chave"], "sha256": o["sha256"], "bytes": o["bytes"]}
            for o in sorted(objetos, key=lambda o: o["chave"])
        ],
    }
    return (json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


# ---------------------------------------------------------------------- L0-06-backup-status (por inquilino)
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
