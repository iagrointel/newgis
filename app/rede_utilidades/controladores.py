"""Controlador de subrede e ciclo de vida da subrede (item L4-04-a-controladores-e-tiers; ADR 20260907T2031).

Um CONTROLADOR de subrede é o TERMINAL de um dispositivo que marca onde a subrede começa (papel `fonte`) ou
termina (papel `sumidouro`) dentro de um TIER. O tier já existe no modelo desde o pacote de ativos
(`plat.rede_tier`: `ordem` dá a hierarquia subestação > alimentador > transformador > baixa tensão, e `tipo`
diz se é `hierarquico` ou `particionado`).

Regras aplicadas aqui, com a fonte de cada uma:
  * só é controlador o terminal de um tipo de ativo que carrega a categoria de rede `controlador`
    (subnetwork-controller.htm: o ativo precisa da categoria de rede atribuída na configuração);
  * o NOME do controlador é único dentro do tier ("A unique name for the controller in the tier must be
    provided"); o nome da SUBREDE é outro campo, e uma subrede pode ter mais de um controlador ("Both radial
    and mesh subnetworks support multiple subnetwork controllers");
  * o controlador é preso ao TERMINAL, não à feição inteira ("Subnetwork controllers are set at the terminal
    level"); um dispositivo sem terminal declarado no pacote não pode ser controlador;
  * a subrede nasce SUJA e só fica limpa depois de `atualizar()` (subnetwork-life-cycle.htm: a subrede é
    marcada como suja por edição e volta a limpa quando é atualizada).

A âncora gravada é a feição + o número do terminal, nunca o nó de topologia: `topologia.habilitar()` apaga e
refaz `plat.rede_topo_no` inteiro, e uma chave estrangeira para o nó levaria o controlador junto na primeira
reconstrução. O nó corrente é resolvido na leitura (`_no_corrente`)."""

import json
import time

from app.erros import ErroAPI
from app.rede_utilidades import tracado

CATEGORIA_CONTROLADOR = "controlador"
PAPEIS = ("fonte", "sumidouro")


# --- leitura do catálogo ------------------------------------------------------------------------------

def _tier(cur, rede_id: str, codigo: str) -> dict:
    cur.execute(
        "SELECT id, codigo, nome, ordem, tipo FROM plat.rede_tier WHERE rede_id = %s::uuid AND codigo = %s",
        (rede_id, codigo),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "tier_inexistente", f"a rede não tem o tier '{codigo}'")
    return dict(r)


def _feicao_controlavel(cur, rede_id: str, feicao_id: str, terminal_num: int | None) -> dict:
    """A feição existe nesta rede, o tipo dela carrega a categoria `controlador` e o terminal pedido é um dos
    terminais que o pacote declara para esse tipo. Devolve tipo_id, tier do tipo e a coordenada."""
    cur.execute(
        "SELECT f.tipo_id, tp.tier_id, tp.chave AS tipo_chave, g.codigo AS grupo, "
        "       tc.terminais, ST_X(f.geom) AS lon, ST_Y(f.geom) AS lat, "
        "       EXISTS (SELECT 1 FROM plat.rede_tipo_categoria tcat "
        "               JOIN plat.rede_categoria c ON c.id = tcat.categoria_id "
        "               WHERE tcat.tipo_id = tp.id AND c.codigo = %s) AS eh_controlador "
        "FROM plat.rede_feicao_ponto f "
        "JOIN plat.rede_tipo tp ON tp.id = f.tipo_id "
        "JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "LEFT JOIN plat.rede_terminal_config tc ON tc.id = tp.terminal_id "
        "WHERE f.rede_id = %s::uuid AND f.id = %s::uuid",
        (CATEGORIA_CONTROLADOR, rede_id, feicao_id),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "feicao_inexistente", "esta feição de ponto não existe nesta rede")
    if not r["eh_controlador"]:
        raise ErroAPI(
            422, "categoria_nao_controladora",
            f"o tipo de ativo '{r['grupo']}/{r['tipo_chave']}' não tem a categoria de rede "
            f"'{CATEGORIA_CONTROLADOR}': só um tipo com essa categoria pode controlar uma subrede",
        )
    numeros = [t["id"] for t in (r["terminais"] or [])]
    if not numeros:
        raise ErroAPI(
            422, "tipo_sem_terminal",
            f"o tipo de ativo '{r['grupo']}/{r['tipo_chave']}' não declara terminal no pacote; "
            "o controlador de subrede é definido no terminal",
        )
    if terminal_num is None:
        if len(numeros) > 1:
            raise ErroAPI(422, "terminal_obrigatorio",
                          f"este tipo tem {len(numeros)} terminais: informe qual ({sorted(numeros)})")
        terminal_num = numeros[0]
    if terminal_num not in numeros:
        raise ErroAPI(422, "terminal_invalido",
                      f"terminal {terminal_num} não existe neste tipo de ativo (declarados: {sorted(numeros)})")
    return {"tipo_id": str(r["tipo_id"]), "tier_id_do_tipo": str(r["tier_id"]), "terminal_num": terminal_num,
            "lon": r["lon"], "lat": r["lat"], "grupo": r["grupo"], "tipo_chave": r["tipo_chave"]}


