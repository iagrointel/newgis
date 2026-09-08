"""Atualizar e exportar subrede (item L4-04-b-atualizar-e-exportar-subrede).

O item irmão L4-04-a criou o CONTROLADOR, o TIER e o registro da subrede (`plat.rede_subrede`, com estado
limpa/suja). Ele parava no traçado: contava elementos e gravava o resumo. Aqui a atualização passa a fazer o
que `Update Subnetwork` faz na fonte (update-subnetworks.htm, update-subnetwork.htm):

  1. traça a subrede a partir dos controladores dela (o MESMO motor de `tracado.tracar`, tipo `subrede`);
  2. grava o nome da subrede em cada elemento alcançado (`plat.rede_subrede_elemento` — o atributo de rede;
     nunca dentro de `rede_feicao_*.atributos`, que é o dado como veio do arquivo);
  3. propaga os atributos declarados como PROPAGADORES do tier, lendo o valor no dispositivo controlador;
  4. gera a linha agregada da subrede (`SubnetLine` da fonte: uma linha por subrede) e o comprimento;
  5. grava o resumo e devolve a subrede `limpa`.

INCREMENTAL POR ÁREA SUJA: a atualização em lote (`atualizar_todas`) não refaz a rede inteira. `marcar_sujas`
cruza as áreas sujas abertas (`plat.rede_topo_area_suja`, gravadas por toda edição desde o item L4-01-b) com
os elementos gravados na última atualização e marca `suja` SÓ a subrede que a edição tocou. Mover uma chave de
fronteira entre dois alimentadores produz uma área suja que cobre a posição velha e a nova: as duas subredes
ficam sujas, e só elas são atualizadas.

EXPORTAR (export-subnetworks.htm, exportsubnetwork-utility-network-server): um JSON com elementos,
conectividade, controladores e resumo — o formato que um sistema de operação consome. O esquema está em
`app/rede_utilidades/esquema_exportacao.py` e a saída é validada contra ele antes de sair (o esquema é
contrato, não documentação)."""

import json
import time
from datetime import datetime, timezone

from jsonschema import Draft202012Validator

from app.erros import ErroAPI
from app.rede_utilidades import controladores, esquema_exportacao, opendss, tracado

_VALIDADOR = Draft202012Validator(esquema_exportacao.ESQUEMA)


def melhor_erro(erros) -> str | None:
    """A primeira falha de esquema, com o caminho — mensagem única em vez de uma lista que ninguém lê."""
    for erro in sorted(erros, key=lambda e: list(e.absolute_path)):
        caminho = ".".join(str(p) for p in erro.absolute_path) or "(raiz)"
        return f"{caminho}: {erro.message}"
    return None


# --- leitura da subrede -------------------------------------------------------------------------------

_SQL_SUBREDE = (
    "SELECT s.id, s.nome, s.estado, s.resumo, s.atualizado_em, s.criado_em, s.comprimento_m, "
    "       t.id AS tier_id, t.codigo AS tier, t.nome AS tier_nome, t.tipo AS tier_tipo, t.ordem AS tier_ordem, "
    "       t.propagadores "
    "FROM plat.rede_subrede s JOIN plat.rede_tier t ON t.id = s.tier_id "
)


def _subrede(cur, rede_id: str, subrede_id: str) -> dict:
    cur.execute(_SQL_SUBREDE + "WHERE s.rede_id = %s::uuid AND s.id = %s::uuid", (rede_id, subrede_id))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "subrede_inexistente", "esta subrede não existe nesta rede")
    return dict(r)


def por_nome(cur, rede_id: str, nome: str, tier: str | None = None) -> dict:
    """A subrede pelo NOME (é assim que a exportação a endereça: `.../subrede/{nome}/exportar`). O nome é
    único dentro do tier, não na rede inteira — sem `tier`, nome repetido em dois tiers é ambíguo e recusado
    em vez de devolver um dos dois em silêncio."""
    cur.execute(
        _SQL_SUBREDE + "WHERE s.rede_id = %s::uuid AND s.nome = %s AND (%s::text IS NULL OR t.codigo = %s) "
        "ORDER BY t.ordem",
        (rede_id, nome, tier, tier),
    )
    linhas = cur.fetchall()
    if not linhas:
        raise ErroAPI(404, "subrede_inexistente", "esta rede não tem subrede com esse nome")
    if len(linhas) > 1:
        tiers = ", ".join(sorted(r["tier"] for r in linhas))
        raise ErroAPI(422, "subrede_ambigua",
                      f"há subrede com esse nome em mais de um tier ({tiers}): informe 'tier'")
    return dict(linhas[0])


