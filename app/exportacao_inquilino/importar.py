"""Importador do pacote de exportação num inquilino NOVO — a prova de portabilidade do portão de pronto
(`L0-06-d-exportar-inquilino`): "importar o pacote num inquilino novo recria itens com os mesmos uuids".

Escopo desta versão (registrado também no handoff): recria os ITENS DE CATÁLOGO com os mesmos `id` —
`plat.item`, `plat.pasta` e `plat.grupo` — a partir de `catalogo.json`. NÃO reimporta o conteúdo das camadas
hospedadas de volta para tabela do PostgreSQL (isso é o item de INGESTÃO, L0-04-a, que já sabe ler um GPKG;
rodar `dados.gpkg` por ele fica para quem for compor os dois itens) nem os arquivos do bucket de volta ao
Garage (o item continua com `dados.chave` apontando para o objeto original, que pode não existir na instalação
de destino). O que este módulo prova é exatamente a cláusula pedida: os UUIDs de item sobrevivem à viagem em
formato aberto — o `catalogo.json` é dado público sobre a estrutura do inquilino, não a camada em si.

Pré-condição: o inquilino de destino não tem NENHUM item com um dos ids do catálogo (senão a chave primária
recusa e a função levanta `ErroImportacao` sem tocar em nada — tudo dentro de uma única transação do `cur`
passado por quem chama, que decide se comita)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path


class ErroImportacao(Exception):
    pass


def ler_catalogo_do_pacote(caminho_zip: Path) -> dict:
    with zipfile.ZipFile(caminho_zip) as z:
        with z.open("catalogo.json") as f:
            return json.loads(f.read().decode("utf-8"))


def importar_catalogo(cur, tenant_id: int, dono_id: int, catalogo: dict) -> dict:
    """Insere pastas, itens e grupos do catálogo no inquilino `tenant_id`, com os MESMOS uuids do pacote.
    `dono_id` é o usuário do inquilino de destino que vira dono de tudo (o catálogo original tem `dono_id`
    da origem, que não existe no destino — mapear usuário por usuário é decisão de produto fora deste item).
    Devolve a contagem do que foi criado; levanta `ErroImportacao` se algum id já existir no destino."""
    cur.execute(
        "SELECT id FROM plat.item WHERE id = ANY(%s::uuid[])",
        ([i["id"] for i in catalogo["itens"]],),
    )
    if cur.fetchone():
        raise ErroImportacao("pelo menos um item do pacote já existe no inquilino de destino")

    for pasta in catalogo["pastas"]:
        cur.execute(
            "INSERT INTO plat.pasta(id, tenant_id, pai_id, nome, dono_id) VALUES (%s::uuid, %s, %s::uuid, %s, %s)",
            (pasta["id"], tenant_id, pasta.get("pai_id"), pasta["nome"], dono_id),
        )
    for item in catalogo["itens"]:
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, resumo, descricao, tags, dono_id, pasta_id, "
            "dados, acesso, origem, tamanho_bytes, criado_por, modificado_por) "
            "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s::uuid, %s, %s, %s, %s, %s, %s)",
            (item["id"], tenant_id, item["tipo"], item["titulo"], item.get("resumo"), item.get("descricao"),
             item.get("tags") or [], dono_id, item.get("pasta_id"), json.dumps(item.get("dados") or {}),
             item.get("acesso", "privado"), item.get("origem", "hospedado"), item.get("tamanho_bytes", 0),
             dono_id, dono_id),
        )
    for grupo in catalogo["grupos"]:
        cur.execute(
            "INSERT INTO plat.grupo(id, tenant_id, nome, resumo, visibilidade, entrada, contribuicao, dono_id) "
            "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s)",
            (grupo["id"], tenant_id, grupo["nome"], grupo.get("resumo"), grupo.get("visibilidade", "membros"),
             grupo.get("entrada", "convite"), grupo.get("contribuicao", "todos"), dono_id),
        )
    return {
        "pastas": len(catalogo["pastas"]), "itens": len(catalogo["itens"]), "grupos": len(catalogo["grupos"]),
    }
