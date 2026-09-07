"""Metadado de campos de uma camada hospedada (`d_<slug>.c_<uuid16>`, ADR 0005) traduzido para o
vocabulário Esri (`esriFieldType`) — item L2-04-c. Usado pela operação `query` do FeatureServer para
`outFields`, para a resposta PBF/JSON (`Field`), e para construir a LISTA BRANCA que `where_ast`
exige: nunca "todas as colunas da tabela" descobertas às cegas, sempre esta função, que já filtra
`geom` e `tenant_id` (controle interno de RLS, nunca exposto como atributo do cliente)."""

from __future__ import annotations

import re

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# ADR 0005 §7.2 (tipos_campo.MAPA) na direção inversa + os tipos que só existem depois da carga
# (globalid/versao/criado_em/... de plat.camada_preparar) — ver docs/adr do L2-04-c para a tabela completa.
TIPO_ESRI = {
    "text": "esriFieldTypeString",
    "character varying": "esriFieldTypeString",
    "character": "esriFieldTypeString",
    "integer": "esriFieldTypeInteger",
    "smallint": "esriFieldTypeSmallInteger",
    "bigint": "esriFieldTypeBigInteger",
    "double precision": "esriFieldTypeDouble",
    "real": "esriFieldTypeSingle",
    "numeric": "esriFieldTypeDouble",
    "boolean": "esriFieldTypeSmallInteger",  # Esri não tem booleano nativo; convertido para 0/1 na saída
    "date": "esriFieldTypeDateOnly",
    "time without time zone": "esriFieldTypeTimeOnly",
    "time": "esriFieldTypeTimeOnly",
    "timestamp with time zone": "esriFieldTypeDate",
    "timestamp without time zone": "esriFieldTypeDate",
    "uuid": "esriFieldTypeGUID",
    "bytea": "esriFieldTypeBlob",
    "jsonb": "esriFieldTypeString",
    "json": "esriFieldTypeString",
}

COMPRIMENTO_PADRAO = {"esriFieldTypeString": 255, "esriFieldTypeGUID": 38}

# colunas de controle interno (RLS/multi-inquilino) nunca expostas como atributo — P6/P7
_OCULTAS = {"tenant_id"}
# colunas de controle expostas normalmente como atributo (a Esri tem editFieldsInfo para isso)
_EDIT_FIELDS = {"criado_em", "atualizado_em", "criado_por", "atualizado_por"}


def campos_da_camada(cur, schema: str, tabela: str) -> list[dict]:
    """[{"nome","tipo_pg","tipo_esri","nullable","comprimento","papel"}] na ordem física da
    tabela; `papel` é "oid" (fid), "globalid", "geometria_controle" (versao) ou "atributo"."""
    cur.execute(
        "SELECT column_name, data_type, is_nullable, character_maximum_length "
        "FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
        (schema, tabela),
    )
    campos = []
    for r in cur.fetchall():
        nome = r["column_name"]
        if nome == "geom" or nome in _OCULTAS:
            continue
        tipo_pg = r["data_type"]
        if nome == "fid":
            papel, tipo_esri = "oid", "esriFieldTypeOID"
        elif nome == "globalid":
            papel, tipo_esri = "globalid", "esriFieldTypeGlobalID"
        else:
            papel = "editField" if nome in _EDIT_FIELDS else "atributo"
            tipo_esri = TIPO_ESRI.get(tipo_pg, "esriFieldTypeString")
        campos.append({
            "nome": nome,
            "tipo_pg": tipo_pg,
            "tipo_esri": tipo_esri,
            "nullable": r["is_nullable"] == "YES",
            "comprimento": r["character_maximum_length"] or COMPRIMENTO_PADRAO.get(tipo_esri),
            "papel": papel,
        })
    return campos


def lista_branca(campos: list[dict]) -> dict[str, str]:
    """nome → `"nome"` (identificador entre aspas), só dos campos revalidados pelo regex — é o que
    `where_ast.compilar`/`compilar_where` recebem como lista branca; nunca a tabela inteira."""
    return {c["nome"]: f'"{c["nome"]}"' for c in campos if IDENT_RE.match(c["nome"])}


def campos_texto(campos: list[dict]) -> list[str]:
    """Nomes dos campos `text`/`character varying` — é o universo de colunas que `fullText`
    (11.4) varre com `to_tsvector`."""
    return [c["nome"] for c in campos if c["tipo_pg"] in ("text", "character varying", "character")]


def por_nome(campos: list[dict]) -> dict[str, dict]:
    return {c["nome"]: c for c in campos}
