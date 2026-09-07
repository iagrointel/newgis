"""Rotas das regras de conectividade da rede de utilidades (item L4-03-a-regras-de-conectividade; ADR
docs/adr/20260906T2058-regras-de-conectividade.md).

Cinco pontas:

- `POST /api/rede/{rede_id}/applyEdits` — lote atômico de adicionar/atualizar/apagar feições e associações.
  As CONEXÕES não vêm no corpo: são derivadas da coincidência geométrica (junção-junção e junção-ponta de
  aresta, tolerância TOLERANCIA_M) e cada uma precisa de uma regra que a permita — "sem regra = proibido" é o
  padrão. A recusa é 409 com código (`sem_regra`/`terminal_errado`) e mensagem que CITA a regra candidata;
  o lote inteiro desfaz (uma transação).
- `POST /api/rede/{rede_id}/validar` — validação em lote: rederiva TODAS as conexões da geometria gravada e
  reavalia TODAS as associações contra o conjunto de regras vigente; devolve os erros por feição. Só lê.
- `GET/POST /api/rede/{rede_id}/regras.csv` — exporta/importa o conjunto de regras nas 13 colunas das
  ferramentas Import/Export Rules do ArcGIS Pro (ver `regras_csv.py`). A importação SUBSTITUI o conjunto
  inteiro numa transação e é ato de admin da rede (`rede.administrar`).
- `PUT /api/rede/{rede_id}/regras/ativacao` — liga/desliga a avaliação (a comporta de carga em massa
  `rede.regras_ativas`). Só `rede.administrar`: não existe atributo de feição nem campo de applyEdits que
  desligue regra — corpo com campo a mais é 422 na borda (extra="forbid" em `modelos.py`).

Semântica dos três tipos de conectividade (fonte: network-rules.htm da Esri, na paridade do item):
junção-aresta governa a ponta da aresta na junção (com o terminal DA JUNÇÃO, declarado pela aresta em
`terminal_inicio`/`terminal_fim`); aresta-junção-aresta permite duas arestas na MESMA junção mesmo sem regra
junção-aresta para os pares (o caso do poste de passagem) — e regra junção-aresta que exista para o par se
sobrepõe (terminal errado é recusa, não cai na aresta-junção-aresta); junção-junção governa pontos
coincidentes. Associações (contenção/estrutura) são sempre explícitas e direcionais."""

import hashlib
import json

import psycopg2
from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import areas_sujas, deposito, regras_csv
from app.rede_utilidades import regras as motor
from app.rede_utilidades.modelos import (
    ApplyEditsEntrada,
    ApplyEditsResultado,
    AtivacaoEntrada,
    AtivacaoResultado,
    ImportacaoRegrasResultado,
    ValidacaoResultado,
)
from app.rede_utilidades.rotas import _uuid_ok

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}
ADMIN = {"x-auth": "S/T", "x-privilegio": "rede.administrar"}

TOLERANCIA_M = 0.5  # coincidência geométrica, em metros (geography); declarada no ADR seção 4
REGRAS_CSV_MAX_BYTES = 2 * 1024 * 1024  # o pacote elétrico inteiro exportado tem ~20 KiB; 2 MiB é folga larga

SQL_FEICAO = (
    "SELECT f.id, g.codigo AS grupo, g.geometria, t.codigo AS tipo, f.terminal_inicio, f.terminal_fim "
    "FROM plat.rede_feicao f JOIN plat.rede_grupo g ON g.id = f.grupo_id "
    "JOIN plat.rede_tipo t ON t.id = f.tipo_id"
)

# junções (grupo de geometria 'ponto') a TOLERANCIA_M de uma feição de referência
SQL_JUNCOES_PERTO = (
    SQL_FEICAO + " WHERE f.rede_id = %s::uuid AND f.id <> %s::uuid AND g.geometria = 'ponto' "
    "AND ST_DWithin(f.geometria::geography, "
    "(SELECT geometria FROM plat.rede_feicao WHERE id = %s::uuid)::geography, %s)"
)