# --- propagadores do tier -----------------------------------------------------------------------------

def definir_propagadores(cur, rede_id: str, tier_codigo: str, codigos: list[str]) -> dict:
    """Declara quais atributos o tier propaga do controlador para os elementos da subrede. O código tem de
    existir em `plat.rede_atributo` da rede (é o vocabulário do pacote), senão a propagação escreveria uma
    chave que ninguém sabe ler."""
    cur.execute(
        "SELECT id, codigo FROM plat.rede_tier WHERE rede_id = %s::uuid AND codigo = %s",
        (rede_id, tier_codigo),
    )
    t = cur.fetchone()
    if t is None:
        raise ErroAPI(404, "tier_inexistente", f"a rede não tem o tier '{tier_codigo}'")
    limpos = []
    for c in codigos:
        c = (c or "").strip()
        if c and c not in limpos:
            limpos.append(c)
    if limpos:
        cur.execute(
            "SELECT DISTINCT codigo FROM plat.rede_atributo WHERE rede_id = %s::uuid AND codigo = ANY(%s)",
            (rede_id, limpos),
        )
        conhecidos = {r["codigo"] for r in cur.fetchall()}
        faltando = [c for c in limpos if c not in conhecidos]
        if faltando:
            raise ErroAPI(422, "atributo_desconhecido",
                          "o pacote desta rede não declara o(s) atributo(s) " + ", ".join(faltando))
    cur.execute("UPDATE plat.rede_tier SET propagadores = %s::jsonb WHERE id = %s::uuid",
                (json.dumps(limpos), str(t["id"])))
    return {"tier": t["codigo"], "propagadores": limpos}


def _valores_propagados(cur, rede_id: str, propagadores: list, controladores_da: list[dict]) -> tuple[dict, list]:
    """Os valores que a subrede propaga: lidos nos ATRIBUTOS DO DISPOSITIVO controlador. Controlador ancorado
    em nó de cabeça (sem feição) não tem de onde propagar. Dois controladores com valores diferentes para o
    mesmo atributo não são fundidos: o atributo fica de fora e é devolvido como divergência."""
    if not propagadores:
        return {}, []
    ids = [c["feicao_id"] for c in controladores_da if c["feicao_id"]]
    if not ids:
        return {}, []
    cur.execute(
        "SELECT id, atributos FROM plat.rede_feicao_ponto WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[])",
        (rede_id, ids),
    )
    vistos: dict = {}
    for linha in cur.fetchall():
        atributos = linha["atributos"] or {}
        for codigo in propagadores:
            if codigo in atributos and atributos[codigo] is not None:
                vistos.setdefault(codigo, []).append(atributos[codigo])
    valores, divergentes = {}, []
    for codigo, lista in vistos.items():
        unicos = {json.dumps(v, sort_keys=True) for v in lista}
        if len(unicos) == 1:
            valores[codigo] = lista[0]
        else:
            divergentes.append(codigo)
    return valores, sorted(divergentes)


# --- atualizar uma subrede ----------------------------------------------------------------------------

