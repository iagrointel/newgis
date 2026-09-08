"""Ponte entre os parâmetros de consulta do protocolo Esri (`gdbVersion`, `historicMoment`) e a relação
versionada que o motor de consulta vai ler (item L2-13-a).

Fica separado de `servico` para que `app/consulta/rotas_query.py` — que é caminho quente — dependa só
disto, e não de todo o ciclo de vida de ramo.
"""

from __future__ import annotations

import datetime as dt

from app.auth.sessao import Auth
from app.erros import ErroAPI
from app.versionamento import leitura, servico

PADRAO = ("SDE.DEFAULT", "DEFAULT", "sde.DEFAULT")


def momento_de(valor: str):
    """`historicMoment` da Esri é epoch em MILISSEGUNDOS; aceitamos também data ISO 8601, que é o que
    uma pessoa digita na barra de endereço."""
    texto = str(valor).strip()
    if texto.lstrip("-").isdigit():
        return dt.datetime.fromtimestamp(int(texto) / 1000, tz=dt.timezone.utc)
    try:
        d = dt.datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError as e:
        raise ErroAPI(
            400, "historicmoment_invalido",
            "historicMoment precisa ser epoch em milissegundos ou data ISO 8601",
        ) from e
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def origem(
    cur, item_id: str, dados: dict, auth: Auth, gdb_version: str | None, historic_moment: str | None
) -> tuple[str | None, list]:
    """Devolve (relação SQL, parâmetros) para o `FROM` da consulta, ou (None, []) quando o pedido é a
    leitura comum do padrão agora."""
    quer_ramo = bool(gdb_version) and gdb_version not in PADRAO
    if not quer_ramo and not historic_moment:
        return None, []
    schema, tabela = leitura.nomes_ok(dados.get("schema"), dados.get("tabela"))
    srid = int(dados["srid"])
    if quer_ramo:
        if historic_moment:
            raise ErroAPI(
                422, "momento_em_ramo_fora",
                "historicMoment vale sobre o padrão; dentro de um ramo a leitura é sempre a do ramo agora",
            )
        if not (dados.get("versionamento") or {}).get("habilitado"):
            raise ErroAPI(422, "gdbversion_fora", "camada não versionada: só SDE.DEFAULT é aceito")
        v = servico.obter_versao(cur, item_id, gdb_version, auth)
        return leitura.relacao_do_ramo(cur, schema, tabela, srid, str(v["id"]), v["momento"])
    return leitura.relacao_padrao_no_momento(cur, schema, tabela, srid, momento_de(historic_moment))