# arestas com ALGUMA ponta a TOLERANCIA_M de uma junção de referência; as flags dizem qual ponta
SQL_ARESTAS_NA_JUNCAO = (
    "SELECT f.id, g.codigo AS grupo, g.geometria, t.codigo AS tipo, f.terminal_inicio, f.terminal_fim, "
    "ST_DWithin(ST_StartPoint(f.geometria)::geography, ref.pt, %s) AS no_inicio, "
    "ST_DWithin(ST_EndPoint(f.geometria)::geography, ref.pt, %s) AS no_fim "
    "FROM (SELECT geometria::geography AS pt FROM plat.rede_feicao WHERE id = %s::uuid) ref, "
    "plat.rede_feicao f JOIN plat.rede_grupo g ON g.id = f.grupo_id "
    "JOIN plat.rede_tipo t ON t.id = f.tipo_id "
    "WHERE f.rede_id = %s::uuid AND f.id <> %s::uuid AND g.geometria = 'linha' "
    "AND (ST_DWithin(ST_StartPoint(f.geometria)::geography, ref.pt, %s) "
    "OR ST_DWithin(ST_EndPoint(f.geometria)::geography, ref.pt, %s))"
)

# junções nas pontas de uma aresta de referência; as flags dizem em qual ponta cada junção está
SQL_JUNCOES_NAS_PONTAS = (
    "SELECT j.id, g.codigo AS grupo, t.codigo AS tipo, j.no_inicio, j.no_fim FROM ("
    "SELECT f.id, f.grupo_id, f.tipo_id, "
    "ST_DWithin(f.geometria::geography, ST_StartPoint(e.geometria)::geography, %s) AS no_inicio, "
    "ST_DWithin(f.geometria::geography, ST_EndPoint(e.geometria)::geography, %s) AS no_fim "
    "FROM plat.rede_feicao e, plat.rede_feicao f "
    "WHERE e.id = %s::uuid AND f.rede_id = e.rede_id AND f.id <> e.id"
    ") j JOIN plat.rede_grupo g ON g.id = j.grupo_id JOIN plat.rede_tipo t ON t.id = j.tipo_id "
    "WHERE g.geometria = 'ponto' AND (j.no_inicio OR j.no_fim)"
)


def _ref(f: dict) -> motor.Ref:
    return (f["grupo"], f["tipo"])