def _gravar_elementos(cur, tenant_id: int, rede_id: str, s: dict, elementos: list[dict],
                      propagados: dict) -> None:
    """Reescreve a associação elemento → subrede desta subrede: apaga a de antes e grava a de agora. Um
    elemento que saiu da subrede (chave de fronteira movida) perde a linha; é isso que faz a conferência
    contra o arquivo enxergar a mudança em vez de acumular membros velhos."""
    cur.execute("DELETE FROM plat.rede_subrede_elemento WHERE subrede_id = %s::uuid", (str(s["id"]),))
    if not elementos:
        return
    valores, gabarito = [], []
    propagados_json = json.dumps(propagados)
    for e in elementos:
        gabarito.append("(%s, %s::uuid, %s::uuid, %s::uuid, %s, %s::uuid, %s, %s, %s::uuid, %s::jsonb)")
        valores += [tenant_id, rede_id, str(s["id"]), str(s["tier_id"]), s["nome"], e["feicao_id"],
                    e["terminal"], "ponto" if e["terminal"] is not None else "linha",
                    e["tipo_id"], propagados_json]
    cur.execute(
        "INSERT INTO plat.rede_subrede_elemento(tenant_id, rede_id, subrede_id, tier_id, subrede_nome, "
        "feicao_id, terminal_num, geometria, tipo_id, propagados) VALUES " + ", ".join(gabarito),
        valores,
    )


def _linha_agregada(cur, rede_id: str, subrede_id: str) -> dict:
    """A `SubnetLine`: uma linha por subrede, a união dos trechos que a subrede contém, costurada por
    `ST_LineMerge`. Comprimento em metros de verdade (`geography`)."""
    cur.execute(
        "WITH partes AS ("
        "  SELECT l.geom FROM plat.rede_subrede_elemento e "
        "  JOIN plat.rede_feicao_linha l ON l.id = e.feicao_id "
        "  WHERE e.subrede_id = %s::uuid AND e.geometria = 'linha' AND l.rede_id = %s::uuid), "
        "juntas AS (SELECT ST_Multi(ST_LineMerge(ST_Collect(geom))) AS g FROM partes) "
        "UPDATE plat.rede_subrede SET linha = juntas.g, "
        "  comprimento_m = CASE WHEN juntas.g IS NULL THEN NULL ELSE ST_Length(juntas.g::geography) END "
        "FROM juntas WHERE plat.rede_subrede.id = %s::uuid "
        "RETURNING comprimento_m, ST_AsGeoJSON(linha) AS geojson, "
        "          CASE WHEN linha IS NULL THEN 0 ELSE ST_NumGeometries(linha) END AS partes",
        (subrede_id, rede_id, subrede_id),
    )
    r = cur.fetchone()
    return {"comprimento_m": r["comprimento_m"],
            "linha": json.loads(r["geojson"]) if r["geojson"] else None,
            "partes": r["partes"]}


def atualizar(cur, tenant_id: int, rede_id: str, subrede_id: str) -> dict:
    """`Update Subnetwork`: refaz o traçado da subrede a partir dos controladores dela, grava o nome em cada
    elemento, propaga os atributos do tier, gera a linha agregada e devolve a subrede `limpa`."""
    s = _subrede(cur, rede_id, subrede_id)
    dela = [c for c in controladores.listar_controladores(cur, rede_id, 1000)
            if c["subrede_id"] == str(subrede_id)]
    if not dela:
        raise ErroAPI(409, "subrede_sem_controlador", "esta subrede não tem controlador para partir")
    sem_no = [c["nome"] for c in dela if c["no_id"] is None]
    if sem_no:
        raise ErroAPI(
            409, "controlador_sem_no",
            "o(s) controlador(es) " + ", ".join(sem_no) + " não têm nó na topologia atual: reconstrua a "
            "topologia (POST .../topologia/habilitar) antes de atualizar a subrede",
        )

    inicio = time.perf_counter()
    partidas = [{"feicao_id": c["feicao_id"], "terminal": c["terminal"]} if c["feicao_id"]
                else {"lon": c["lon"], "lat": c["lat"]} for c in dela]
    resultado = tracado.tracar(cur, tenant_id, rede_id, "subrede", partidas, [])
    propagados, divergentes = _valores_propagados(cur, rede_id, list(s["propagadores"] or []), dela)
    _gravar_elementos(cur, tenant_id, rede_id, s, resultado["elementos"], propagados)
    agregada = _linha_agregada(cur, rede_id, str(subrede_id))

    resumo = {
        "elementos": resultado["contagem"],
        "nos_alcancados": resultado["nos_alcancados"],
        "controladores": len(dela),
        "trechos": sum(1 for e in resultado["elementos"] if e["terminal"] is None),
        "terminais": sum(1 for e in resultado["elementos"] if e["terminal"] is not None),
        "comprimento_m": round(agregada["comprimento_m"], 3) if agregada["comprimento_m"] else 0.0,
        "partes_da_linha": agregada["partes"],
        "propagados": propagados,
        "propagadores_divergentes": divergentes,
        "duracao_ms": int((time.perf_counter() - inicio) * 1000),
    }
    cur.execute(
        "UPDATE plat.rede_subrede SET estado = 'limpa', resumo = %s::jsonb, atualizado_em = now() "
        "WHERE id = %s::uuid RETURNING atualizado_em",
        (json.dumps(resumo), str(subrede_id)),
    )
    atualizado_em = cur.fetchone()["atualizado_em"]
    return {"subrede_id": str(subrede_id), "nome": s["nome"], "tier": s["tier"], "estado": "limpa",
            "resumo": resumo, "atualizado_em": atualizado_em, "geometria": resultado["geometria"],
            "linha": agregada["linha"]}