# --- subrede ------------------------------------------------------------------------------------------

def _subrede_id(cur, tenant_id: int, rede_id: str, tier_id: str, nome: str) -> str:
    cur.execute(
        "SELECT id FROM plat.rede_subrede WHERE rede_id = %s::uuid AND tier_id = %s::uuid AND nome = %s",
        (rede_id, tier_id, nome),
    )
    r = cur.fetchone()
    if r is not None:
        return str(r["id"])
    cur.execute(
        "INSERT INTO plat.rede_subrede(tenant_id, rede_id, tier_id, nome) "
        "VALUES (%s, %s::uuid, %s::uuid, %s) RETURNING id",
        (tenant_id, rede_id, tier_id, nome),
    )
    return str(cur.fetchone()["id"])


def _sujar(cur, subrede_id: str) -> None:
    cur.execute("UPDATE plat.rede_subrede SET estado = 'suja' WHERE id = %s::uuid", (subrede_id,))


# --- definir e remover --------------------------------------------------------------------------------

def definir(cur, tenant_id: int, rede_id: str, *, feicao_id: str, terminal: int | None, subrede: str,
            tier_codigo: str, papel: str, nome: str | None = None, usuario_id: int | None = None) -> dict:
    """Marca o terminal de um dispositivo como controlador da subrede `subrede` no tier `tier_codigo`."""
    if papel not in PAPEIS:
        raise ErroAPI(422, "papel_invalido", f"papel deve ser um de {PAPEIS}")
    tier = _tier(cur, rede_id, tier_codigo)
    info = _feicao_controlavel(cur, rede_id, feicao_id, terminal)
    sub_id = _subrede_id(cur, tenant_id, rede_id, str(tier["id"]), subrede)
    nome = nome or subrede

    cur.execute(
        "SELECT nome FROM plat.rede_controlador WHERE rede_id = %s::uuid AND tier_id = %s::uuid AND nome = %s",
        (rede_id, str(tier["id"]), nome),
    )
    if cur.fetchone() is not None:
        raise ErroAPI(
            409, "nome_de_controlador_repetido",
            f"já existe um controlador chamado '{nome}' no tier '{tier['codigo']}': o nome do controlador é "
            "único dentro do tier (o nome da SUBREDE é que pode reunir vários controladores)",
        )
    cur.execute(
        "SELECT id FROM plat.rede_controlador WHERE rede_id = %s::uuid AND feicao_id = %s::uuid "
        "AND coalesce(terminal_num, 0) = %s",
        (rede_id, feicao_id, info["terminal_num"]),
    )
    if cur.fetchone() is not None:
        raise ErroAPI(409, "terminal_ja_controlador",
                      "este terminal já é controlador de uma subrede desta rede")

    cur.execute(
        "INSERT INTO plat.rede_controlador(tenant_id, rede_id, subrede_id, tier_id, nome, origem, feicao_id, "
        "terminal_num, tipo_id, papel, geom, criado_por) "
        "VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, 'dispositivo', %s::uuid, %s, %s::uuid, %s, "
        "ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s) RETURNING id, criado_em",
        (tenant_id, rede_id, sub_id, str(tier["id"]), nome, feicao_id, info["terminal_num"],
         info["tipo_id"], papel, info["lon"], info["lat"], usuario_id),
    )
    novo = cur.fetchone()
    _sujar(cur, sub_id)
    return {"id": str(novo["id"]), "subrede_id": sub_id, "subrede": subrede, "nome": nome,
            "tier": tier["codigo"], "tier_tipo": tier["tipo"], "papel": papel,
            "feicao_id": feicao_id, "terminal": info["terminal_num"], "tipo_id": info["tipo_id"],
            "grupo": info["grupo"], "tipo_chave": info["tipo_chave"], "origem": "dispositivo",
            "criado_em": novo["criado_em"]}