def _carregar_rede(cur, rid: str) -> dict:
    cur.execute(
        "SELECT id, regras_ativas, pacote_codigo, versao_edicao, tracado_sobre_area_suja_modo "
        "FROM plat.rede WHERE id = %s::uuid",
        (rid,),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")
    return r


def _exigir_pacote(rede: dict) -> None:
    if rede["pacote_codigo"] is None:
        raise ErroAPI(409, "rede_sem_pacote",
                      "a rede ainda não recebeu um pacote de ativos; sem catálogo não há tipos nem regras "
                      "para editar feições")


def _carregar_feicao(cur, rid: str, feicao_id: str) -> dict:
    cur.execute(SQL_FEICAO + " WHERE f.rede_id = %s::uuid AND f.id = %s::uuid", (rid, feicao_id))
    f = cur.fetchone()
    if f is None:
        raise ErroAPI(404, "feicao_inexistente", f"a feição {feicao_id} não existe nesta rede")
    return f


def _conferir_geometria(geometria: dict | None, papel: str) -> None:
    """GeoJSON de entrada contra o papel do grupo (ponto/linha/sem_geometria). 422 apontando o campo."""
    if papel == "sem_geometria":
        if geometria is not None:
            raise ErroAPI(422, "geometria_nao_se_aplica",
                          "o grupo tem geometria 'sem_geometria'; a feição não leva geometria",
                          {"campo": "geometria"})
        return
    if geometria is None:
        raise ErroAPI(422, "geometria_obrigatoria",
                      f"o grupo tem geometria {papel!r}; a feição precisa de geometria GeoJSON",
                      {"campo": "geometria"})
    tipo = geometria.get("type")
    coords = geometria.get("coordinates")
    esperado = "Point" if papel == "ponto" else "LineString"
    if tipo != esperado or not isinstance(coords, list):
        raise ErroAPI(422, "geometria_papel_errado",
                      f"o grupo é de geometria {papel!r}; a geometria tem de ser GeoJSON {esperado}",
                      {"campo": "geometria"})
    pontos = [coords] if tipo == "Point" else coords
    if tipo == "LineString" and len(pontos) < 2:
        raise ErroAPI(422, "geometria_papel_errado",
                      "uma LineString precisa de ao menos 2 pontos", {"campo": "geometria"})
    for p in pontos:
        if (not isinstance(p, list) or len(p) != 2
                or not all(isinstance(v, (int, float)) for v in p)
                or not (-180 <= p[0] <= 180) or not (-90 <= p[1] <= 90)):
            raise ErroAPI(422, "coordenada_invalida",
                          f"coordenada {p!r} inválida; vale [longitude, latitude] em WGS84",
                          {"campo": "geometria"})


def _conferir_terminais_na_feicao(terminal_inicio: str | None, terminal_fim: str | None, papel: str) -> None:
    """Os campos de terminal declaram o terminal DA JUNÇÃO em cada ponta de uma ARESTA; numa junção ou
    feição sem geometria eles não têm significado e são recusados na entrada (nunca ignorados em silêncio)."""
    if papel != "linha" and (terminal_inicio is not None or terminal_fim is not None):
        raise ErroAPI(422, "terminal_nao_se_aplica",
                      "terminal_inicio/terminal_fim declaram o terminal da junção na ponta de uma aresta; "
                      f"esta feição é do papel {papel!r}",
                      {"campo": "terminal_inicio"})


def _pontas_na_juncao(cur, rid: str, juncao_id: str) -> list[dict]:
    """Arestas com ponta na junção: [{feicao, ref, terminal}]. O terminal é o declarado pela aresta para
    aquela ponta (terminal_inicio/fim)."""
    cur.execute(SQL_ARESTAS_NA_JUNCAO,
                (TOLERANCIA_M, TOLERANCIA_M, juncao_id, rid, juncao_id, TOLERANCIA_M, TOLERANCIA_M))
    pontas = []
    for a in cur.fetchall():
        if a["no_inicio"]:
            pontas.append({"id": str(a["id"]), "ref": _ref(a), "terminal": a["terminal_inicio"]})
        if a["no_fim"]:
            pontas.append({"id": str(a["id"]), "ref": _ref(a), "terminal": a["terminal_fim"]})
    return pontas


def _avaliar_ponto(regras: list[motor.Regra], juncao_ref: motor.Ref, pontas: list[dict],
                   feicoes: list[str]) -> tuple[dict, list[motor.Violacao]]:
    """Todas as pontas de aresta numa junção. Junção-aresta governa primeiro; a ponta sem regra
    junção-aresta (e sem CANDIDATA — terminal errado é recusa direta, a regra do par se sobrepõe) só é
    permitida se uma regra aresta-junção-aresta a ligar a outra aresta da mesma junção. Devolve
    ({índice da ponta: regra que permitiu}, [violações])."""
    cobertas: dict[int, motor.Regra] = {}
    violacoes: list[motor.Violacao] = []
    sem_je: list[int] = []
    for i, p in enumerate(pontas):
        r, v = motor.avaliar_je(regras, juncao_ref, p["ref"], p["terminal"], feicoes)
        if r is not None:
            cobertas[i] = r
        elif v.codigo == "terminal_errado":
            violacoes.append(v)
        else:
            sem_je.append(i)
    for i in sem_je:
        a = pontas[i]["ref"]
        regra_eje = None
        for j, q in enumerate(pontas):
            if j == i:
                continue
            r, _ = motor.avaliar_eje(regras, a, juncao_ref, q["ref"], feicoes)
            if r is not None:
                regra_eje = r
                break
        if regra_eje is not None:
            cobertas[i] = regra_eje
        else:
            violacoes.append(motor.Violacao(
                "sem_regra",
                f"conexão proibida entre a aresta {motor.texto_ref(a)} e a junção "
                f"{motor.texto_ref(juncao_ref)}: nenhuma regra juncao_aresta cobre o par e nenhuma regra "
                f"aresta_juncao_aresta liga esta aresta a outra nesta junção; {motor.SEM_REGRA}",
                feicoes,
            ))
    return cobertas, violacoes


def _levantar(violacoes: list[motor.Violacao]) -> None:
    """A primeira violação vira a resposta 409; as demais vão no detalhe (o lote desfaz inteiro de
    qualquer jeito, então a pessoa recebe de uma vez tudo o que o lote quebraria)."""
    if not violacoes:
        return
    v = violacoes[0]
    detalhe = v.json()
    if len(violacoes) > 1:
        detalhe["outras"] = [x.json() for x in violacoes[1:]]
    raise ErroAPI(409, v.codigo, v.mensagem, detalhe)


def _derivar_juncao(cur, tenant_id: int, rid: str, juncao: dict, regras, ativas: bool) -> int:
    """Conexões de uma junção: junção-junção com as coincidentes e junção-aresta (ou aresta-junção-aresta)
    com as pontas de aresta que nela caem. Devolve quantas conexões novas gravou."""
    jid = str(juncao["id"])
    jref = _ref(juncao)
    gravadas = 0
    violacoes: list[motor.Violacao] = []

    cur.execute(SQL_JUNCOES_PERTO, (rid, jid, jid, TOLERANCIA_M))
    for outra in cur.fetchall():
        oid = str(outra["id"])
        de_id, para_id = (jid, oid) if jid < oid else (oid, jid)  # par não ordenado em forma canônica
        regra_id = None
        if ativas:
            r, v = motor.avaliar_jj(regras, jref, _ref(outra), sorted([jid, oid]))
            if r is None:
                violacoes.append(v)
                continue
            regra_id = r.id
        cur.execute(
            "INSERT INTO plat.rede_conexao(tenant_id, rede_id, tipo, de_feicao_id, para_feicao_id, regra_id) "
            "VALUES (%s, %s::uuid, 'jj', %s::uuid, %s::uuid, %s::uuid) ON CONFLICT DO NOTHING",
            (tenant_id, rid, de_id, para_id, regra_id),
        )
        gravadas += cur.rowcount

    pontas = _pontas_na_juncao(cur, rid, jid)
    if pontas:
        if ativas:
            cobertas, vs = _avaliar_ponto(regras, jref, pontas, sorted({jid, *[p["id"] for p in pontas]}))
            violacoes.extend(vs)
        else:
            cobertas = {i: None for i in range(len(pontas))}
        _levantar(violacoes)
        for i, p in enumerate(pontas):
            if i not in cobertas:
                continue  # coberta só por violação já levantada; aqui por completude
            regra = cobertas[i]
            cur.execute(
                "INSERT INTO plat.rede_conexao(tenant_id, rede_id, tipo, de_feicao_id, para_feicao_id, "
                "de_terminal, regra_id) VALUES (%s, %s::uuid, 'je', %s::uuid, %s::uuid, %s, %s::uuid) "
                "ON CONFLICT DO NOTHING",
                (tenant_id, rid, jid, p["id"], p["terminal"], regra.id if regra else None),
            )
            gravadas += cur.rowcount
    _levantar(violacoes)
    return gravadas


def _derivar_aresta(cur, tenant_id: int, rid: str, aresta: dict, regras, ativas: bool) -> int:
    """Conexões de uma aresta: para cada ponta, as junções que nela caem (a avaliação é a mesma de
    `_derivar_juncao`, vista do outro lado — a aresta-junção-aresta precisa enxergar TODAS as pontas da
    junção, inclusive as que já estavam gravadas)."""
    aid = str(aresta["id"])
    gravadas = 0
    cur.execute(SQL_JUNCOES_NAS_PONTAS, (TOLERANCIA_M, TOLERANCIA_M, aid))
    juncoes = cur.fetchall()
    for j in juncoes:
        jid = str(j["id"])
        pontas = _pontas_na_juncao(cur, rid, jid)  # já inclui esta aresta, que está gravada
        violacoes: list[motor.Violacao] = []
        if ativas:
            cobertas, violacoes = _avaliar_ponto(regras, _ref(j), pontas, sorted({aid, jid}))
            _levantar(violacoes)
        else:
            cobertas = {i: None for i in range(len(pontas))}
        for i, p in enumerate(pontas):
            if p["id"] != aid or i not in cobertas:
                continue  # as conexões das OUTRAS arestas desta junção já existem (ON CONFLICT as pularia)
            regra = cobertas[i]
            cur.execute(
                "INSERT INTO plat.rede_conexao(tenant_id, rede_id, tipo, de_feicao_id, para_feicao_id, "
                "de_terminal, regra_id) VALUES (%s, %s::uuid, 'je', %s::uuid, %s::uuid, %s, %s::uuid) "
                "ON CONFLICT DO NOTHING",
                (tenant_id, rid, jid, aid, p["terminal"], regra.id if regra else None),
            )
            gravadas += cur.rowcount
    return gravadas


def _derivar(cur, tenant_id: int, rid: str, feicao_id: str, regras, ativas: bool) -> int:
    f = _carregar_feicao(cur, rid, feicao_id)
    if f["geometria"] == "ponto":
        return _derivar_juncao(cur, tenant_id, rid, f, regras, ativas)
    if f["geometria"] == "linha":
        return _derivar_aresta(cur, tenant_id, rid, f, regras, ativas)
    return 0


def _apagar_conexoes_derivadas(cur, rid: str, feicao_id: str) -> None:
    """Antes de rederivar uma feição atualizada. As associações NÃO caem: são explícitas, não derivadas."""
    cur.execute(
        "DELETE FROM plat.rede_conexao WHERE rede_id = %s::uuid AND (de_feicao_id = %s::uuid OR "
        "para_feicao_id = %s::uuid)",
        (rid, feicao_id, feicao_id),
    )


def _apply_edits_sincrono(rid: str, corpo: ApplyEditsEntrada, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        rede = _carregar_rede(cur, rid)
        _exigir_pacote(rede)
        ativas = rede["regras_ativas"]
        mapas = deposito.mapas_catalogo(cur, rid)
        regras = deposito.carregar_regras(cur, rid) if ativas else []

        adicionadas: list[str] = []
        afetadas: list[str] = []

        for f in corpo.adicionar:
            tipo_id = mapas["ids"].get((f.grupo, f.tipo))
            if tipo_id is None:
                raise ErroAPI(422, "tipo_inexistente",
                              f"não existe tipo de ativo {f.tipo} no grupo {f.grupo!r} desta rede",
                              {"campo": "grupo"})
            papel = mapas["geometrias"][f.grupo]
            _conferir_geometria(f.geometria, papel)
            _conferir_terminais_na_feicao(f.terminal_inicio, f.terminal_fim, papel)
            cur.execute(
                "INSERT INTO plat.rede_feicao(tenant_id, rede_id, grupo_id, tipo_id, geometria, atributos, "
                "terminal_inicio, terminal_fim, criado_por) "
                "VALUES (%s, %s::uuid, %s::uuid, %s::uuid, "
                "CASE WHEN %s::text IS NULL THEN NULL ELSE ST_GeomFromGeoJSON(%s) END, "
                "%s::jsonb, %s, %s, %s) RETURNING id",
                (auth.tenant_id, rid, mapas["grupo_ids"][f.grupo], tipo_id,
                 json.dumps(f.geometria) if f.geometria is not None else None,
                 json.dumps(f.geometria) if f.geometria is not None else None,
                 json.dumps(f.atributos, ensure_ascii=False), f.terminal_inicio, f.terminal_fim,
                 auth.usuario_id),
            )
            novo_id = str(cur.fetchone()["id"])
            adicionadas.append(novo_id)
            afetadas.append(novo_id)

        for f in corpo.atualizar:
            atual = _carregar_feicao(cur, rid, f.id)
            campos = f.model_fields_set
            if "geometria" in campos:
                _conferir_geometria(f.geometria, atual["geometria"])
            ti = f.terminal_inicio if "terminal_inicio" in campos else None
            tf = f.terminal_fim if "terminal_fim" in campos else None
            if "terminal_inicio" in campos or "terminal_fim" in campos:
                _conferir_terminais_na_feicao(
                    f.terminal_inicio if "terminal_inicio" in campos else None,
                    f.terminal_fim if "terminal_fim" in campos else None,
                    atual["geometria"])
            cur.execute(
                "UPDATE plat.rede_feicao SET "
                "geometria = CASE WHEN %s THEN CASE WHEN %s::text IS NULL THEN NULL "
                "ELSE ST_GeomFromGeoJSON(%s) END ELSE geometria END, "
                "atributos = CASE WHEN %s THEN %s::jsonb ELSE atributos END, "
                "terminal_inicio = CASE WHEN %s THEN %s ELSE terminal_inicio END, "
                "terminal_fim = CASE WHEN %s THEN %s ELSE terminal_fim END "
                "WHERE rede_id = %s::uuid AND id = %s::uuid",
                ("geometria" in campos,
                 json.dumps(f.geometria) if f.geometria is not None else None,
                 json.dumps(f.geometria) if f.geometria is not None else None,
                 "atributos" in campos, json.dumps(f.atributos, ensure_ascii=False),
                 "terminal_inicio" in campos, ti,
                 "terminal_fim" in campos, tf,
                 rid, f.id),
            )
            afetadas.append(f.id)

        apagadas = 0
        geometrias_apagadas: list[tuple[str, str | None]] = []
        for fid in corpo.apagar:
            _carregar_feicao(cur, rid, fid)  # 404 honesto: apagar o que não existe é erro, não silêncio
            cur.execute("SELECT ST_AsText(geometria) AS wkt FROM plat.rede_feicao WHERE id = %s::uuid", (fid,))
            geometrias_apagadas.append((fid, cur.fetchone()["wkt"]))
            cur.execute("DELETE FROM plat.rede_feicao WHERE rede_id = %s::uuid AND id = %s::uuid", (rid, fid))
            apagadas += cur.rowcount

        associacoes_adicionadas = 0
        for a in corpo.associacoes.adicionar:
            de = _carregar_feicao(cur, rid, a.de)
            para = _carregar_feicao(cur, rid, a.para)
            regra_id = None
            if ativas:
                r, v = motor.avaliar_associacao(regras, a.tipo, _ref(de), _ref(para), sorted([a.de, a.para]))
                if r is None:
                    _levantar([v])
                regra_id = r.id
            try:
                cur.execute(
                    "INSERT INTO plat.rede_associacao(tenant_id, rede_id, tipo, de_feicao_id, "
                    "para_feicao_id, regra_id) VALUES (%s, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid)",
                    (auth.tenant_id, rid, a.tipo, a.de, a.para, regra_id),
                )
            except psycopg2.errors.UniqueViolation as e:
                raise ErroAPI(409, "associacao_existente",
                              "já existe essa associação entre as duas feições") from e
            associacoes_adicionadas += 1

        associacoes_apagadas = 0
        for aid in corpo.associacoes.apagar:
            cur.execute(
                "DELETE FROM plat.rede_associacao WHERE rede_id = %s::uuid AND id = %s::uuid", (rid, aid))
            if cur.rowcount == 0:
                raise ErroAPI(404, "associacao_inexistente", f"a associação {aid} não existe nesta rede")
            associacoes_apagadas += 1

        conexoes = 0
        for fid in afetadas:
            _apagar_conexoes_derivadas(cur, rid, fid)
        for fid in afetadas:
            if fid in corpo.apagar:
                continue
            conexoes += _derivar(cur, auth.tenant_id, rid, fid, regras, ativas)

        # área suja (item L4-03-d-areas-sujas-e-validacao): uma por FEIÇÃO tocada neste lote (adicionada ou
        # atualizada, se tiver geometria — `registrar_por_feicoes` filtra) mais uma por feição apagada (pela
        # geometria capturada ANTES do DELETE). Uma única versão de edição para o lote inteiro: é o "por
        # versão" do portão, e um applyEdits já é uma unidade atômica.
        area_sujas_criadas = 0
        if afetadas or geometrias_apagadas:
            versao = areas_sujas.proxima_versao(cur, rid)
            area_sujas_criadas += areas_sujas.registrar_por_feicoes(cur, auth.tenant_id, rid, versao, afetadas)
            for fid, wkt in geometrias_apagadas:
                area_sujas_criadas += areas_sujas.registrar_para_geometria_apagada(
                    cur, auth.tenant_id, rid, versao, fid, wkt)

        registrar_evento(cur, request, "redes/apply_edits", "rede", rid, {
            "adicionadas": len(adicionadas), "atualizadas": len(corpo.atualizar), "apagadas": apagadas,
            "associacoes_adicionadas": associacoes_adicionadas,
            "associacoes_apagadas": associacoes_apagadas, "conexoes": conexoes,
            "regras_ativas": ativas, "area_sujas_criadas": area_sujas_criadas,
        })
        return {
            "rede_id": rid, "regras_ativas": ativas, "adicionadas": adicionadas,
            "atualizadas": len(corpo.atualizar), "apagadas": apagadas,
            "associacoes_adicionadas": associacoes_adicionadas,
            "associacoes_apagadas": associacoes_apagadas, "conexoes": conexoes,
            "area_sujas_criadas": area_sujas_criadas,
        }


@router.post("/{rede_id}/applyEdits", response_model=ApplyEditsResultado, openapi_extra=EDITAR)
def apply_edits(rede_id: str, corpo: ApplyEditsEntrada, request: Request,
                auth: Auth = autenticado("rede.editar")):
    """Lote atômico de edição. Síncrono de propósito: o teto é MAX_POR_LOTE operações por tipo e a derivação
    é por feição com índice GiST — o caso medido no teste (lote de 5 feições) fecha em dezenas de ms."""
    return _apply_edits_sincrono(_uuid_ok(rede_id), corpo, auth, request)


@router.post("/{rede_id}/validar", response_model=ValidacaoResultado, openapi_extra=EDITAR)
def validar(rede_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """Validação em lote: rederiva TODA conexão da geometria gravada e reavalia TODA associação contra o
    conjunto de regras vigente. Só lê; os erros vêm por feição. Avalia mesmo com a comporta desligada — é
    justamente ela que mostra o que a carga em massa deixou fora da lei."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        rede = _carregar_rede(cur, rid)
        _exigir_pacote(rede)
        regras = deposito.carregar_regras(cur, rid)
        erros: list[dict] = []
        avaliadas = 0

        cur.execute(SQL_FEICAO + " WHERE f.rede_id = %s::uuid AND g.geometria = 'ponto' ORDER BY f.id",
                    (rid,))
        juncoes = cur.fetchall()
        for j in juncoes:
            jid = str(j["id"])
            cur.execute(SQL_JUNCOES_PERTO, (rid, jid, jid, TOLERANCIA_M))
            for outra in cur.fetchall():
                if str(outra["id"]) <= jid:
                    continue  # cada par junção-junção é avaliado uma única vez
                avaliadas += 1
                _, v = motor.avaliar_jj(regras, _ref(j), _ref(outra), sorted([jid, str(outra["id"])]))
                if v is not None:
                    erros.append(v.json())
            pontas = _pontas_na_juncao(cur, rid, jid)
            if not pontas:
                continue
            avaliadas += len(pontas)
            _, vs = _avaliar_ponto(regras, _ref(j), pontas, sorted({jid, *[p["id"] for p in pontas]}))
            erros.extend(v.json() for v in vs)

        cur.execute(
            "SELECT a.id, a.tipo, a.de_feicao_id, a.para_feicao_id FROM plat.rede_associacao a "
            "WHERE a.rede_id = %s::uuid ORDER BY a.id", (rid,))
        associacoes = cur.fetchall()
        for a in associacoes:
            de = _carregar_feicao(cur, rid, str(a["de_feicao_id"]))
            para = _carregar_feicao(cur, rid, str(a["para_feicao_id"]))
            _, v = motor.avaliar_associacao(regras, a["tipo"], _ref(de), _ref(para),
                                            sorted([str(a["de_feicao_id"]), str(a["para_feicao_id"])]))
            if v is not None:
                erros.append(v.json())

        registrar_evento(cur, request, "redes/validar_regras", "rede", rid, {
            "conexoes_avaliadas": avaliadas, "associacoes_avaliadas": len(associacoes),
            "total_erros": len(erros),
        })
        return {
            "rede_id": rid, "regras_ativas": rede["regras_ativas"],
            "conexoes_avaliadas": avaliadas, "associacoes_avaliadas": len(associacoes),
            "total_erros": len(erros), "erros": erros,
        }


@router.get("/{rede_id}/regras", openapi_extra=LER)
def listar_regras(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """O conjunto de regras em JSON citável (a mesma forma dos lados no pacote versão 2)."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _carregar_rede(cur, rid)
        regras = deposito.carregar_regras(cur, rid)
    return {"total": len(regras), "itens": [motor.regra_json(r) for r in regras]}


@router.get("/{rede_id}/regras.csv", openapi_extra=LER, response_class=Response)
def exportar_regras_csv(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """O conjunto de regras nas 13 colunas das ferramentas Import/Export Rules do ArcGIS Pro."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _carregar_rede(cur, rid)
        regras = deposito.carregar_regras(cur, rid)
    bruto = regras_csv.exportar(regras)
    return Response(
        content=bruto,
        media_type="text/csv; charset=utf-8",
        headers={"ETag": '"' + hashlib.sha256(bruto).hexdigest() + '"', "Cache-Control": "no-store",
                 "Content-Disposition": "attachment; filename=regras.csv"},
    )


def _importar_regras_sincrono(rid: str, bruto: bytes, auth: Auth, request: Request) -> dict:
    if len(bruto) > REGRAS_CSV_MAX_BYTES:
        raise ErroAPI(413, "csv_grande_demais",
                      f"o CSV de regras passa de {REGRAS_CSV_MAX_BYTES} bytes ({len(bruto)})")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid FOR UPDATE", (rid,))
        if cur.fetchone() is None:
            raise ErroAPI(404, "rede_inexistente", "rede inexistente")
        _exigir_pacote(_carregar_rede(cur, rid))
        mapas = deposito.mapas_catalogo(cur, rid)
        try:
            validadas = regras_csv.importar(bruto, mapas["tipos_por_grupo"], mapas["terminais"],
                                            mapas["geometrias"])
        except regras_csv.ErroCsv as e:
            raise ErroAPI(422, "csv_regras_invalido",
                          f"o CSV de regras foi recusado: {len(e.problemas)} problema(s)", e.problemas) from e
        total = deposito.substituir_regras(cur, auth.tenant_id, rid, validadas, mapas["ids"])
        sha = hashlib.sha256(bruto).hexdigest()
        registrar_evento(cur, request, "redes/importar_regras_csv", "rede", rid,
                         {"total": total, "sha256": sha, "bytes": len(bruto)})
        return {"rede_id": rid, "total": total, "sha256": sha, "bytes": len(bruto)}


@router.post("/{rede_id}/regras.csv", response_model=ImportacaoRegrasResultado, status_code=201,
             openapi_extra=ADMIN)
async def importar_regras_csv(rede_id: str, request: Request,
                              auth: Auth = autenticado("rede.administrar")):
    """Substitui o conjunto INTEIRO de regras pelo do CSV (formato de colunas da Esri), numa transação.
    Ato de admin da rede: a ferramenta Import Rules da Esri ACRESCENTA; aqui substitui — a diferença e o
    motivo estão na paridade do item.

    Corpo NÃO é JSON (é `text/csv`): sob sessão de navegador o CSRF de `checar_escrita_sob_cookie` (ADR
    0002 §5.3, "corpo só JSON") recusa com 415 antes mesmo do privilégio ser checado — a mesma regra que
    já vale para `POST /api/arquivos` (ADR 0006, "upload só por token, nunca cookie"). Na prática, quem
    substitui o conjunto de regras por CSV usa um token de serviço com escopo `admin:inquilino`, nunca a
    sessão do navegador; a tela administrativa faz a chamada por trás com o token do próprio inquilino."""
    rid = _uuid_ok(rede_id)
    bruto = await request.body()
    return await run_in_threadpool(_importar_regras_sincrono, rid, bruto, auth, request)


@router.put("/{rede_id}/regras/ativacao", response_model=AtivacaoResultado, openapi_extra=ADMIN)
def ativar_regras(rede_id: str, corpo: AtivacaoEntrada, request: Request,
                  auth: Auth = autenticado("rede.administrar")):
    """Liga/desliga a avaliação de regras no applyEdits (a comporta de carga em massa). O padrão é LIGADA:
    'sem regra = proibido'. Desligar não apaga regra nem conexão — só grava as conexões novas com
    regra_id NULL; a validação em lote continua avaliando tudo contra o conjunto vigente."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _carregar_rede(cur, rid)
        deposito.definir_regras_ativas(cur, rid, corpo.ativa)
        registrar_evento(cur, request, "redes/regras_ativacao", "rede", rid, {"ativa": corpo.ativa})
        return {"rede_id": rid, "regras_ativas": corpo.ativa}