# --- incremental: área suja → subrede suja --------------------------------------------------------------

def marcar_sujas(cur, rede_id: str, area_id: str | None = None) -> dict:
    """Cruza as áreas sujas abertas (ou só a área `area_id`, no instante da edição) com os elementos gravados
    na última atualização e marca `suja` só a subrede que a edição tocou. É a parte INCREMENTAL do item: sem
    isto, ou se atualiza tudo a cada edição, ou não se sabe o que atualizar.

    Uma subrede sem elemento gravado (nunca atualizada) já nasce `suja` e não depende deste cruzamento."""
    cur.execute(
        "SELECT count(*) AS n FROM plat.rede_topo_area_suja WHERE rede_id = %s::uuid "
        "AND (%s::uuid IS NULL OR id = %s::uuid)",
        (rede_id, area_id, area_id),
    )
    areas = cur.fetchone()["n"]
    if not areas:
        return {"areas_sujas": 0, "subredes_marcadas": 0, "nomes": []}
    cur.execute(
        "UPDATE plat.rede_subrede s SET estado = 'suja' "
        "WHERE s.rede_id = %(rede)s::uuid AND s.estado = 'limpa' AND EXISTS ("
        "  SELECT 1 FROM plat.rede_subrede_elemento e "
        "  LEFT JOIN plat.rede_feicao_ponto p ON p.id = e.feicao_id "
        "  LEFT JOIN plat.rede_feicao_linha l ON l.id = e.feicao_id "
        "  JOIN plat.rede_topo_area_suja a ON a.rede_id = %(rede)s::uuid "
        "     AND (%(area)s::uuid IS NULL OR a.id = %(area)s::uuid) "
        "     AND ST_Intersects(a.geom, coalesce(p.geom, l.geom)) "
        "  WHERE e.subrede_id = s.id) "
        "RETURNING s.nome",
        {"rede": rede_id, "area": area_id},
    )
    nomes = sorted(r["nome"] for r in cur.fetchall())
    return {"areas_sujas": areas, "subredes_marcadas": len(nomes), "nomes": nomes}


