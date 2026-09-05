"""Relações declaradas (ADR 0004 seção 5): extratores por tipo (o uuid sai de `dados`, nunca se infere na consulta),
sincronização de plat.item_relacao na mesma transação do PUT do item, consultas usado-por / criado-a-partir-de /
ordem de exclusão (funções SECURITY DEFINER do banco, com `visivel` por pode_ler)."""

import uuid
from collections.abc import Callable

import psycopg2

from app.catalogo import comum
from app.erros import ErroAPI


def _uuids(valores) -> list[str]:
    saida = []
    for v in valores or []:
        if isinstance(v, dict):
            v = v.get("id") or v.get("item_id") or v.get("camada_id")
        try:
            u = str(uuid.UUID(str(v)))
        except (ValueError, TypeError):
            continue
        if u not in saida:
            saida.append(u)
    return saida


def _mapa(dados: dict) -> list[tuple[str, str, int | None]]:
    corpo = dados.get("corpo") or {}
    return [(u, "camada_de_mapa", i) for i, u in enumerate(_uuids(corpo.get("camadas")))]


def _vista(dados: dict) -> list[tuple[str, str, int | None]]:
    return [(u, "vista_de_camada", None) for u in _uuids([dados.get("camada_id")])]


def _app(dados: dict) -> list[tuple[str, str, int | None]]:
    corpo = dados.get("corpo") or {}
    mapas = corpo.get("mapas") or ([corpo["mapa_id"]] if corpo.get("mapa_id") else [])
    return [(u, "mapa_de_app", i) for i, u in enumerate(_uuids(mapas))]


def _amc(dados: dict) -> list[tuple[str, str, int | None]]:
    return [
        (u, "fator_de_motor", i) for i, u in enumerate(_uuids(f.get("camada_id") for f in dados.get("fatores") or []))
    ]


def _rede(dados: dict) -> list[tuple[str, str, int | None]]:
    camadas = dados.get("camadas") or {}
    return [
        (u, "rede_de_camada", i)
        for i, u in enumerate(_uuids([camadas.get("nos"), camadas.get("arestas"), camadas.get("equipamentos")]))
    ]


EXTRATORES: dict[str, Callable[[dict], list[tuple[str, str, int | None]]]] = {
    "mapa": _mapa,
    "cena": _mapa,
    "vista_de_camada": _vista,
    "app": _app,
    "painel": _app,
    "modelo_amc": _amc,
    "rede": _rede,
}


def tem_extrator(tipo: str) -> bool:
    return tipo in EXTRATORES


def extrair(tipo: str, dados: dict) -> list[tuple[str, str, int | None]]:
    f = EXTRATORES.get(tipo)
    return f(dados or {}) if f else []


def sincronizar(cur, tenant_id: int, item_id: str, desejadas: list[tuple[str, str, int | None]]) -> dict:
    """Iguala plat.item_relacao(origem = item_id) à lista (destino, tipo, posicao). Destino que o ator não lê = 422
    (mesmo código do gatilho: não confirma existência). Devolve {inseridas, removidas, atualizadas}."""
    cur.execute("SELECT destino, tipo, posicao FROM plat.item_relacao WHERE origem = %s::uuid", (item_id,))
    atuais = {(str(r["destino"]), r["tipo"]): r["posicao"] for r in cur.fetchall()}
    alvo = {(d, t): p for d, t, p in desejadas}
    inseridas = removidas = atualizadas = 0
    for chave in set(atuais) - set(alvo):
        cur.execute(
            "DELETE FROM plat.item_relacao WHERE origem = %s::uuid AND destino = %s::uuid AND tipo = %s",
            (item_id, chave[0], chave[1]),
        )
        removidas += 1
    for (destino, tipo), posicao in alvo.items():
        if destino == item_id:
            raise ErroAPI(422, "relacao_com_outro_inquilino", "um item não depende de si mesmo")
        cur.execute("SELECT 1 FROM plat.item WHERE id = %s::uuid", (destino,))
        if cur.fetchone() is None:
            raise ErroAPI(
                422,
                "relacao_com_outro_inquilino",
                "item inexistente, apagado ou de outro inquilino",
                {"destino": destino},
            )
        if (destino, tipo) in atuais:
            if atuais[(destino, tipo)] != posicao:
                cur.execute(
                    "UPDATE plat.item_relacao SET posicao = %s "
                    "WHERE origem = %s::uuid AND destino = %s::uuid AND tipo = %s",
                    (posicao, item_id, destino, tipo),
                )
                atualizadas += 1
            continue
        try:
            cur.execute("SAVEPOINT rel")
            cur.execute(
                "INSERT INTO plat.item_relacao(origem, destino, tipo, tenant_id, posicao) VALUES "
                "(%s::uuid, %s::uuid, %s, %s, %s)",
                (item_id, destino, tipo, tenant_id, posicao),
            )
            cur.execute("RELEASE SAVEPOINT rel")
        except psycopg2.Error as e:
            cur.execute("ROLLBACK TO SAVEPOINT rel")
            if isinstance(e, psycopg2.errors.ForeignKeyViolation):
                raise ErroAPI(
                    422, "relacao_familia_invalida", "tipo de relação fora do vocabulário", {"tipo": tipo}
                ) from e
            raise comum.erro_do_banco(e) from e
        inseridas += 1
    return {"inseridas": inseridas, "removidas": removidas, "atualizadas": atualizadas}


