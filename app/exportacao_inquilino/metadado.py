"""Metadado e estilo dentro do próprio GeoPackage (item L0-06-d-exportar-inquilino).

A hipótese do item pede o pacote "com estilo em JSON e metadado como tabelas gpkg_metadata". O GeoPackage
tem uma extensão padronizada para isso — `gpkg_metadata` e `gpkg_metadata_reference`, registradas em
`gpkg_extensions` (OGC GeoPackage 1.2, seção "extension_metadata") — e é ela que se usa aqui, em vez de uma
tabela inventada: quem abrir o arquivo no QGIS, no ogrinfo ou em qualquer leitor conforme encontra o metadado
no lugar previsto pela norma.

Por camada exportada gravamos DUAS linhas de metadado, ambas `mime_type = application/json`:

- escopo `dataset`, referência à tabela da camada: o cartão do item no catálogo (uuid, título, resumo,
  descrição, marcadores, datas) — é o que amarra a camada dentro do GeoPackage ao item do `catalogo.json`;
- escopo `dataset` também, mas com o estilo MapLibre do item de estilo ligado à camada por
  `plat.item_relacao`, quando existe um. O estilo continua em JSON (é MapLibre, não SLD): a norma não define
  formato de simbologia, define onde o documento vive.

`sqlite3` é da biblioteca padrão e o GeoPackage é um banco SQLite — não entra dependência nova, e o arquivo
já foi fechado pelo `ogr2ogr` quando esta função abre."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

URI_ESTILO = "https://maplibre.org/maplibre-style-spec/"
URI_ITEM = "https://plataforma.invalido/esquemas/exportacao_inquilino.schema.json"

DDL = (
    """CREATE TABLE IF NOT EXISTS gpkg_extensions (
        table_name TEXT, column_name TEXT, extension_name TEXT NOT NULL, definition TEXT NOT NULL,
        scope TEXT NOT NULL,
        CONSTRAINT ge_tce UNIQUE (table_name, column_name, extension_name))""",
    """CREATE TABLE IF NOT EXISTS gpkg_metadata (
        id INTEGER CONSTRAINT m_pk PRIMARY KEY ASC NOT NULL,
        md_scope TEXT NOT NULL DEFAULT 'dataset',
        md_standard_uri TEXT NOT NULL,
        mime_type TEXT NOT NULL DEFAULT 'text/xml',
        metadata TEXT NOT NULL DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS gpkg_metadata_reference (
        reference_scope TEXT NOT NULL, table_name TEXT, column_name TEXT, row_id_value INTEGER,
        timestamp DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        md_file_id INTEGER NOT NULL, md_parent_id INTEGER,
        CONSTRAINT crmr_mfi_fk FOREIGN KEY (md_file_id) REFERENCES gpkg_metadata(id),
        CONSTRAINT crmr_mpi_fk FOREIGN KEY (md_parent_id) REFERENCES gpkg_metadata(id))""",
)
EXTENSAO = (
    "INSERT OR IGNORE INTO gpkg_extensions(table_name, column_name, extension_name, definition, scope) "
    "VALUES (?, NULL, 'gpkg_metadata', 'http://www.geopackage.org/spec120/#extension_metadata', 'read-write')"
)

CAMPOS_CARTAO = ("id", "tipo", "titulo", "resumo", "descricao", "tags", "acesso", "origem",
                 "criado_em", "modificado_em")


def estilos_por_camada(catalogo: dict) -> dict[str, dict]:
    """Mapa `item_id da camada` -> `dados do item de estilo` ligado a ela por `plat.item_relacao`. A relação é
    gravada com `origem` = estilo e `destino` = camada (é assim que a transferência de dono a lê), mas aceitamos
    os dois sentidos: o que importa é que um dos lados seja um item de tipo `estilo`."""
    por_id = {i["id"]: i for i in catalogo["itens"]}
    saida: dict[str, dict] = {}
    for rel in catalogo.get("relacoes", []):
        a, b = por_id.get(rel["origem"]), por_id.get(rel["destino"])
        if a is None or b is None:
            continue
        if a["tipo"] == "estilo" and b["tipo"] == "camada_vetorial":
            saida.setdefault(b["id"], a.get("dados") or {})
        elif b["tipo"] == "estilo" and a["tipo"] == "camada_vetorial":
            saida.setdefault(a["id"], b.get("dados") or {})
    return saida


def gravar(caminho_gpkg: Path, camadas: list[tuple[str, dict]], catalogo: dict) -> int:
    """`camadas` é a lista de (nome da tabela dentro do GeoPackage, item do catálogo). Devolve quantas linhas de
    `gpkg_metadata` foram escritas."""
    if not camadas:
        return 0
    estilos = estilos_por_camada(catalogo)
    escritas = 0
    con = sqlite3.connect(str(caminho_gpkg))
    try:
        for ddl in DDL:
            con.execute(ddl)
        for tabela in ("gpkg_metadata", "gpkg_metadata_reference"):
            con.execute(EXTENSAO, (tabela,))
        for nome_tabela, item in camadas:
            cartao = {c: item.get(c) for c in CAMPOS_CARTAO}
            escritas += _uma(con, nome_tabela, URI_ITEM, cartao)
            estilo = estilos.get(item["id"])
            if estilo:
                escritas += _uma(con, nome_tabela, URI_ESTILO, estilo)
        con.commit()
    finally:
        con.close()
    return escritas


def _uma(con: sqlite3.Connection, nome_tabela: str, uri: str, documento: dict) -> int:
    cur = con.execute(
        "INSERT INTO gpkg_metadata(md_scope, md_standard_uri, mime_type, metadata) "
        "VALUES ('dataset', ?, 'application/json', ?)",
        (uri, json.dumps(documento, ensure_ascii=False, default=str)),
    )
    con.execute(
        "INSERT INTO gpkg_metadata_reference(reference_scope, table_name, md_file_id) "
        "VALUES ('table', ?, ?)",
        (nome_tabela, cur.lastrowid),
    )
    return 1


def ler(caminho_gpkg: Path) -> list[dict]:
    """Lê de volta o que `gravar` escreveu (usado pelo teste do portão e por quem receber o pacote).

    Filtra pelos DOIS `md_standard_uri` desta casa de propósito: o próprio GDAL grava em `gpkg_metadata`, na
    mesma tabela, o bloco `<GDALMultiDomainMetadata>` com o que ele sabe do arquivo de origem (medido: uma
    conversão de GeoJSON já deixa uma linha em XML). Ler tudo e tentar decodificar como JSON quebraria em
    cima do metadado do GDAL — que é legítimo e não deve ser apagado."""
    con = sqlite3.connect(str(caminho_gpkg))
    try:
        con.row_factory = sqlite3.Row
        try:
            linhas = con.execute(
                "SELECT r.table_name, m.md_standard_uri, m.mime_type, m.metadata "
                "FROM gpkg_metadata_reference r JOIN gpkg_metadata m ON m.id = r.md_file_id "
                "WHERE m.md_standard_uri IN (?, ?) AND m.mime_type = 'application/json' ORDER BY m.id",
                (URI_ITEM, URI_ESTILO),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [
            {"tabela": ln["table_name"], "uri": ln["md_standard_uri"], "mime_type": ln["mime_type"],
             "documento": json.loads(ln["metadata"])}
            for ln in linhas
        ]
    finally:
        con.close()
