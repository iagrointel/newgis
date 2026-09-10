"""Avisos de fidelidade da exportação (item L6-02-o): o que o formato de destino faz com os campos, dito ANTES
de gerar — o GDAL executa a transformação em silêncio ("Warning 6" no stderr, que o usuário nunca vê).

Regras MEDIDAS no GDAL 3.8.4 desta máquina (06/09/2026, prova em tests/unit/test_intercambio_avisos.py):

- DBF (shapefile) trunca nome de campo em 10 caracteres: "comprimento_total" → "compriment"; na colisão,
  8 caracteres + "_" + contador: "comprimento_parcial" → "comprime_1".
- DBF não tem tipo data-hora: DateTime vira campo texto com ISO 8601 ("2026-09-06T10:20:30Z"); Date (sem
  hora) é preservado como Date.
- DBF limita campo texto a 254 caracteres: valor maior é truncado pelo driver.
"""

from __future__ import annotations

from app import limites

NOME_DBF_MAX = 10


def nome_dbf(nome: str, usados: set[str]) -> str:
    """O nome que o GDAL 3.8.4 grava no DBF (medido): 10 primeiros caracteres; se colide, 8 + '_' + 1..9,
    depois 7 + '_' + 10..99. Nunca devolve nome já usado."""
    base = nome[:NOME_DBF_MAX]
    if base not in usados:
        usados.add(base)
        return base
    for largura, inicio in ((8, 1), (7, 10), (6, 100)):
        for i in range(inicio, inicio * 10):
            candidato = f"{nome[:largura]}_{i}"
            if candidato not in usados:
                usados.add(candidato)
                return candidato
    raise ValueError(f"sem nome DBF livre para o campo {nome!r}")


def mapa_nomes_dbf(campos: list[dict]) -> dict[str, str]:
    """{nome_do_campo: nome_no_dbf} só dos campos cujo nome MUDA (o que já cabe não entra no mapa)."""
    usados: set[str] = set()
    mapa: dict[str, str] = {}
    for c in campos:
        nome = c["nome"]
        gravado = nome_dbf(nome, usados)
        if gravado != nome:
            mapa[nome] = gravado
    return mapa


def avisos_shapefile(
    campos: list[dict], max_len_texto: dict[str, int] | None = None
) -> tuple[dict[str, str], list[str]]:
    """(mapa de nomes truncados, avisos por campo) para uma exportação shapefile.zip.

    `campos`: [{nome, tipo}] como em item.dados.campos (tipos do PostGIS: text, integer, bigint,
    double precision, date, "timestamp with time zone"...). `max_len_texto`: {campo: maior comprimento
    medido} (consulta no banco); quando informado, valor acima do limite DBF ganha aviso próprio de
    truncamento de VALOR."""
    mapa = mapa_nomes_dbf(campos)
    avisos: list[str] = []
    for nome, gravado in mapa.items():
        avisos.append(
            f"campo {nome!r} tem mais de {NOME_DBF_MAX} caracteres: no shapefile ele se chama {gravado!r} "
            "(limite do formato DBF)"
        )
    for c in campos:
        if c.get("tipo") in ("timestamp with time zone", "timestamp without time zone", "time"):
            avisos.append(
                f"campo {c['nome']!r} é data-hora: o shapefile não tem tipo data-hora; ele é gravado como "
                "texto ISO 8601"
            )
    for nome, maior in (max_len_texto or {}).items():
        if maior > limites.INTERCAMBIO_DBF_LARGURA_MAX:
            avisos.append(
                f"campo {nome!r} tem texto de até {maior} caracteres: o shapefile grava no máximo "
                f"{limites.INTERCAMBIO_DBF_LARGURA_MAX}; os valores serão truncados"
            )
    return mapa, avisos