def remover(cur, rede_id: str, controlador_id: str) -> dict:
    cur.execute(
        "DELETE FROM plat.rede_controlador WHERE rede_id = %s::uuid AND id = %s::uuid "
        "RETURNING subrede_id, nome, tier_id",
        (rede_id, controlador_id),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "controlador_inexistente", "este controlador não existe nesta rede")
    sub_id = str(r["subrede_id"])
    _sujar(cur, sub_id)
    cur.execute("SELECT count(*) AS n FROM plat.rede_controlador WHERE subrede_id = %s::uuid", (sub_id,))
    restantes = cur.fetchone()["n"]
    if restantes == 0:
        # subrede sem controlador nenhum deixa de existir: a subrede É o conjunto controlado.
        cur.execute("DELETE FROM plat.rede_subrede WHERE id = %s::uuid", (sub_id,))
    return {"subrede_id": sub_id, "nome": r["nome"], "controladores_restantes": restantes}


# --- leitura ------------------------------------------------------------------------------------------

_SQL_CONTROLADOR = (
    "SELECT c.id, c.nome, c.papel, c.origem, c.feicao_id, c.terminal_num, c.tipo_id, c.criado_em, "
    "       c.subrede_id, s.nome AS subrede, t.codigo AS tier, t.nome AS tier_nome, t.tipo AS tier_tipo, "
    "       t.ordem AS tier_ordem, g.codigo AS grupo, tp.chave AS tipo_chave, tp.nome AS tipo_nome, "
    "       ST_X(c.geom) AS lon, ST_Y(c.geom) AS lat, "
    "       (SELECT n.id FROM plat.rede_topo_no n WHERE n.rede_id = c.rede_id AND ("
    "          (c.feicao_id IS NOT NULL AND n.origem_id = c.feicao_id AND n.terminal_num = c.terminal_num) "
    "          OR (c.feicao_id IS NULL AND n.geom = c.geom)) LIMIT 1) AS no_id "
    "FROM plat.rede_controlador c "
    "JOIN plat.rede_subrede s ON s.id = c.subrede_id "
    "JOIN plat.rede_tier t ON t.id = c.tier_id "
    "LEFT JOIN plat.rede_tipo tp ON tp.id = c.tipo_id "
    "LEFT JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
)


def _controlador_json(r: dict) -> dict:
    return {
        "id": str(r["id"]), "nome": r["nome"], "papel": r["papel"], "origem": r["origem"],
        "subrede_id": str(r["subrede_id"]), "subrede": r["subrede"],
        "tier": r["tier"], "tier_nome": r["tier_nome"], "tier_tipo": r["tier_tipo"],
        "tier_ordem": r["tier_ordem"],
        "feicao_id": str(r["feicao_id"]) if r["feicao_id"] else None,
        "terminal": r["terminal_num"], "tipo_id": str(r["tipo_id"]) if r["tipo_id"] else None,
        "grupo": r["grupo"], "tipo_chave": r["tipo_chave"], "tipo_nome": r["tipo_nome"],
        "no_id": str(r["no_id"]) if r["no_id"] else None,
        "lon": r["lon"], "lat": r["lat"],
    }


def listar_controladores(cur, rede_id: str, limite: int) -> list[dict]:
    cur.execute(_SQL_CONTROLADOR + "WHERE c.rede_id = %s::uuid ORDER BY t.ordem, c.nome LIMIT %s",
                (rede_id, limite))
    return [_controlador_json(r) for r in cur.fetchall()]


def ver_controlador(cur, rede_id: str, controlador_id: str) -> dict:
    cur.execute(_SQL_CONTROLADOR + "WHERE c.rede_id = %s::uuid AND c.id = %s::uuid", (rede_id, controlador_id))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "controlador_inexistente", "este controlador não existe nesta rede")
    return _controlador_json(r)


