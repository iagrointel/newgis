"""Normalização de nomes de camada/tabela/coluna (ADR 0005 seção 8). Função pura, testada por tabela em
`tests/unit/test_nomes.py`: minúsculo, sem acento, `[a-z0-9_]`, <= 63 bytes, sem começar por dígito, palavra
reservada ou coluna obrigatória com sufixo `_`, duplicata com `_2`, `_3`… O `motivo` (quando não None) vai para
`campos[].avisos` da proposta de importação."""

from __future__ import annotations

import re
import unicodedata

NOME_BYTES_MAX = 63

# Colunas que toda tabela de camada carrega (ADR 0005 seção 7.1) — nome de campo do dado que colidisse com elas
# tem de ganhar sufixo, senão o ALTER TABLE da carga falharia colidindo com a coluna nossa.
COLUNAS_OBRIGATORIAS = {
    "fid", "globalid", "versao", "tenant_id", "geom",
    "criado_em", "atualizado_em", "criado_por", "atualizado_por",
}

# Palavras reservadas do PostgreSQL 16 (pg_get_keywords() WHERE catcode IN ('R','T')), congeladas aqui (ADR 0005
# seção 8 item 6): usar um nome reservado sem aspas quebra o ALTER TABLE ... AS "<nome>" da carga.
RESERVADAS = frozenset("""
all analyse analyze and any array as asc asymmetric authorization between bigint binary bit boolean both case cast
char character check collate collation column concurrently constraint create cross current_catalog current_date
current_role current_schema current_time current_timestamp current_user default deferrable desc distinct do else
end except false fetch float for foreign freeze from full grant group grouping having ilike in initially inner
int integer intersect into is isnull join lateral leading left like limit localtime localtimestamp national
natural none not notnull null numeric offset on only or order out outer overlaps placing precision primary real
references returning right select session_user setof similar smallint some symmetric table then time timestamp
to trailing true union unique user using varchar variadic verbose when where window with
""".split())

_SUBST_LITERAL = {"²": "2", "³": "3", "&": "_e_", "%": "_pct", "#": "_n"}
_NAO_ALFANUM = re.compile(r"[^a-z0-9]+")
_SUBLINHADOS_REPETIDOS = re.compile(r"_{2,}")


def _sem_acentos(texto: str) -> tuple[str, bool]:
    """(texto sem diacríticos, True se algum byte era inválido/controle — U+FFFD ou caractere de controle)."""
    invalido = "�" in texto or any(ord(c) < 0x20 for c in texto if c not in "\t")
    for de, para in _SUBST_LITERAL.items():
        texto = texto.replace(de, para)
    # caractere de controle vira separador (nunca some em silêncio: "mun\x01icipios" não pode virar "municipios")
    texto = "".join(c if (ord(c) >= 0x20 or c == "\t") else " " for c in texto)
    nfkd = unicodedata.normalize("NFKD", texto)
    sem = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem, invalido


def normalizar(nome: str, usados: set[str] | None = None, *, posicao: int = 0) -> tuple[str, str | None]:
    """(nome_novo, motivo|None). `usados` é o conjunto (mutável, já em minúsculo) dos nomes já emitidos NESTA
    camada — a função acrescenta o próprio resultado a ele, então chame em ordem estável (ordem dos campos)."""
    if usados is None:
        usados = set()
    original = nome or ""
    sem, caractere_invalido = _sem_acentos(original)
    minusculo = sem.lower()
    limpo = _NAO_ALFANUM.sub("_", minusculo)
    limpo = _SUBLINHADOS_REPETIDOS.sub("_", limpo).strip("_")

    motivo = "caractere_invalido" if caractere_invalido else None
    if not limpo:
        limpo = f"campo_{posicao}"
        motivo = motivo or "nome_vazio"
    if limpo[0].isdigit():
        limpo = f"c_{limpo}"
        motivo = motivo or "digito_inicial"
    if len(limpo.encode("utf-8")) > NOME_BYTES_MAX:
        # corta em bytes, nunca no meio de um caractere multibyte (não deveria sobrar acento aqui, mas por
        # segurança decodifica ignorando o resto de um caractere cortado ao meio)
        limpo = limpo.encode("utf-8")[:NOME_BYTES_MAX].decode("utf-8", errors="ignore").rstrip("_")
        motivo = motivo or "comprimento"
    if limpo in RESERVADAS or limpo in COLUNAS_OBRIGATORIAS:
        sufixo = "_"
        while (limpo + sufixo) in usados:
            sufixo += "_"
        limpo = limpo + sufixo
        motivo = motivo or "reservado"

    base = limpo
    n = 2
    while limpo in usados:
        limpo = f"{base}_{n}"
        n += 1
        motivo = "duplicado"
    usados.add(limpo)
    return limpo, motivo


def normalizar_titulo(nome: str) -> str:
    """Título sugerido (editável pelo usuário na tela): mantém acento/caixa (é texto para gente, não
    identificador SQL) — só remove caractere de controle e byte inválido e comprime espaço."""
    texto = "".join(c for c in (nome or "") if ord(c) >= 0x20 and c != "�")
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto or "camada"
