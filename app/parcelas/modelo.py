"""Operações do modelo de parcelas sobre as tabelas `plat.parcela_*` (migração
20260908T2140_parcelas.sql). Toda escrita é por transação do chamador (o cursor vem de fora);
o inquilino vem de fora também e vai na coluna `tenant_id` — a RLS do papel `plat_app` é a
segunda trava, não a primeira. Erros são ErroAPI 422 com código curto, no mesmo padrão do
motor de regras de rede (app/rede/regras.py).

Semântica de retirada (é a refutação do item): retirar uma parcela NÃO apaga linha — a
parcela ganha `retirada_por_registro` + `retirada_em`, sai de `v_parcela_atual` e entra em
`v_parcela_historico` com o registro. Linha que serve SÓ a parcelas retiradas é retirada junto;
linha PARTILHADA com parcela ativa continua ativa. Ponto fica (é acervo cadastral do
inquilino, não da parcela).
"""

from typing import Iterable

import psycopg2.extras

from app.erros import ErroAPI

SRID = 31982  # SIRGAS 2000 / UTM 22S — o mesmo do SIG de teste interno (geometry_columns)

TIPOS = ("lote", "gleba", "quadra", "servidao", "estrato")
TIPOS_REGISTRO = (
    "matricula", "escritura", "loteamento", "desmembramento", "remembramento", "aprovacao", "outro",
)
ORIGENS = ("medida", "escaneada", "derivada")
ORIGENS_REGISTRO = ("manual", "importado", "sintetico")

_COLUNAS_PARCELA = (
    "id, tenant_id, tipo, codigo, geom, area_declarada_m2, area_calculada_m2, erro_fechamento_m, "
    "erro_fechamento_razao, atributos, criada_por_registro, retirada_por_registro, retirada_em, "
    "ativa, criado_em"
)