def listar_subredes(cur, rede_id: str, limite: int, tier: str | None = None) -> list[dict]:
    """As subredes da rede: tier, controladores, estado (limpa/suja) e resumo da última atualização.

    O estado gravado vira `suja` também quando há área suja aberta na rede (edição depois da última
    construção da topologia): a subrede pode estar limpa no registro e obsoleta no chão."""
    cur.execute("SELECT count(*) AS n FROM plat.rede_topo_area_suja WHERE rede_id = %s::uuid", (rede_id,))
    areas_sujas = cur.fetchone()["n"]
    cur.execute(
        "SELECT s.id, s.nome, s.estado, s.resumo, s.atualizado_em, s.criado_em, "
        "       t.codigo AS tier, t.nome AS tier_nome, t.tipo AS tier_tipo, t.ordem AS tier_ordem "
        "FROM plat.rede_subrede s JOIN plat.rede_tier t ON t.id = s.tier_id "
        "WHERE s.rede_id = %s::uuid AND (%s::text IS NULL OR t.codigo = %s) "
        "ORDER BY t.ordem, s.nome LIMIT %s",
        (rede_id, tier, tier, limite),
    )
    subredes = [dict(r) for r in cur.fetchall()]
    if not subredes:
        return []
    cur.execute(
        _SQL_CONTROLADOR + "WHERE c.rede_id = %s::uuid AND c.subrede_id = ANY(%s::uuid[]) ORDER BY c.nome",
        (rede_id, [s["id"] for s in subredes]),
    )
    por_subrede: dict = {}
    for r in cur.fetchall():
        por_subrede.setdefault(str(r["subrede_id"]), []).append(_controlador_json(r))
    saida = []
    for s in subredes:
        estado = "suja" if (s["estado"] == "suja" or areas_sujas) else "limpa"
        saida.append({
            "id": str(s["id"]), "nome": s["nome"], "tier": s["tier"], "tier_nome": s["tier_nome"],
            "tier_tipo": s["tier_tipo"], "tier_ordem": s["tier_ordem"], "estado": estado,
            "estado_gravado": s["estado"], "areas_sujas_abertas": areas_sujas,
            "resumo": s["resumo"], "atualizado_em": s["atualizado_em"], "criado_em": s["criado_em"],
            "controladores": por_subrede.get(str(s["id"]), []),
        })
    return saida


def listar_tiers(cur, rede_id: str) -> list[dict]:
    """Os tiers da rede, na ordem da hierarquia, com o domínio, o tipo e quantas subredes cada um tem."""
    cur.execute(
        "SELECT t.id, t.codigo, t.nome, t.ordem, t.tipo, d.codigo AS dominio, d.nome AS dominio_nome, "
        "       (SELECT count(*) FROM plat.rede_subrede s WHERE s.tier_id = t.id) AS subredes, "
        "       (SELECT count(*) FROM plat.rede_controlador c WHERE c.tier_id = t.id) AS controladores "
        "FROM plat.rede_tier t JOIN plat.rede_dominio d ON d.id = t.dominio_id "
        "WHERE t.rede_id = %s::uuid ORDER BY d.ordem, t.ordem",
        (rede_id,),
    )
    return [{"id": str(r["id"]), "codigo": r["codigo"], "nome": r["nome"], "ordem": r["ordem"],
             "tipo": r["tipo"], "dominio": r["dominio"], "dominio_nome": r["dominio_nome"],
             "subredes": r["subredes"], "controladores": r["controladores"]} for r in cur.fetchall()]


# --- ciclo de vida: atualizar a subrede ----------------------------------------------------------------

