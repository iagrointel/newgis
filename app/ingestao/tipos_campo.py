"""Mapa de tipo de campo OGR -> PostgreSQL (ADR 0005 seção 7.2, reduzido aos tipos que os 4 formatos desta
passagem produzem) e as promoções que a tela oferece em `opcoes_tipo`."""

from __future__ import annotations

MAPA = {
    "String": "text",
    "Integer": "integer",
    "Integer/Boolean": "boolean",
    "Integer64": "bigint",
    "Real": "double precision",
    "Real/Float32": "real",
    "Date": "date",
    "Time": "time",
    "DateTime": "timestamp with time zone",
    "Binary": "bytea",
}

PROMOCOES = {
    "text": ["text", "bigint", "integer", "double precision"],
    "integer": ["integer", "bigint", "double precision", "text"],
    "bigint": ["bigint", "double precision", "text"],
    "double precision": ["double precision", "text"],
    "real": ["real", "double precision", "text"],
    "boolean": ["boolean", "text"],
    "date": ["date", "text"],
    "time": ["time", "text"],
    "timestamp with time zone": ["timestamp with time zone", "text"],
    "bytea": ["bytea"],
}


def pg_de(tipo_ogr: str, subtipo: str | None = None) -> str:
    chave = f"{tipo_ogr}/{subtipo}" if subtipo else tipo_ogr
    return MAPA.get(chave, MAPA.get(tipo_ogr, "text"))


def opcoes_de(tipo_pg: str) -> list[str]:
    return PROMOCOES.get(tipo_pg, [tipo_pg])