def _resumo(cur, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    cur.execute(
        "SELECT i.id, i.titulo, i.tipo, i.acesso, i.status, i.protegido, u.login AS dono_login, u.id AS dono_id, "
        "plat.pode_editar(i.id) AS pode_editar, "
        "(SELECT count(*) FROM plat.item_grupo g WHERE g.item_id = i.id) AS grupos "
        "FROM plat.item i JOIN plat.usuario u ON u.id = i.dono_id WHERE i.id = ANY (%s::uuid[])",
        (ids,),
    )
    return {str(r["id"]): r for r in cur.fetchall()}


def _linha(r: dict, resumo: dict | None) -> dict:
    if resumo is None:
        return {"id": str(r["id"]), "oculto": True}
    return {
        "id": str(r["id"]),
        "titulo": resumo["titulo"],
        "tipo": resumo["tipo"],
        "acesso": resumo["acesso"],
        "status": resumo["status"],
        "protegido": resumo["protegido"],
        "dono": {"id": resumo["dono_id"], "login": resumo["dono_login"]},
        "grupos": resumo["grupos"],
        "pode_editar": bool(resumo["pode_editar"]),
    }


def usado_por(cur, item_id: str, profundidade: int) -> list[dict]:
    cur.execute(
        "SELECT id, tipo_relacao, profundidade, caminho::text[] AS caminho, visivel, apaga_junto "
        "FROM plat.item_usado_por(%s::uuid, %s) ORDER BY profundidade, id",
        (item_id, profundidade),
    )
    linhas = cur.fetchall()
    resumos = _resumo(cur, [str(r["id"]) for r in linhas if r["visivel"]])
    saida = []
    for r in linhas:
        base = _linha(r, resumos.get(str(r["id"])) if r["visivel"] else None)
        base.update(
            {
                "tipo_relacao": r["tipo_relacao"],
                "profundidade": r["profundidade"],
                "caminho": [str(c) for c in r["caminho"]],
                "apaga_junto": r["apaga_junto"],
            }
        )
        saida.append(base)
    return saida


def criado_a_partir_de(cur, item_id: str) -> list[dict]:
    cur.execute("SELECT * FROM plat.item_criado_a_partir_de(%s::uuid)", (item_id,))
    linhas = cur.fetchall()
    resumos = _resumo(cur, [str(r["id"]) for r in linhas if r["visivel"]])
    saida = []
    for r in linhas:
        base = _linha(r, resumos.get(str(r["id"])) if r["visivel"] else None)
        base.update({"tipo_relacao": r["tipo_relacao"], "posicao": r["posicao"]})
        saida.append(base)
    return saida


def ordem_de_exclusao(cur, item_id: str) -> dict:
    """Fecho de dependentes em ordem topológica (dependentes mais fundos primeiro), o próprio item por último."""
    linhas = usado_por(cur, item_id, 20)
    linhas.sort(key=lambda x: -x["profundidade"])
    ocultos = sum(1 for x in linhas if x.get("oculto"))
    ordem = [x for x in linhas if not x.get("oculto")]
    return {"ordem": ordem, "ocultos": ocultos}