def atualizar(cur, tenant_id: int, rede_id: str, subrede_id: str) -> dict:
    """Refaz o traçado da subrede a partir dos controladores dela e grava o resumo; a subrede volta a `limpa`.

    É o `Update Subnetwork` da paridade (subnetwork-life-cycle.htm): o traçado é o de tipo `subrede`, que para
    em qualquer ativo de transformação (fronteira entre dois tiers)."""
    cur.execute(
        "SELECT s.id, s.nome, t.codigo AS tier FROM plat.rede_subrede s JOIN plat.rede_tier t ON t.id = s.tier_id "
        "WHERE s.rede_id = %s::uuid AND s.id = %s::uuid",
        (rede_id, subrede_id),
    )
    s = cur.fetchone()
    if s is None:
        raise ErroAPI(404, "subrede_inexistente", "esta subrede não existe nesta rede")
    controladores = [c for c in listar_controladores(cur, rede_id, 1000) if c["subrede_id"] == str(subrede_id)]
    if not controladores:
        raise ErroAPI(409, "subrede_sem_controlador", "esta subrede não tem controlador para partir")
    sem_no = [c["nome"] for c in controladores if c["no_id"] is None]
    if sem_no:
        raise ErroAPI(
            409, "controlador_sem_no",
            "o(s) controlador(es) " + ", ".join(sem_no) + " não têm nó na topologia atual: reconstrua a "
            "topologia (POST .../topologia/habilitar) antes de atualizar a subrede",
        )

    inicio = time.perf_counter()
    partidas = [{"feicao_id": c["feicao_id"], "terminal": c["terminal"]} if c["feicao_id"]
                else {"lon": c["lon"], "lat": c["lat"]} for c in controladores]
    resultado = tracado.tracar(cur, tenant_id, rede_id, "subrede", partidas, [])
    resumo = {
        "elementos": resultado["contagem"],
        "nos_alcancados": resultado["nos_alcancados"],
        "controladores": len(controladores),
        "duracao_ms": int((time.perf_counter() - inicio) * 1000),
    }
    cur.execute(
        "UPDATE plat.rede_subrede SET estado = 'limpa', resumo = %s::jsonb, atualizado_em = now() "
        "WHERE id = %s::uuid RETURNING atualizado_em",
        (json.dumps(resumo), subrede_id),
    )
    atualizado_em = cur.fetchone()["atualizado_em"]
    return {"subrede_id": str(subrede_id), "nome": s["nome"], "tier": s["tier"], "estado": "limpa",
            "resumo": resumo, "atualizado_em": atualizado_em, "geometria": resultado["geometria"]}


# --- marcação a partir da importação (BDGD Módulo 10) ---------------------------------------------------

GRUPO_TRECHO_MT = "trecho_de_media_tensao"
GRUPO_TRECHO_BT = "trecho_de_baixa_tensao"
GRUPO_TRAFO = "transformador_de_distribuicao"
GRUPO_CHAVE_MT = "chave_de_media_tensao"


def _tier_do_grupo(cur, rede_id: str, grupo_codigo: str) -> dict:
    """O tier em que vive o grupo de ativo `grupo_codigo` (o menor `ordem`, quando o grupo tem tipos em
    tiers diferentes). É assim que a marcação descobre "o tier de média tensão" sem depender do NOME do
    tier: o pacote é que diz onde cada grupo vive."""
    cur.execute(
        "SELECT t.id, t.codigo, t.nome, t.ordem, t.tipo FROM plat.rede_tipo tp "
        "JOIN plat.rede_grupo g ON g.id = tp.grupo_id JOIN plat.rede_tier t ON t.id = tp.tier_id "
        "WHERE tp.rede_id = %s::uuid AND g.codigo = %s ORDER BY t.ordem LIMIT 1",
        (rede_id, grupo_codigo),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(409, "grupo_ausente_no_pacote",
                      f"o pacote desta rede não tem o grupo de ativo '{grupo_codigo}'")
    return dict(r)


def _terminal_de_jusante(terminais: list | None) -> int | None:
    """O terminal a jusante (`montante=false`) do dispositivo: é ele que alimenta a subrede do tier de baixo
    (o lado de baixa do transformador). Com um terminal só, é esse mesmo."""
    if not terminais:
        return None
    jusante = [t["id"] for t in terminais if not t.get("montante")]
    return min(jusante) if jusante else min(t["id"] for t in terminais)


def _ja_controlado(cur, rede_id: str, feicao_id: str, terminal_num: int | None) -> bool:
    cur.execute(
        "SELECT 1 FROM plat.rede_controlador WHERE rede_id = %s::uuid AND feicao_id = %s::uuid "
        "AND coalesce(terminal_num, 0) = %s",
        (rede_id, feicao_id, terminal_num or 0),
    )
    return cur.fetchone() is not None


def _no_de_cabeca(cur, rede_id: str, ctmt: str, sub: str | None) -> dict | None:
    """Nó de cabeça do alimentador, usado só quando o arquivo NÃO traz o equipamento de saída da subestação.

    ⛔ É uma CONVENÇÃO declarada, não uma leitura do arquivo: os alimentadores de uma mesma subestação
    irradiam dela, então o centróide dos trechos de média tensão da subestação (`sub`) é um PROXY da posição
    da subestação, e a cabeça de cada alimentador é o nó do subgrafo daquele alimentador mais próximo desse
    proxy. O controlador nascido daqui fica gravado com `origem='no_de_cabeca'` justamente para que ninguém
    o confunda com um terminal lido do arquivo. Sem `sub` no arquivo, o proxy é o centróide do próprio
    alimentador — mais fraco ainda, e igualmente marcado."""
    cur.execute(
        "WITH mt AS ("
        "  SELECT f.id, f.geom, f.atributos FROM plat.rede_feicao_linha f "
        "  JOIN plat.rede_tipo tp ON tp.id = f.tipo_id JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "  WHERE f.rede_id = %(rede)s::uuid AND g.codigo = %(grupo)s), "
        "proxy AS (SELECT ST_Centroid(ST_Collect(geom)) AS g FROM mt "
        "          WHERE (%(sub)s::text IS NOT NULL AND atributos->>'sub' = %(sub)s) "
        "             OR (%(sub)s::text IS NULL AND atributos->>'ctmt' = %(ctmt)s)), "
        "nos AS (SELECT DISTINCT n.id, n.geom FROM plat.rede_topo_aresta a "
        "        JOIN mt ON mt.id = a.origem_id "
        "        JOIN plat.rede_topo_no n ON n.id IN (a.no_origem_id, a.no_destino_id) "
        "        WHERE a.rede_id = %(rede)s::uuid AND mt.atributos->>'ctmt' = %(ctmt)s) "
        "SELECT nos.id, ST_X(nos.geom) AS lon, ST_Y(nos.geom) AS lat "
        "FROM nos, proxy WHERE proxy.g IS NOT NULL ORDER BY nos.geom <-> proxy.g, nos.id LIMIT 1",
        {"rede": rede_id, "grupo": GRUPO_TRECHO_MT, "ctmt": ctmt, "sub": sub},
    )
    r = cur.fetchone()
    return dict(r) if r else None