def atualizar_todas(cur, tenant_id: int, rede_id: str, *, todas: bool = False, tier: str | None = None,
                    progresso=None) -> dict:
    """Atualiza as subredes sujas da rede (ou todas, com `todas=True`), na ordem da hierarquia de tiers.

    Ordem por `tier.ordem` porque a subrede de baixa tensão nasce depois da de média: atualizar de cima para
    baixo deixa o resultado igual ao de rodar uma a uma na ordem natural da rede. `tier` restringe o lote a um
    tier — na fonte a atualização também é por tier/domínio, e numa distribuidora o tier de baixa tensão tem
    uma subrede por transformador (milhares), enquanto o de média tem uma por alimentador (dezenas)."""
    inicio = time.perf_counter()
    marcacao = marcar_sujas(cur, rede_id)
    cur.execute(
        _SQL_SUBREDE + "WHERE s.rede_id = %s::uuid AND (%s OR s.estado = 'suja') "
        "AND (%s::text IS NULL OR t.codigo = %s) ORDER BY t.ordem, s.nome",
        (rede_id, todas, tier, tier),
    )
    alvos = [dict(r) for r in cur.fetchall()]
    feitas, recusadas = [], []
    for i, s in enumerate(alvos):
        try:
            r = atualizar(cur, tenant_id, rede_id, str(s["id"]))
        except ErroAPI as e:
            # uma subrede sem controlador (ou com controlador sem nó) não pode travar o lote inteiro:
            # ela sai nomeada, com o código do erro, e continua suja.
            recusadas.append({"subrede": s["nome"], "tier": s["tier"], "erro": e.erro})
            continue
        feitas.append({"subrede": r["nome"], "tier": r["tier"], "elementos": r["resumo"]["elementos"],
                       "comprimento_m": r["resumo"]["comprimento_m"],
                       "duracao_ms": r["resumo"]["duracao_ms"]})
        if progresso is not None and alvos:
            progresso(int(100 * (i + 1) / len(alvos)), f"{i + 1}/{len(alvos)} subredes")
    return {
        "rede_id": rede_id, "tier": tier,
        "candidatas": len(alvos), "atualizadas": len(feitas), "recusadas": recusadas,
        "elementos": sum(f["elementos"] for f in feitas),
        "areas_sujas": marcacao["areas_sujas"], "sujas_por_area": marcacao["nomes"],
        "duracao_ms": int((time.perf_counter() - inicio) * 1000), "itens": feitas,
    }


# --- conferência contra o atributo do arquivo -----------------------------------------------------------

def conferir(cur, rede_id: str, atributo: str, grupo: str, tier: str | None = None,
             limite: int = 200) -> dict:
    """Compara o nome da subrede gravado em cada elemento com o valor de um atributo DO ARQUIVO no mesmo
    elemento (na BDGD, o `ctmt` do trecho de média tensão). Não é uma verificação do traçado contra ele
    mesmo: o nome vem do traçado, o atributo vem do arquivo, e a diferença é candidata a erro de cadastro —
    nunca uma acusação. Elemento sem o atributo preenchido fica em `sem_atributo` e não conta como diferença.
    """
    cur.execute(
        "SELECT l.id, l.atributos->>%(atributo)s AS valor, e.subrede_nome "
        "FROM plat.rede_feicao_linha l "
        "JOIN plat.rede_tipo tp ON tp.id = l.tipo_id JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "LEFT JOIN plat.rede_subrede_elemento e ON e.feicao_id = l.id "
        "  AND e.rede_id = l.rede_id AND (%(tier)s::text IS NULL OR e.tier_id IN ("
        "     SELECT id FROM plat.rede_tier WHERE rede_id = l.rede_id AND codigo = %(tier)s)) "
        "WHERE l.rede_id = %(rede)s::uuid AND g.codigo = %(grupo)s",
        {"rede": rede_id, "grupo": grupo, "atributo": atributo, "tier": tier},
    )
    total = iguais = 0
    sem_atributo = sem_subrede = 0
    diferencas = []
    for r in cur.fetchall():
        total += 1
        if r["valor"] is None:
            sem_atributo += 1
            continue
        if r["subrede_nome"] is None:
            sem_subrede += 1
            if len(diferencas) < limite:
                diferencas.append({"feicao_id": str(r["id"]), "atributo": r["valor"], "subrede": None,
                                   "candidata_a": "trecho fora de toda subrede atualizada"})
            continue
        if r["subrede_nome"] == r["valor"]:
            iguais += 1
        elif len(diferencas) < limite:
            diferencas.append({"feicao_id": str(r["id"]), "atributo": r["valor"],
                               "subrede": r["subrede_nome"],
                               "candidata_a": "nome da subrede calculado diferente do atributo do arquivo"})
    comparaveis = total - sem_atributo
    return {
        "atributo": atributo, "grupo": grupo, "tier": tier,
        "total": total, "comparaveis": comparaveis, "iguais": iguais,
        "sem_atributo": sem_atributo, "sem_subrede": sem_subrede,
        "diferentes": comparaveis - iguais,
        "concordancia": round(iguais / comparaveis, 6) if comparaveis else None,
        "diferencas": diferencas, "diferencas_truncadas": (comparaveis - iguais) > len(diferencas),
    }