def _texto(valor, campo: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErroAPI(422, "valor_invalido", f"{campo} precisa ser texto não vazio")
    return valor.strip()


# ------------------------------------------------------------------ registro


def criar_registro(cur, tenant_id: int, *, codigo, tipo, origem="manual", data_registro=None,
                   descricao=None) -> dict:
    """O documento legal. `codigo` é o nome do documento NO INQUILINO — nunca número de
    matrícula real (regra do item)."""
    _texto(codigo, "codigo do registro")
    if tipo not in TIPOS_REGISTRO:
        raise ErroAPI(422, "tipo_invalido", f"tipo de registro precisa ser um de: {', '.join(TIPOS_REGISTRO)}")
    if origem not in ORIGENS_REGISTRO:
        raise ErroAPI(422, "tipo_invalido", f"origem precisa ser uma de: {', '.join(ORIGENS_REGISTRO)}")
    cur.execute(
        "INSERT INTO plat.parcela_registro(tenant_id, codigo, tipo, origem, data_registro, descricao) "
        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id, codigo, tipo, origem, data_registro",
        (tenant_id, codigo, tipo, origem, data_registro, descricao),
    )
    return cur.fetchone()


# ------------------------------------------------------------------ ponto


def criar_ponto(cur, tenant_id: int, *, x: float, y: float, nome=None, precisao_xy_m=None,
                fixo=False, origem="medida", registro_id=None, categoria=None) -> dict:
    """Ponto da malha com PRECISÃO DECLARADA (a coluna existe para ser preenchida por quem
    mediu; importação derivada deixa NULL — ausência declarada, não inferência) e CATEGORIA de
    exatidão (item 03: 'controle' é o datum do ajuste, 'apoio' o resto; o DEFAULT do banco é
    'apoio', a CHECK do banco recusa o resto)."""
    if origem not in ORIGENS:
        raise ErroAPI(422, "tipo_invalido", f"origem precisa ser uma de: {', '.join(ORIGENS)}")
    cur.execute(
        "INSERT INTO plat.parcela_ponto(tenant_id, nome, geom, precisao_xy_m, fixo, origem, "
        "criada_por_registro, categoria) VALUES (%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),%s),%s,%s,"
        "%s,%s,COALESCE(%s,'apoio')) "
        "RETURNING id, nome, precisao_xy_m, fixo, origem, categoria",
        (tenant_id, nome, float(x), float(y), SRID, precisao_xy_m, bool(fixo), origem, registro_id,
         categoria),
    )
    return cur.fetchone()


def _ponto_xy(cur, ponto_id) -> tuple[float, float]:
    cur.execute("SELECT ST_X(geom) AS x, ST_Y(geom) AS y FROM plat.parcela_ponto WHERE id = %s::uuid",
                (str(ponto_id),))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(422, "valor_invalido", f"ponto {ponto_id} não existe")
    return float(r["x"]), float(r["y"])


# ------------------------------------------------------------------ linha (COGO)


def criar_linha(cur, tenant_id: int, *, de_ponto_id, para_ponto_id, rumo_graus=None,
                distancia_m=None, raio_m=None, arco_m=None, tipo_cogo=None, precisao_rumo_s=None,
                precisao_dist_cm=None, origem="medida", registro_id=None, categoria=None) -> dict:
    """Linha de limite com atributos COGO. A GEOMETRIA vem sempre dos dois pontos
    (ST_MakeLine) — arco de verdade fica para a fase de desenho; a corda fecha a malha e o
    raio (COM SINAL: positivo curva à direita) e o comprimento de arco ficam declarados na
    linha (paridade §3 do documento de paridade). CATEGORIA de exatidão (item 03): 'medido'
    (padrão do banco), 'escritura' ou 'derivado'; o par de sigma padrão vem da tabela de
    categorias em ajuste.py."""
    if origem not in ORIGENS:
        raise ErroAPI(422, "tipo_invalido", f"origem precisa ser uma de: {', '.join(ORIGENS)}")
    if tipo_cogo not in ("reta", "arco", None):
        raise ErroAPI(422, "tipo_invalido", "tipo_cogo precisa ser 'reta', 'arco' ou nulo")
    if (tipo_cogo == "arco") != (raio_m is not None):
        raise ErroAPI(422, "valor_invalido", "arco precisa de raio; reta não tem raio")
    if raio_m is not None and arco_m is None:
        raise ErroAPI(422, "valor_invalido", "arco precisa também do comprimento de arco (arco_m)")
    x1, y1 = _ponto_xy(cur, de_ponto_id)
    x2, y2 = _ponto_xy(cur, para_ponto_id)
    cur.execute(
        "INSERT INTO plat.parcela_linha(tenant_id, de_ponto_id, para_ponto_id, geom, rumo_graus, "
        "distancia_m, raio_m, arco_m, tipo_cogo, precisao_rumo_s, precisao_dist_cm, origem, "
        "criada_por_registro, categoria) VALUES (%s,%s,%s,ST_SetSRID(ST_MakeLine(ST_MakePoint(%s,%s),"
        "ST_MakePoint(%s,%s)),%s),%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,'medido')) "
        "RETURNING id, tipo_cogo, rumo_graus, distancia_m, raio_m, arco_m, categoria",
        (tenant_id, str(de_ponto_id), str(para_ponto_id), x1, y1, x2, y2, SRID, rumo_graus,
         distancia_m, raio_m, arco_m, tipo_cogo, precisao_rumo_s, precisao_dist_cm, origem,
         registro_id, categoria),
    )
    return cur.fetchone()


# ------------------------------------------------------------------ parcela


def criar_parcela(cur, tenant_id: int, *, tipo, codigo, registro_id, anel=None, wkt=None,
                  area_declarada_m2=None, atributos=None, linha_ids: Iterable | None = None,
                  erro_fechamento_m=None, erro_fechamento_razao=None) -> dict:
    """Polígono por TIPO (lote/gleba/quadra/servidão/estrato) criado POR um registro. O anel
    fecha sozinho (último vértice ≠ primeiro é aceito); a área calculada é do banco
    (ST_Area), nunca do chamador. `linha_ids` associa as linhas de limite — a mesma linha pode
    servir a outra parcela (linhas partilhadas)."""
    if tipo not in TIPOS:
        raise ErroAPI(422, "tipo_invalido", f"tipo de parcela precisa ser um de: {', '.join(TIPOS)}")
    _texto(codigo, "codigo da parcela")
    if wkt is None and anel is not None:
        pts = [(float(x), float(y)) for x, y in anel]
        if len(pts) < 3:
            raise ErroAPI(422, "valor_invalido", "anel precisa de pelo menos 3 vértices")
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        wkt = "POLYGON((" + ", ".join(f"{x} {y}" for x, y in pts) + "))"
    if wkt is None:
        raise ErroAPI(422, "valor_invalido", "parcela precisa de anel ou wkt")
    cur.execute(
        "INSERT INTO plat.parcela(tenant_id, tipo, codigo, geom, area_declarada_m2, "
        "area_calculada_m2, erro_fechamento_m, erro_fechamento_razao, atributos, "
        "criada_por_registro) VALUES (%s,%s,%s,ST_GeomFromText(%s,%s),%s,"
        "ST_Area(ST_GeomFromText(%s,%s)),%s,%s,%s,%s) "
        "RETURNING " + _COLUNAS_PARCELA,
        (tenant_id, tipo, codigo, wkt, SRID, area_declarada_m2, wkt, SRID, erro_fechamento_m,
         erro_fechamento_razao, psycopg2.extras.Json(atributos or {}), str(registro_id)),
    )
    parcela = cur.fetchone()
    for lid in linha_ids or ():
        cur.execute(
            "INSERT INTO plat.parcela_linha_parcela(tenant_id, linha_id, parcela_id) "
            "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
            (tenant_id, str(lid), str(parcela["id"])),
        )
    return parcela


def criar_conexao(cur, tenant_id: int, *, de_ponto_id, para_ponto_id, rumo_graus=None,
                  distancia_m=None, descricao=None, registro_id=None) -> dict:
    """Medida entre dois pontos que NÃO é limite de parcela (connection line da paridade)."""
    x1, y1 = _ponto_xy(cur, de_ponto_id)
    x2, y2 = _ponto_xy(cur, para_ponto_id)
    cur.execute(
        "INSERT INTO plat.parcela_conexao(tenant_id, de_ponto_id, para_ponto_id, geom, rumo_graus, "
        "distancia_m, descricao, criada_por_registro) VALUES (%s,%s,%s,ST_SetSRID(ST_MakeLine("
        "ST_MakePoint(%s,%s),ST_MakePoint(%s,%s)),%s),%s,%s,%s,%s) RETURNING id, distancia_m",
        (tenant_id, str(de_ponto_id), str(para_ponto_id), x1, y1, x2, y2, SRID, rumo_graus,
         distancia_m, descricao, registro_id),
    )
    return cur.fetchone()


# ------------------------------------------------------------------ retirada e linhagem


def retirar_parcela(cur, tenant_id: int, *, parcela_id, registro_id) -> dict:
    """A retirada é um ATO DE REGISTRO: a parcela fica histórica (ativa=false +
    retirada_por_registro + retirada_em) e as linhas que só ela usava são retiradas junto.
    Linha partilhada com parcela ativa continua. Nunca apaga."""
    cur.execute(
        "UPDATE plat.parcela SET ativa = false, retirada_por_registro = %s, retirada_em = now(), "
        "atualizado_em = now() WHERE id = %s::uuid AND tenant_id = %s AND ativa "
        "AND retirada_por_registro IS NULL RETURNING id, codigo, tipo",
        (str(registro_id), str(parcela_id), tenant_id),
    )
    retirada = cur.fetchone()
    if retirada is None:
        raise ErroAPI(422, "valor_invalido", f"parcela {parcela_id} não está ativa neste inquilino")
    cur.execute(
        "UPDATE plat.parcela_linha l SET ativa = false, retirada_por_registro = %s, "
        "atualizado_em = now() WHERE l.tenant_id = %s AND l.ativa "
        "AND EXISTS (SELECT 1 FROM plat.parcela_linha_parcela u WHERE u.linha_id = l.id "
        "            AND u.parcela_id = %s::uuid) "
        "AND NOT EXISTS (SELECT 1 FROM plat.parcela_linha_parcela u2 "
        "                JOIN plat.parcela p2 ON p2.id = u2.parcela_id "
        "                WHERE u2.linha_id = l.id AND p2.ativa)",
        (str(registro_id), tenant_id, str(parcela_id)),
    )
    return dict(retirada)


def ficha(cur, tenant_id: int, parcela_id) -> dict:
    """A ficha COM linhagem (o que o portão pede ver): registro de criação, registro de
    retirada, predecessoras (parcelas retiradas pelo registro que criou esta) e sucessoras
    (parcelas criadas pelo registro que retirou esta) — linhagem nos dois sentidos, como no
    modelo de referência."""
    cur.execute(
        "SELECT p.id, p.tipo, p.codigo, p.ativa, p.area_calculada_m2, p.atributos, "
        "       rc.codigo AS criada_por_codigo, rc.tipo AS criada_por_tipo, rc.data_registro, "
        "       rr.codigo AS retirada_por_codigo, rr.tipo AS retirada_por_tipo, p.retirada_em "
        "FROM plat.parcela p "
        "JOIN plat.parcela_registro rc ON rc.id = p.criada_por_registro "
        "LEFT JOIN plat.parcela_registro rr ON rr.id = p.retirada_por_registro "
        "WHERE p.id = %s::uuid AND p.tenant_id = %s",
        (str(parcela_id), tenant_id),
    )
    p = cur.fetchone()
    if p is None:
        raise ErroAPI(404, "nao_encontrado", f"parcela {parcela_id} não existe neste inquilino")
    cur.execute(
        "SELECT id, tipo, codigo FROM plat.parcela WHERE tenant_id = %s AND retirada_por_registro = "
        "(SELECT criada_por_registro FROM plat.parcela WHERE id = %s::uuid) AND id <> %s::uuid",
        (tenant_id, str(parcela_id), str(parcela_id)),
    )
    predecessoras = cur.fetchall()
    cur.execute(
        "SELECT id, tipo, codigo, ativa FROM plat.parcela WHERE tenant_id = %s AND criada_por_registro = "
        "(SELECT retirada_por_registro FROM plat.parcela WHERE id = %s::uuid) AND id <> %s::uuid",
        (tenant_id, str(parcela_id), str(parcela_id)),
    )
    sucessoras = cur.fetchall()
    return {
        "id": p["id"], "tipo": p["tipo"], "codigo": p["codigo"], "ativa": p["ativa"],
        "criada_por": {"codigo": p["criada_por_codigo"], "tipo": p["criada_por_tipo"],
                       "data": p["data_registro"]},
        "retirada_por": ({"codigo": p["retirada_por_codigo"], "tipo": p["retirada_por_tipo"]}
                         if p["retirada_por_codigo"] else None),
        "retirada_em": p["retirada_em"],
        "predecessoras": predecessoras,
        "sucessoras": sucessoras,
    }