def _inserir_cabeca(cur, tenant_id: int, rede_id: str, tier_id: str, subrede_id: str, nome: str,
                    lon: float, lat: float, usuario_id: int | None) -> str:
    cur.execute(
        "INSERT INTO plat.rede_controlador(tenant_id, rede_id, subrede_id, tier_id, nome, origem, papel, "
        "geom, criado_por) VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, 'no_de_cabeca', 'fonte', "
        "ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s) RETURNING id",
        (tenant_id, rede_id, subrede_id, tier_id, nome, lon, lat, usuario_id),
    )
    return str(cur.fetchone()["id"])


def marcar_da_importacao(cur, tenant_id: int, rede_id: str, usuario_id: int | None) -> dict:
    """Marca os controladores que a importação da BDGD Módulo 10 permite deduzir, sem inventar nada:

      * UM controlador por ALIMENTADOR (CTMT), no tier da média tensão. Preferência absoluta pelo TERMINAL do
        dispositivo de saída da subestação (disjuntor/chave com a categoria `controlador`, mesmo CTMT); só
        quando o arquivo não traz esse equipamento é que entra o nó de cabeça (`_no_de_cabeca`, convenção
        declarada, gravada como `origem='no_de_cabeca'`).
      * UM controlador por TRANSFORMADOR DE DISTRIBUIÇÃO (UNTRMT), no tier da baixa tensão, no terminal de
        jusante (o lado de baixa) — é ele que dá origem à subrede de BT.

    Idempotente: rodar de novo não duplica (o terminal já marcado é contado em `ja_marcados`). Exige a
    topologia construída, porque o nó de cabeça só existe depois dela."""
    cur.execute("SELECT 1 FROM plat.rede_topo_resumo WHERE rede_id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(409, "topologia_inexistente", "esta rede ainda não teve a topologia habilitada")

    tier_mt = _tier_do_grupo(cur, rede_id, GRUPO_TRECHO_MT)
    tier_bt = _tier_do_grupo(cur, rede_id, GRUPO_TRECHO_BT)
    contagem = {"tier_media_tensao": tier_mt["codigo"], "tier_baixa_tensao": tier_bt["codigo"],
                "alimentadores": 0, "alimentadores_por_dispositivo": 0, "alimentadores_por_no_de_cabeca": 0,
                "alimentadores_sem_no": 0, "transformadores": 0, "transformadores_marcados": 0,
                "ja_marcados": 0}

    cur.execute(
        "SELECT f.atributos->>'ctmt' AS ctmt, max(f.atributos->>'sub') AS sub, count(*) AS trechos "
        "FROM plat.rede_feicao_linha f JOIN plat.rede_tipo tp ON tp.id = f.tipo_id "
        "JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE f.rede_id = %s::uuid AND g.codigo = %s AND f.atributos->>'ctmt' IS NOT NULL "
        "GROUP BY 1 ORDER BY 1",
        (rede_id, GRUPO_TRECHO_MT),
    )
    alimentadores = [dict(r) for r in cur.fetchall()]
    contagem["alimentadores"] = len(alimentadores)

    for al in alimentadores:
        ctmt = al["ctmt"]
        cur.execute(
            "SELECT f.id, tc.terminais FROM plat.rede_feicao_ponto f "
            "JOIN plat.rede_tipo tp ON tp.id = f.tipo_id JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
            "LEFT JOIN plat.rede_terminal_config tc ON tc.id = tp.terminal_id "
            "WHERE f.rede_id = %s::uuid AND f.atributos->>'ctmt' = %s AND tp.tier_id = %s::uuid "
            "AND EXISTS (SELECT 1 FROM plat.rede_tipo_categoria tcat "
            "            JOIN plat.rede_categoria c ON c.id = tcat.categoria_id "
            "            WHERE tcat.tipo_id = tp.id AND c.codigo = %s) "
            "ORDER BY (g.codigo = %s) DESC, f.id LIMIT 1",
            (rede_id, ctmt, str(tier_mt["id"]), CATEGORIA_CONTROLADOR, GRUPO_CHAVE_MT),
        )
        disp = cur.fetchone()
        if disp is not None:
            terminal = _terminal_de_jusante(disp["terminais"])
            if _ja_controlado(cur, rede_id, str(disp["id"]), terminal):
                contagem["ja_marcados"] += 1
                continue
            definir(cur, tenant_id, rede_id, feicao_id=str(disp["id"]), terminal=terminal, subrede=ctmt,
                    tier_codigo=tier_mt["codigo"], papel="fonte", nome=ctmt, usuario_id=usuario_id)
            contagem["alimentadores_por_dispositivo"] += 1
            continue
        cabeca = _no_de_cabeca(cur, rede_id, ctmt, al["sub"])
        if cabeca is None:
            contagem["alimentadores_sem_no"] += 1
            continue
        cur.execute(
            "SELECT 1 FROM plat.rede_controlador WHERE rede_id = %s::uuid AND tier_id = %s::uuid AND nome = %s",
            (rede_id, str(tier_mt["id"]), ctmt),
        )
        if cur.fetchone() is not None:
            contagem["ja_marcados"] += 1
            continue
        sub_id = _subrede_id(cur, tenant_id, rede_id, str(tier_mt["id"]), ctmt)
        _inserir_cabeca(cur, tenant_id, rede_id, str(tier_mt["id"]), sub_id, ctmt,
                        cabeca["lon"], cabeca["lat"], usuario_id)
        _sujar(cur, sub_id)
        contagem["alimentadores_por_no_de_cabeca"] += 1

    cur.execute(
        "SELECT f.id, f.atributos->>'cod_id' AS cod_id, tc.terminais FROM plat.rede_feicao_ponto f "
        "JOIN plat.rede_tipo tp ON tp.id = f.tipo_id JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "LEFT JOIN plat.rede_terminal_config tc ON tc.id = tp.terminal_id "
        "WHERE f.rede_id = %s::uuid AND g.codigo = %s "
        "AND EXISTS (SELECT 1 FROM plat.rede_tipo_categoria tcat "
        "            JOIN plat.rede_categoria c ON c.id = tcat.categoria_id "
        "            WHERE tcat.tipo_id = tp.id AND c.codigo = %s) ORDER BY f.id",
        (rede_id, GRUPO_TRAFO, CATEGORIA_CONTROLADOR),
    )
    trafos = [dict(r) for r in cur.fetchall()]
    contagem["transformadores"] = len(trafos)
    for tr in trafos:
        terminal = _terminal_de_jusante(tr["terminais"])
        if _ja_controlado(cur, rede_id, str(tr["id"]), terminal):
            contagem["ja_marcados"] += 1
            continue
        nome = tr["cod_id"] or str(tr["id"])
        definir(cur, tenant_id, rede_id, feicao_id=str(tr["id"]), terminal=terminal, subrede=nome,
                tier_codigo=tier_bt["codigo"], papel="fonte", nome=nome, usuario_id=usuario_id)
        contagem["transformadores_marcados"] += 1
    return contagem