# --- exportar -------------------------------------------------------------------------------------------

def exportar(cur, rede_id: str, nome: str, tier: str | None = None) -> dict:
    """`Export Subnetwork`: elementos, conectividade, controladores e resumo da subrede, em JSON validado
    contra `esquema_exportacao.ESQUEMA`.

    Exporta o que a ÚLTIMA atualização gravou (`plat.rede_subrede_elemento`), não um traçado novo: é a mesma
    escolha da fonte, onde a exportação lê a subrede já atualizada — e é o que permite comparar exportação e
    traçado elemento a elemento. Subrede suja é exportada assim mesmo, com `estado: "suja"` bem visível;
    subrede que nunca foi atualizada não tem o que exportar e é recusada.
    """
    s = por_nome(cur, rede_id, nome, tier)
    if s["atualizado_em"] is None:
        raise ErroAPI(409, "subrede_nunca_atualizada",
                      "esta subrede ainda não foi atualizada: não há elementos gravados para exportar")
    cur.execute("SELECT id, nome, disciplina FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    rede = cur.fetchone()

    cur.execute(
        "SELECT e.feicao_id, e.terminal_num, e.geometria, e.propagados, g.codigo AS grupo, "
        "       tp.chave AS tipo_chave "
        "FROM plat.rede_subrede_elemento e "
        "LEFT JOIN plat.rede_tipo tp ON tp.id = e.tipo_id "
        "LEFT JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE e.subrede_id = %s::uuid ORDER BY e.geometria, e.feicao_id, e.terminal_num",
        (str(s["id"]),),
    )
    elementos = [{"feicao_id": str(r["feicao_id"]), "terminal": r["terminal_num"],
                  "geometria": r["geometria"], "grupo": r["grupo"], "tipo_chave": r["tipo_chave"],
                  "propagados": r["propagados"] or {}} for r in cur.fetchall()]

    # conectividade: as arestas REAIS da topologia cujo trecho é membro da subrede. A ligação interna de um
    # dispositivo multi-terminal (o "caminho válido" do pacote) não é aresta gravada — é montada por chamada
    # dentro do traçado (tracado._montar_sql_arestas) — e por isso não aparece aqui; quem consome vê os dois
    # terminais do dispositivo como elementos e sabe, pelo pacote, que eles se ligam.
    cur.execute(
        "SELECT a.origem_id, a.no_origem_id, a.no_destino_id FROM plat.rede_topo_aresta a "
        "WHERE a.rede_id = %s::uuid AND a.no_origem_id IS NOT NULL AND a.no_destino_id IS NOT NULL "
        "AND a.origem_id IN (SELECT feicao_id FROM plat.rede_subrede_elemento "
        "                    WHERE subrede_id = %s::uuid AND geometria = 'linha') "
        "ORDER BY a.origem_id",
        (rede_id, str(s["id"])),
    )
    conectividade = [{"feicao_id": str(r["origem_id"]) if r["origem_id"] else None,
                      "de": str(r["no_origem_id"]), "para": str(r["no_destino_id"])}
                     for r in cur.fetchall()]

    cur.execute("SELECT ST_AsGeoJSON(linha) AS geojson FROM plat.rede_subrede WHERE id = %s::uuid",
                (str(s["id"]),))
    geojson = cur.fetchone()["geojson"]

    dela = [c for c in controladores.listar_controladores(cur, rede_id, 1000)
            if c["subrede_id"] == str(s["id"])]
    resumo = dict(s["resumo"] or {})
    saida = {
        "esquema": esquema_exportacao.ESQUEMA_ID,
        "esquema_versao": esquema_exportacao.ESQUEMA_VERSAO,
        "exportado_em": datetime.now(timezone.utc).isoformat(),
        "rede": {"id": str(rede["id"]), "nome": rede["nome"], "disciplina": rede["disciplina"]},
        "subrede": {
            "id": str(s["id"]), "nome": s["nome"], "tier": s["tier"], "tier_nome": s["tier_nome"],
            "tier_tipo": s["tier_tipo"], "estado": s["estado"],
            "atualizado_em": s["atualizado_em"].isoformat() if s["atualizado_em"] else None,
            "comprimento_m": s["comprimento_m"],
            "propagados": resumo.get("propagados") or {},
            "linha": json.loads(geojson) if geojson else None,
        },
        "controladores": [{"id": c["id"], "nome": c["nome"], "papel": c["papel"], "origem": c["origem"],
                           "feicao_id": c["feicao_id"], "terminal": c["terminal"], "grupo": c["grupo"],
                           "tipo_chave": c["tipo_chave"], "lon": c["lon"], "lat": c["lat"]} for c in dela],
        "elementos": elementos,
        "conectividade": conectividade,
        "resumo": resumo,
    }
    erro = melhor_erro(_VALIDADOR.iter_errors(saida))
    if erro is not None:
        # esquema é contrato: saída fora dele é defeito da plataforma, não pedido inválido do chamador.
        raise ErroAPI(500, "exportacao_fora_do_esquema",
                      "a exportação não bate com o esquema declarado: " + erro)
    return saida


def exportar_dss(cur, rede_id: str, nome: str, tier: str | None = None, ano: int | None = None,
                 jusante: bool = False) -> dict:
    """`Export Subnetwork` no formato do OpenDSS (item L4-05-a-exportar-opendss): a pasta `.dss` da subrede.

    Devolve `{"arquivos": {nome_do_arquivo: texto}, "resumo": {...}}`. O resumo traz a conferência que o
    portão do item exige — barras esperadas × nós da subrede, linhas esperadas × trechos — junto com os
    avisos e o que o conversor ignorou. Quem chama embrulha em zip.

    A recusa da subrede nunca atualizada é a MESMA de `exportar`: sem elemento gravado não há o que
    converter, e devolver um circuito vazio seria pior que recusar."""
    s = por_nome(cur, rede_id, nome, tier)
    if s["atualizado_em"] is None:
        raise ErroAPI(409, "subrede_nunca_atualizada",
                      "esta subrede ainda não foi atualizada: não há elementos gravados para exportar")
    dela = [c for c in controladores.listar_controladores(cur, rede_id, 1000)
            if c["subrede_id"] == str(s["id"])]
    s = dict(s)
    s["propagados"] = (dict(s["resumo"] or {})).get("propagados") or {}
    ids = [str(s["id"])]
    if jusante:
        ids = opendss.subredes_de_jusante(cur, rede_id, ids, s["tier_ordem"])
    try:
        modelo = opendss.montar_da_subrede(cur, rede_id, s, dela,
                                           ano if ano is not None else datetime.now(timezone.utc).year,
                                           ids)
    except opendss.ErroConversao as e:
        # 422: o pedido é legítimo, o DADO é que não permite converter. O código do erro nomeia o que falta.
        raise ErroAPI(422, e.codigo, e.mensagem) from e
    arquivos = opendss.linhas_do_circuito(modelo)
    resumo = {
        "subrede": s["nome"], "tier": s["tier"], "ano_da_curva": modelo["ano"],
        "subredes_no_circuito": len(modelo["subredes"]), "com_jusante": jusante,
        "exportado_em": datetime.now(timezone.utc).isoformat(),
        "barra_fonte": modelo["barra_fonte"], "kv_fonte": modelo["kv_fonte"],
        "codigo_tensao_nominal": modelo["codigo_tensao_nominal"],
        "conferencia": modelo["conferencia"], "avisos": modelo["avisos"], "ignorados": modelo["ignorados"],
        "chaves": [{"codigo": c["codigo"], "tipo": c["tipo"], "estado": c["estado"]} for c in modelo["chaves"]],
        "pontos_por_curva": opendss.PONTOS_DA_CURVA,
    }
    arquivos["resumo.json"] = json.dumps(resumo, ensure_ascii=False, indent=1) + "\n"
    return {"arquivos": arquivos, "resumo": resumo}
