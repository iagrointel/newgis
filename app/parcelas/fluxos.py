"""Fluxos de edição cadastral da malha de parcelas (item L4-parcelas-02-fluxos-cogo): dividir
(por área igual/proporção/largura com rumo, ou por uma linha de corte), unir, recortar,
construir parcelas a partir de linhas (build), sementes (createSeeds/reconstructFromSeeds),
duplicar, mudar tipo e atribuir feições a registro. A fachada REST desses fluxos está em
app/parcelas/rotas.py; os nomes e as formas de entrada seguem a documentação do ParcelFabricServer
(consultada em 08/09/2026; a tabela operação por operação está em docs/PARIDADE_PARCELAS.md §11).

Regras da casa que atravessam tudo (item 01, docs/adr/20260908T2210-parcelas.md):
  * Toda feição nasce e morre POR um registro — os fluxos que criam/retiram exigem registro_id
    (na fachada, o parâmetro `record` da doc). Onde a doc faz o parâmetro opcional, a casa exige
    (divergência declarada em §11).
  * Nada é DELETE: o "apaga" da doc vira RETIRADA (ativa=false + retirada_por_registro).
  * Área calculada é sempre do banco (ST_Area), nunca do chamador.
O corte por rumo varre um meio-plano com busca binária: a área acumulada de um lado é monótona
no deslocamento da reta, então a raiz é única em qualquer polígono (convexo ou não); 64 passos
de bisseção deixam o erro da área de corte muito abaixo do ±0,01 m² do portão.
"""

import math
from typing import Iterable

from app import limites
from app.erros import ErroAPI
from app.parcelas import modelo

SRID = modelo.SRID
OPCOES_DIVIDE = ("ProportionalArea", "EqualArea", "EqualWidth")
OPCOES_CLIP = ("PreserveArea", "DiscardArea", "PreserveBothAreasSplit")
CAMADAS = ("parcela", "linha", "ponto", "conexao")
ESCREVER = ("CreatedByRecord", "RetiredByRecord")
AREA_LASCA_M2 = 0.01  # lascas de flutuante não viram parte (mesma ordem da tolerância de sobreposição)


# ------------------------------------------------------------------ apoio


def _carregar_parcela(cur, tenant_id: int, parcela_id) -> dict:
    cur.execute(
        "SELECT id, tipo, codigo, geom, area_calculada_m2, area_declarada_m2 FROM plat.parcela "
        "WHERE id = %s::uuid AND tenant_id = %s AND ativa",
        (str(parcela_id), tenant_id),
    )
    p = cur.fetchone()
    if p is None:
        raise ErroAPI(404, "nao_encontrado",
                      f"parcela {parcela_id} não existe (ou não está ativa) neste inquilino")
    return p


def _validar_registro(cur, tenant_id: int, registro_id) -> None:
    cur.execute("SELECT 1 FROM plat.parcela_registro WHERE id = %s::uuid AND tenant_id = %s",
                (str(registro_id), tenant_id))
    if cur.fetchone() is None:
        raise ErroAPI(404, "nao_encontrado", f"registro {registro_id} não existe neste inquilino")


def _area_de_wkt(cur, wkt: str) -> float:
    cur.execute("SELECT ST_Area(ST_GeomFromText(%s,%s)) AS a", (wkt, SRID))
    return float(cur.fetchone()["a"])


def _wkt_poligono_unico(cur, wkt: str, o_que: str) -> str:
    """Exige UM polígono (não multi, não vazio). Corte que estilhaça a parcela em pedaços é
    recusado — o fluxo não inventa multiplicidade que o chamador não pediu."""
    cur.execute("SELECT ST_GeometryType(ST_GeomFromText(%s,%s)) AS t", (wkt, SRID))
    t = cur.fetchone()["t"]
    if t != "ST_Polygon":
        raise ErroAPI(422, "valor_invalido",
                      f"{o_que} não resultou em um polígono único (resultado: {t or 'vazio'}); "
                      "refaça com um corte que não estilhe a parcela")
    return wkt


def _associar_linhas(cur, tenant_id: int, parcela_id, wkt: str) -> int:
    """Associa à parcela as linhas ativas que jazem na FRONTEIRA da geometria (ST_Covers da
    fronteira) — é isso que mantém a divisa partilhada partilhada depois do fluxo."""
    cur.execute(
        "WITH ins AS ("
        "  INSERT INTO plat.parcela_linha_parcela(tenant_id, linha_id, parcela_id) "
        "  SELECT %s, l.id, %s::uuid FROM plat.parcela_linha l "
        "  WHERE l.tenant_id = %s AND l.ativa AND ST_Covers(ST_Boundary(ST_GeomFromText(%s,%s)), l.geom) "
        "  ON CONFLICT DO NOTHING RETURNING 1) "
        "SELECT count(*) AS n FROM ins",
        (tenant_id, str(parcela_id), tenant_id, wkt, SRID),
    )
    return int(cur.fetchone()["n"])


# ------------------------------------------------------------------ dividir


class _Varredura:
    """Varredura de meio-plano na direção do rumo sobre UM polígono corrente. `u` é o vetor do
    azimute e `n` a normal à direita; a projeção de um ponto em `n` dá o deslocamento s. A caixa
    "antes" cobre s <= limite e a "depois" cobre s >= limite (retângulos enormes)."""

    def __init__(self, cur, geom_sql, rumo_graus: float, lado_esquerdo: bool):
        self.cur = cur
        self.geom = geom_sql
        teta = math.radians(rumo_graus)
        ux, uy = math.sin(teta), math.cos(teta)
        nx, ny = math.cos(teta), -math.sin(teta)
        cur.execute("SELECT ST_X(g) AS x, ST_Y(g) AS y FROM ST_PointOnSurface(%s::geometry) AS g",
                    (geom_sql,))
        ref = cur.fetchone()
        self.cx, self.cy = float(ref["x"]), float(ref["y"])
        cur.execute("SELECT ST_XMin(g) AS x0, ST_YMin(g) AS y0, ST_XMax(g) AS x1, ST_YMax(g) AS y1 "
                    "FROM (SELECT %s::geometry AS g) s", (geom_sql,))
        bb = cur.fetchone()
        self.m = max(float(bb["x1"]) - float(bb["x0"]), float(bb["y1"]) - float(bb["y0"])) * 2.0 + 1.0

        def proje(x: float, y: float) -> float:
            return (x - self.cx) * nx + (y - self.cy) * ny

        # a projeção extrema de uma caixa está num dos QUATRO cantos (com normal diagonal, os dois
        # cantos "min" e "max" ficam no meio do intervalo) — projetar só dois partiria a varredura
        cantos = [(float(bb["x0"]), float(bb["y0"])), (float(bb["x1"]), float(bb["y0"])),
                  (float(bb["x0"]), float(bb["y1"])), (float(bb["x1"]), float(bb["y1"]))]
        proj = [proje(x, y) for x, y in cantos]
        smin, smax = min(proj), max(proj)
        # divideLeftSide da doc: False espelha a normal, e a varredura passa a começar do outro lado
        if not lado_esquerdo:
            nx, ny = -nx, -ny
            smin, smax = -smax, -smin
        self.n = (nx, ny)
        self.u = (ux, uy)
        self.smin, self.smax = smin, smax

    def _caixa(self, s_limite: float, lado: str) -> str:
        nx, ny = self.n
        ux, uy = self.u
        qx, qy = self.cx + s_limite * nx, self.cy + s_limite * ny
        m = self.m
        if lado == "antes":
            cantos = [(qx - m * ux, qy - m * uy), (qx + m * ux, qy + m * uy),
                      (qx + m * ux - m * nx, qy + m * uy - m * ny),
                      (qx - m * ux - m * nx, qy - m * uy - m * ny)]
        else:
            cantos = [(qx - m * ux, qy - m * uy), (qx + m * ux, qy + m * uy),
                      (qx + m * ux + m * nx, qy + m * uy + m * ny),
                      (qx - m * ux + m * nx, qy - m * uy + m * ny)]
        # o anel fecha REAPROVEITANDO o primeiro ponto (recomputar a quina drifta 1e-14 e o
        # PostGIS recusa anel não fechado)
        cantos.append(cantos[0])
        return "POLYGON((" + ", ".join(repr(x) + " " + repr(y) for x, y in cantos) + "))"

    def _inter(self, caixa_wkt: str):
        cur = self.cur
        cur.execute(
            "SELECT ST_AsText(ST_Intersection(%s::geometry, ST_GeomFromText(%s,%s))) AS wkt, "
            "       ST_Area(ST_Intersection(%s::geometry, ST_GeomFromText(%s,%s))) AS a",
            (self.geom, caixa_wkt, SRID, self.geom, caixa_wkt, SRID))
        return cur.fetchone()

    def area_antes(self, s_limite: float) -> float:
        return float(self._inter(self._caixa(s_limite, "antes"))["a"])

    def fatia(self, s_de: float, s_ate: float) -> tuple[str, float]:
        """Pedago s_de < s <= s_ate do polígono corrente: (wkt, área)."""
        cur = self.cur
        r = self._inter(self._caixa(s_ate, "antes"))
        if s_de is not None and s_de > self.smin:
            cur.execute(
                "SELECT ST_AsText(ST_Difference(ST_GeomFromText(%s,%s), ST_GeomFromText(%s,%s))) AS wkt",
                (r["wkt"], SRID, self._caixa(s_de, "antes"), SRID))
            wkt = cur.fetchone()["wkt"]
            a = self._area_de(wkt)
        else:
            wkt, a = r["wkt"], float(r["a"])
        return wkt, a

    def _area_de(self, wkt: str) -> float:
        self.cur.execute("SELECT ST_Area(ST_GeomFromText(%s,%s)) AS a", (wkt, SRID))
        return float(self.cur.fetchone()["a"])

    def subtrair(self, wkt: str) -> float:
        """Tira a fatia do polígono corrente; devolve a área que sobrou."""
        self.cur.execute(
            "SELECT ST_AsEWKT(d) AS wkt, ST_Area(d) AS a FROM "
            "(SELECT ST_Difference(%s::geometry, ST_GeomFromText(%s,%s)) AS d) s",
            (self.geom, wkt, SRID))
        # EWKT e não WKT: o polígono corrente volta a entrar por %s::geometry nas operações
        # seguintes, e WKT solto perde o SRID (o banco recusa mistura 0 != 31982)
        r = self.cur.fetchone()
        self.geom = r["wkt"]
        return float(r["a"])


def dividir(cur, tenant_id: int, *, parcela_id, registro_id, rumo_graus: float,
            opcao: str = "ProportionalArea", numero_de_partes: int = 2,
            parte_area_ou_largura: float = 0.0, lado_esquerdo: bool = True,
            distribuir_restante: bool = False, tipo: str | None = None,
            prefixo_codigo: str | None = None) -> list[dict]:
    """Divide a parcela com retas paralelas na direção do rumo (azimute 0-360). divideOption da
    doc, mapa da casa: ProportionalArea = partes iguais em proporção (N partes); EqualArea = cada
    parte com dividePartAreaOrWidth m² (0 = N partes iguais); EqualWidth = faixas de
    dividePartAreaOrWidth m. A sobra que não fecha parte inteira vira a ÚLTIMA parte
    (divideDistributeRemainder=false da doc; true nas N partes iguais de EqualArea)."""
    if opcao not in OPCOES_DIVIDE:
        raise ErroAPI(422, "tipo_invalido", f"divideOption precisa ser um de: {', '.join(OPCOES_DIVIDE)}")
    rumo = float(rumo_graus)
    if not (0 <= rumo < 360):
        raise ErroAPI(422, "valor_invalido", "divideLineBearing é azimute em graus (0-360)")
    n_partes = int(numero_de_partes)
    if n_partes < 2:
        raise ErroAPI(422, "valor_invalido", "divideNumberOfParts precisa de pelo menos 2")
    if n_partes > limites.PARCELA_DIVIDE_PARTES_MAX:
        raise ErroAPI(422, "regras_demais",
                      f"o teto são {limites.PARCELA_DIVIDE_PARTES_MAX} partes por divisão")
    parte = float(parte_area_ou_largura)
    if opcao == "ProportionalArea" and parte != 0.0:
        raise ErroAPI(422, "valor_invalido", "em ProportionalArea o dividePartAreaOrWidth vale 0")
    if opcao == "EqualWidth" and parte <= 0:
        raise ErroAPI(422, "valor_invalido", "EqualWidth precisa de dividePartAreaOrWidth > 0")
    # EqualArea com 0 = N partes iguais (divideNumberOfParts); com área > 0, cada parte sai com
    # essa área e a sobra vira a última parte

    p = _carregar_parcela(cur, tenant_id, parcela_id)
    _validar_registro(cur, tenant_id, registro_id)
    tipo_final = tipo or p["tipo"]
    if tipo_final not in modelo.TIPOS:
        raise ErroAPI(422, "tipo_invalido",
                      f"tipo de parcela precisa ser um de: {', '.join(modelo.TIPOS)}")
    prefixo = prefixo_codigo or p["codigo"]

    cur.execute("SELECT ST_Area(%s::geometry) AS a", (p["geom"],))
    area_total = float(cur.fetchone()["a"])
    varredura = _Varredura(cur, p["geom"], rumo, lado_esquerdo)

    partes: list[tuple[str, float | None]] = []  # (wkt, área declarada)
    if opcao == "EqualWidth":
        s_de = varredura.smin
        while len(partes) < limites.PARCELA_DIVIDE_PARTES_MAX:
            s_ate = min(s_de + parte, varredura.smax)
            wkt, a = varredura.fatia(s_de if partes else None, s_ate)
            if a <= AREA_LASCA_M2:
                break
            partes.append((_wkt_poligono_unico(cur, wkt, "parte da divisão"), None))
            if varredura.subtrair(wkt) <= AREA_LASCA_M2:
                break
            s_de = s_ate
    else:
        if opcao == "ProportionalArea":
            alvo, declarada, resto = area_total / n_partes, None, True
        elif parte <= 0 or distribuir_restante:
            alvo, declarada, resto = area_total / n_partes, area_total / n_partes, False
        else:
            alvo, declarada, resto = parte, parte, True
        while len(partes) < limites.PARCELA_DIVIDE_PARTES_MAX:
            restante = varredura.area_antes(varredura.smax)
            if restante <= AREA_LASCA_M2:
                break
            if resto:
                alvo_real = min(alvo, restante)
            else:
                alvo_real = alvo
            if restante - alvo_real <= AREA_LASCA_M2:
                break  # o que sobra É a última parte: nada mais a cortar
            # bisseção no deslocamento: área acumulada é monótona, a raiz é única
            lo, hi = varredura.smin, varredura.smax
            for _ in range(64):
                meio = (lo + hi) / 2.0
                if varredura.area_antes(meio) < alvo_real:
                    lo = meio
                else:
                    hi = meio
            wkt, _a = varredura.fatia(None, (lo + hi) / 2.0)
            partes.append((_wkt_poligono_unico(cur, wkt, "parte da divisão"), declarada))
            varredura.subtrair(wkt)
        # a última parte é o que ficou; em partes iguais (resto=False) ela É uma parte de alvo,
        # então a área declarada dela é o alvo também (não fica sem declarar a última)
        cur.execute("SELECT ST_AsText(%s::geometry) AS wkt", (varredura.geom,))
        wkt_resto = cur.fetchone()["wkt"]
        if _area_de_wkt(cur, wkt_resto) > AREA_LASCA_M2:
            partes.append((_wkt_poligono_unico(cur, wkt_resto, "parte da divisão"),
                           None if resto else alvo))

    if len(partes) < 2:
        raise ErroAPI(422, "valor_invalido",
                      f"o corte separou {len(partes)} parte(s); a divisão precisa de 2 ou mais")

    saida: list[dict] = []
    for i, (wkt, declarada) in enumerate(partes):
        saida.append(modelo.criar_parcela(
            cur, tenant_id, tipo=tipo_final, codigo=f"{prefixo}-{i + 1:02d}", registro_id=registro_id,
            wkt=wkt, area_declarada_m2=declarada,
            atributos={"fluxo": "divide", "divideOption": opcao, "rumo_graus": round(rumo, 6)},
        ))
        _associar_linhas(cur, tenant_id, saida[-1]["id"], wkt)
    modelo.retirar_parcela(cur, tenant_id, parcela_id=parcela_id, registro_id=registro_id)
    return saida


def dividir_por_linha(cur, tenant_id: int, *, parcela_id, registro_id,
                      linha: Iterable[tuple], tipo: str | None = None) -> list[dict]:
    """Divide a parcela por uma linha de corte. A REFUTAÇÃO DO ITEM mora aqui: linha que NÃO cruza
    a parcela é recusada com 422 linha_nao_cruza — nunca divisão em silêncio. A casa aceita corte
    RETO de 2 pontos (a referência aceita polilinha — divergência declarada §11)."""
    pts = [(float(x), float(y)) for x, y in linha]
    if len(pts) != 2:
        raise ErroAPI(422, "valor_invalido", "a linha de corte precisa de exatamente 2 pontos")
    p = _carregar_parcela(cur, tenant_id, parcela_id)
    _validar_registro(cur, tenant_id, registro_id)
    wkt_linha = "LINESTRING(" + ", ".join(f"{x} {y}" for x, y in pts) + ")"
    cur.execute("SELECT ST_Crosses(%s::geometry, ST_GeomFromText(%s,%s)) AS cruza",
                (p["geom"], wkt_linha, SRID))
    if not cur.fetchone()["cruza"]:
        raise ErroAPI(422, "linha_nao_cruza", "a linha de corte não cruza a parcela — divisão recusada")
    cur.execute("SELECT ST_AsText(d.g) AS g, ST_GeometryType(d.g) AS t FROM "
                "(SELECT (ST_Dump(ST_Split(%s::geometry, ST_GeomFromText(%s,%s)))).geom AS g) d",
                (p["geom"], wkt_linha, SRID))
    pedacos = [_wkt_poligono_unico(cur, r["g"], "parte da divisão") for r in cur.fetchall()
               if r["t"] == "ST_Polygon"]
    pedacos = [w for w in pedacos if _area_de_wkt(cur, w) > AREA_LASCA_M2]
    if len(pedacos) != 2:
        raise ErroAPI(422, "valor_invalido",
                      f"o corte separou {len(pedacos)} pedaço(s) aproveitável(is) (esperado 2); "
                      "refaça a linha de corte")
    tipo_final = tipo or p["tipo"]
    if tipo_final not in modelo.TIPOS:
        raise ErroAPI(422, "tipo_invalido",
                      f"tipo de parcela precisa ser um de: {', '.join(modelo.TIPOS)}")
    criadas = []
    for i, wkt in enumerate(pedacos):
        criadas.append(modelo.criar_parcela(
            cur, tenant_id, tipo=tipo_final, codigo=f"{p['codigo']}-{'AB'[i]}", registro_id=registro_id,
            wkt=wkt, atributos={"fluxo": "divide", "divideOption": "linha"},
        ))
        _associar_linhas(cur, tenant_id, criadas[-1]["id"], wkt)
    modelo.retirar_parcela(cur, tenant_id, parcela_id=parcela_id, registro_id=registro_id)
    return criadas


# ------------------------------------------------------------------ unir


def unir(cur, tenant_id: int, *, parcela_ids: Iterable, registro_id, codigo: str | None = None,
         tipo: str | None = None) -> dict:
    """Une 2+ parcelas contíguas: cria a parcela da união e retira as originais. As linhas
    EXTERNAS continuam ativas e passam a servir a unida; a divisa INTERNA (que só servia às
    originais) é RETIRADA pelo cascade da retirada — o "apaga a interna" da doc é retirada aqui
    (a casa não apaga; paridade §11). União descontínua é recusada."""
    ids = [str(i) for i in parcela_ids]
    if len(ids) < 2:
        raise ErroAPI(422, "valor_invalido", "unir precisa de pelo menos 2 parcelas")
    if len(ids) > limites.PARCELA_UNIR_MAX:
        raise ErroAPI(422, "regras_demais",
                      f"o teto são {limites.PARCELA_UNIR_MAX} parcelas por união")
    _validar_registro(cur, tenant_id, registro_id)
    origens = [_carregar_parcela(cur, tenant_id, pid) for pid in ids]
    tipos = {o["tipo"] for o in origens}
    tipo_final = tipo or (tipos.pop() if len(tipos) == 1 else None)
    if tipo_final is None:
        raise ErroAPI(422, "valor_invalido",
                      "as parcelas têm tipos diferentes: declare targetParcelType (tipo) da união")
    if tipo_final not in modelo.TIPOS:
        raise ErroAPI(422, "tipo_invalido",
                      f"tipo de parcela precisa ser um de: {', '.join(modelo.TIPOS)}")
    cur.execute("SELECT ST_AsText(ST_UnaryUnion(ST_Collect(g))) AS wkt "
                "FROM (SELECT unnest(%s::geometry[]) AS g) s",
                ([o["geom"] for o in origens],))
    wkt_uniao = _wkt_poligono_unico(cur, cur.fetchone()["wkt"], "união")
    unida = modelo.criar_parcela(
        cur, tenant_id, tipo=tipo_final, codigo=codigo or origens[0]["codigo"],
        registro_id=registro_id, wkt=wkt_uniao, area_declarada_m2=None,
        atributos={"fluxo": "merge", "origens": ids},
    )
    # 1) a unida nasce e ASSOCIA as linhas externas (fronteira da união) ANTES da retirada das
    #    originais — é isso que as salva do cascade da retirada;
    _associar_linhas(cur, tenant_id, unida["id"], wkt_uniao)
    # 2) as originais são retiradas; a divisa interna, que só servia a elas, é retirada junto.
    for o in origens:
        modelo.retirar_parcela(cur, tenant_id, parcela_id=o["id"], registro_id=registro_id)
    return unida


# ------------------------------------------------------------------ recortar


def recortar(cur, tenant_id: int, *, parcela_id, registro_id, opcao: str,
             geometria_wkt: str | None = None, parcela_recorte_id=None,
             codigo: str | None = None) -> dict:
    """Recorta a parcela com um polígono (clippingGeometry OU clippingParcels da doc — um dos
    dois). Casa: PreserveArea = a interseção vira parcela nova e o pai fica com o resto (sem
    resto, o pai é retirado); DiscardArea = o pai fica com o resto e a interseção é descartada;
    PreserveBothAreasSplit = o pai é retirado e nascem a interseção e o resto."""
    if opcao not in OPCOES_CLIP:
        raise ErroAPI(422, "tipo_invalido", f"clipOption precisa ser um de: {', '.join(OPCOES_CLIP)}")
    if (geometria_wkt is None) == (parcela_recorte_id is None):
        raise ErroAPI(422, "valor_invalido", "informe clippingGeometry OU clippingParcels (um dos dois)")
    p = _carregar_parcela(cur, tenant_id, parcela_id)
    _validar_registro(cur, tenant_id, registro_id)
    if parcela_recorte_id is not None:
        c = _carregar_parcela(cur, tenant_id, parcela_recorte_id)
        cur.execute("SELECT ST_AsText(%s::geometry) AS wkt", (c["geom"],))
        geometria_wkt = cur.fetchone()["wkt"]
    cur.execute(
        "SELECT ST_AsText(ST_Intersection(%s::geometry, ST_GeomFromText(%s,%s))) AS inter, "
        "       ST_AsText(ST_Difference(%s::geometry, ST_GeomFromText(%s,%s))) AS dife",
        (p["geom"], geometria_wkt, SRID, p["geom"], geometria_wkt, SRID),
    )
    r = cur.fetchone()
    area_inter = _area_de_wkt(cur, r["inter"]) if r["inter"] else 0.0
    area_dife = _area_de_wkt(cur, r["dife"]) if r["dife"] else 0.0

    adds: list[dict] = []
    if opcao in ("PreserveArea", "PreserveBothAreasSplit"):
        if area_inter <= AREA_LASCA_M2:
            raise ErroAPI(422, "valor_invalido", "o recorte não captura área nenhuma da parcela")
        wkt_inter = _wkt_poligono_unico(cur, r["inter"], "parte do recorte")
        adds.append(modelo.criar_parcela(
            cur, tenant_id, tipo=p["tipo"], codigo=codigo or f"{p['codigo']}-R", registro_id=registro_id,
            wkt=wkt_inter, atributos={"fluxo": "clip", "clipOption": opcao},
        ))
        _associar_linhas(cur, tenant_id, adds[-1]["id"], wkt_inter)

    atualizado = None
    if opcao == "PreserveBothAreasSplit":
        modelo.retirar_parcela(cur, tenant_id, parcela_id=p["id"], registro_id=registro_id)
        if area_dife > AREA_LASCA_M2:
            wkt_dife = _wkt_poligono_unico(cur, r["dife"], "parte do recorte")
            adds.append(modelo.criar_parcela(
                cur, tenant_id, tipo=p["tipo"], codigo=f"{p['codigo']}-S", registro_id=registro_id,
                wkt=wkt_dife, atributos={"fluxo": "clip", "clipOption": opcao},
            ))
            _associar_linhas(cur, tenant_id, adds[-1]["id"], wkt_dife)
    elif area_dife > AREA_LASCA_M2:
        # o pai CONTINUA (mesma feição, mesma identidade) com o resto: atualização no lugar
        wkt_dife = _wkt_poligono_unico(cur, r["dife"], "parte do recorte")
        cur.execute(
            "UPDATE plat.parcela SET geom = ST_GeomFromText(%s,%s), "
            "area_calculada_m2 = ST_Area(ST_GeomFromText(%s,%s)), atualizado_em = now() "
            "WHERE id = %s::uuid AND tenant_id = %s RETURNING " + modelo._COLUNAS_PARCELA,
            (wkt_dife, SRID, wkt_dife, SRID, str(p["id"]), tenant_id),
        )
        atualizado = cur.fetchone()
        _associar_linhas(cur, tenant_id, p["id"], wkt_dife)
    else:
        # sem resto: o recorte consumiu a parcela inteira
        modelo.retirar_parcela(cur, tenant_id, parcela_id=p["id"], registro_id=registro_id)
    return {"adds": adds, "atualizado": atualizado}


# ------------------------------------------------------------------ build e sementes


def _linhas_livres(cur, tenant_id: int, registro_id=None, extent: dict | None = None) -> tuple:
    """Linhas ativas SEM parcela ativa (a matéria-prima do build), filtradas por registro e pela
    caixa extent ({xmin,ymin,xmax,ymax}). Devolve o ST_Collect e a contagem."""
    filtro = ""
    args: list = [tenant_id]
    if registro_id is not None:
        filtro += " AND l.criada_por_registro = %s::uuid"
        args.append(str(registro_id))
    if extent is not None:
        xmin, ymin, xmax, ymax = (float(extent[k]) for k in ("xmin", "ymin", "xmax", "ymax"))
        filtro += " AND l.geom && ST_MakeEnvelope(%s,%s,%s,%s,%s)"
        args += [xmin, ymin, xmax, ymax, SRID]
    cur.execute(
        "SELECT ST_Collect(l.geom) AS g, count(*) AS n FROM plat.parcela_linha l "
        "WHERE l.tenant_id = %s AND l.ativa AND NOT EXISTS ("
        "  SELECT 1 FROM plat.parcela_linha_parcela u JOIN plat.parcela p ON p.id = u.parcela_id "
        "  WHERE u.linha_id = l.id AND p.ativa)" + filtro,
        args,
    )
    r = cur.fetchone()
    return r["g"], int(r["n"])


def _faces(cur, colecao, extent: dict | None = None) -> list[str]:
    """Fecha os anéis das linhas (ST_Polygonize) e devolve os WKT das faces. Sem face fechada não
    é erro: quem chama devolve contagem zero."""
    if colecao is None:
        return []
    filtro = ""
    args: list = [colecao]
    if extent is not None:
        xmin, ymin, xmax, ymax = (float(extent[k]) for k in ("xmin", "ymin", "xmax", "ymax"))
        filtro = " WHERE ST_Intersects(d.g, ST_MakeEnvelope(%s,%s,%s,%s,%s))"
        args += [xmin, ymin, xmax, ymax, SRID]
    cur.execute(
        "SELECT ST_AsText(d.g) AS wkt FROM (SELECT (ST_Dump(ST_Polygonize(%s::geometry))).geom AS g) d"
        + filtro,
        args,
    )
    return [r["wkt"] for r in cur.fetchall()]


def construir(cur, tenant_id: int, *, registro_id, tipo: str = "lote", extent: dict | None = None,
              prefixo: str = "B") -> list[dict]:
    """Build: fecha anéis com as linhas livres e cria UMA parcela por face. O registro é
    obrigatório na casa (a doc o faz opcional — divergência declarada §11). Face com semente
    ativa fica de fora (é da reconstructFromSeeds)."""
    tipo = tipo or "lote"  # sem declaração, a face vira lote (o padrão da casa)
    if tipo not in modelo.TIPOS:
        raise ErroAPI(422, "tipo_invalido",
                      f"tipo de parcela precisa ser um de: {', '.join(modelo.TIPOS)}")
    _validar_registro(cur, tenant_id, registro_id)
    colecao, n_linhas = _linhas_livres(cur, tenant_id, registro_id, extent)
    if n_linhas == 0:
        return []
    if n_linhas > limites.PARCELA_BUILD_LINHAS_MAX:
        raise ErroAPI(422, "regras_demais",
                      f"o teto são {limites.PARCELA_BUILD_LINHAS_MAX} linhas por build (há {n_linhas})")
    faces = _faces(cur, colecao, extent)
    if len(faces) > limites.PARCELA_BUILD_FACES_MAX:
        raise ErroAPI(422, "regras_demais",
                      f"o teto são {limites.PARCELA_BUILD_FACES_MAX} faces por build (achou {len(faces)})")
    criadas = []
    for i, wkt in enumerate(faces):
        if _area_de_wkt(cur, wkt) <= AREA_LASCA_M2:
            continue
        cur.execute(
            "SELECT 1 FROM plat.parcela_semente s WHERE s.tenant_id = %s AND s.ativa "
            "AND ST_Intersects(s.geom, ST_GeomFromText(%s,%s)) LIMIT 1",
            (tenant_id, wkt, SRID),
        )
        if cur.fetchone() is not None:
            continue  # face com semente: é da reconstructFromSeeds, não do build
        criadas.append(modelo.criar_parcela(
            cur, tenant_id, tipo=tipo, codigo=f"{prefixo}-{i + 1:05d}", registro_id=registro_id,
            wkt=wkt, atributos={"fluxo": "build"},
        ))
        _associar_linhas(cur, tenant_id, criadas[-1]["id"], wkt)
    return criadas


def criar_sementes(cur, tenant_id: int, *, registro_id, extent: dict | None = None) -> list[dict]:
    """createSeeds: uma semente por face fechada pelas linhas do registro (a doc exige registro; a
    casa também). A semente guarda a face inteira; quem a consome é a reconstructFromSeeds."""
    import psycopg2.extras

    _validar_registro(cur, tenant_id, registro_id)
    colecao, n_linhas = _linhas_livres(cur, tenant_id, registro_id, extent)
    if n_linhas == 0:
        return []
    criadas = []
    for wkt in _faces(cur, colecao, extent):
        if _area_de_wkt(cur, wkt) <= AREA_LASCA_M2:
            continue
        cur.execute(
            "INSERT INTO plat.parcela_semente(tenant_id, geom, criada_por_registro, atributos) "
            "VALUES (%s, ST_GeomFromText(%s,%s), %s::uuid, %s) RETURNING id",
            (tenant_id, wkt, SRID, str(registro_id), psycopg2.extras.Json({"fluxo": "createSeeds"})),
        )
        criadas.append({"id": str(cur.fetchone()["id"]), "wkt": wkt})
    return criadas


def reconstruir_de_sementes(cur, tenant_id: int, *, registro_id, extent: dict) -> dict:
    """reconstructFromSeeds: para cada semente ativa dentro da extent, acha a face fechada pelas
    linhas livres que a contém, RETIRA a semente e cria a parcela no mesmo lugar. A doc não pede
    registro (a parcela herda a associação das linhas); a casa exige, porque toda feição nasce e
    morre por um registro (divergência declarada §11). Devolve a contagem — o
    reconstructedParcelCount da doc."""
    if extent is None:
        raise ErroAPI(422, "valor_invalido", "reconstructFromSeeds precisa da extent")
    xmin, ymin, xmax, ymax = (float(extent[k]) for k in ("xmin", "ymin", "xmax", "ymax"))
    _validar_registro(cur, tenant_id, registro_id)
    cur.execute(
        "SELECT s.id, s.geom FROM plat.parcela_semente s WHERE s.tenant_id = %s AND s.ativa "
        "AND s.geom && ST_MakeEnvelope(%s,%s,%s,%s,%s)",
        (tenant_id, xmin, ymin, xmax, ymax, SRID),
    )
    sementes = cur.fetchall()
    if not sementes:
        return {"count": 0, "criadas": []}
    colecao, n_linhas = _linhas_livres(cur, tenant_id, None, extent)
    faces = _faces(cur, colecao, extent) if n_linhas else []
    criadas = []
    for s in sementes:
        wkt_face = None
        for wkt in faces:
            cur.execute(
                "SELECT ST_Contains(ST_GeomFromText(%s,%s), ST_PointOnSurface(%s::geometry)) AS dentro",
                (wkt, SRID, s["geom"]))
            if cur.fetchone()["dentro"]:
                wkt_face = wkt
                break
        if wkt_face is None:
            continue  # semente sem face fechada: fica para a próxima rodada
        if _area_de_wkt(cur, wkt_face) <= AREA_LASCA_M2:
            continue
        cur.execute(
            "UPDATE plat.parcela_semente SET ativa = false, retirada_por_registro = %s::uuid, "
            "retirada_em = now(), atualizado_em = now() WHERE id = %s::uuid AND tenant_id = %s",
            (str(registro_id), str(s["id"]), tenant_id),
        )
        criadas.append(modelo.criar_parcela(
            cur, tenant_id, tipo="lote", codigo=f"S-{len(criadas) + 1:05d}", registro_id=registro_id,
            wkt=wkt_face, atributos={"fluxo": "reconstructFromSeeds", "semente": str(s["id"])},
        ))
        _associar_linhas(cur, tenant_id, criadas[-1]["id"], wkt_face)
    return {"count": len(criadas), "criadas": criadas}


# ------------------------------------------------------------------ duplicar, mudar tipo, atribuir


def duplicar(cur, tenant_id: int, *, parcela_id, registro_id, codigo: str,
             tipo: str | None = None) -> dict:
    """Duplicar: cópia da geometria e dos atributos em parcela NOVA, pelo registro. As linhas
    continuam partilhadas com a original (a associação é n:n; cópia não desdobra linha)."""
    p = _carregar_parcela(cur, tenant_id, parcela_id)
    _validar_registro(cur, tenant_id, registro_id)
    tipo_final = tipo or p["tipo"]
    if tipo_final not in modelo.TIPOS:
        raise ErroAPI(422, "tipo_invalido",
                      f"tipo de parcela precisa ser um de: {', '.join(modelo.TIPOS)}")
    cur.execute("SELECT ST_AsText(%s::geometry) AS wkt", (p["geom"],))
    wkt = cur.fetchone()["wkt"]
    copia = modelo.criar_parcela(
        cur, tenant_id, tipo=tipo_final, codigo=codigo, registro_id=registro_id, wkt=wkt,
        area_declarada_m2=p["area_declarada_m2"],
        atributos={"fluxo": "duplicar", "origem": str(p["id"])},
    )
    _associar_linhas(cur, tenant_id, copia["id"], wkt)
    return copia


def mudar_tipo(cur, tenant_id: int, *, parcela_id, tipo: str) -> dict:
    """Mudar tipo é EDIÇÃO DE ATRIBUTO: a feição continua a mesma, sem nascer nem morrer
    (divergência declarada §11 — na referência a feição MIGRA de classe de feição)."""
    if tipo not in modelo.TIPOS:
        raise ErroAPI(422, "tipo_invalido",
                      f"tipo de parcela precisa ser um de: {', '.join(modelo.TIPOS)}")
    _carregar_parcela(cur, tenant_id, parcela_id)
    cur.execute(
        "UPDATE plat.parcela SET tipo = %s, atualizado_em = now() "
        "WHERE id = %s::uuid AND tenant_id = %s RETURNING " + modelo._COLUNAS_PARCELA,
        (tipo, str(parcela_id), tenant_id),
    )
    return cur.fetchone()


def atribuir_a_registro(cur, tenant_id: int, *, pares: list[dict], registro_id,
                        escrever: str = "CreatedByRecord") -> dict:
    """assignFeaturesToRecord: atribui feições a um registro. writeAttribute da doc:
    CreatedByRecord | RetiredByRecord. layerId da doc vira camada da casa: parcela | linha |
    ponto | conexao. RetiredByRecord RETIRA (ativa=false + registro + instante) — nunca apaga.
    Ponto não tem retirada por registro (item 01, decisão 2): fica inativo, declarado."""
    if escrever not in ESCREVER:
        raise ErroAPI(422, "tipo_invalido", f"writeAttribute precisa ser um de: {', '.join(ESCREVER)}")
    _validar_registro(cur, tenant_id, registro_id)
    if not pares:
        raise ErroAPI(422, "valor_invalido", "parcelFeatures vazio")
    if len(pares) > limites.PARCELA_ATRIBUICAO_MAX:
        raise ErroAPI(422, "regras_demais",
                      f"o teto são {limites.PARCELA_ATRIBUICAO_MAX} feições por atribuição")
    retirar = escrever == "RetiredByRecord"
    feitos: list[dict] = []
    for par in pares:
        camada = par.get("layerId")
        fid = str(par.get("id"))
        if camada not in CAMADAS:
            raise ErroAPI(422, "tipo_invalido", f"layerId precisa ser um de: {', '.join(CAMADAS)}")
        if retirar and camada == "parcela":
            cur.execute(
                "SELECT 1 FROM plat.parcela WHERE id = %s::uuid AND tenant_id = %s "
                "AND criada_por_registro = %s::uuid",
                (fid, tenant_id, str(registro_id)),
            )
            if cur.fetchone() is not None:
                raise ErroAPI(422, "valor_invalido",
                              "a parcela foi criada por este registro: retirada por ele mesmo é proibida")
        if camada == "parcela":
            if retirar:
                sql = ("UPDATE plat.parcela SET retirada_por_registro = %s::uuid, ativa = false, "
                       "retirada_em = now(), atualizado_em = now() "
                       "WHERE id = %s::uuid AND tenant_id = %s RETURNING id")
            else:
                sql = ("UPDATE plat.parcela SET criada_por_registro = %s::uuid, atualizado_em = now() "
                       "WHERE id = %s::uuid AND tenant_id = %s RETURNING id")
            args = [str(registro_id)]
        elif camada == "linha":
            if retirar:
                sql = ("UPDATE plat.parcela_linha SET retirada_por_registro = %s::uuid, ativa = false, "
                       "atualizado_em = now() WHERE id = %s::uuid AND tenant_id = %s RETURNING id")
            else:
                sql = ("UPDATE plat.parcela_linha SET criada_por_registro = %s::uuid, atualizado_em = now() "
                       "WHERE id = %s::uuid AND tenant_id = %s RETURNING id")
            args = [str(registro_id)]
        elif camada == "ponto":
            if retirar:
                sql = ("UPDATE plat.parcela_ponto SET ativa = false, atualizado_em = now() "
                       "WHERE id = %s::uuid AND tenant_id = %s RETURNING id")
                args = []
            else:
                sql = ("UPDATE plat.parcela_ponto SET criada_por_registro = %s::uuid, atualizado_em = now() "
                       "WHERE id = %s::uuid AND tenant_id = %s RETURNING id")
                args = [str(registro_id)]
        else:
            if retirar:
                sql = ("UPDATE plat.parcela_conexao SET retirada_por_registro = %s::uuid, ativa = false, "
                       "atualizado_em = now() WHERE id = %s::uuid AND tenant_id = %s RETURNING id")
            else:
                sql = ("UPDATE plat.parcela_conexao SET criada_por_registro = %s::uuid, atualizado_em = now() "
                       "WHERE id = %s::uuid AND tenant_id = %s RETURNING id")
            args = [str(registro_id)]
        args += [fid, tenant_id]
        cur.execute(sql, args)
        r = cur.fetchone()
        if r is None:
            raise ErroAPI(404, "nao_encontrado", f"feição {fid} ({camada}) não existe neste inquilino")
        feitos.append({"id": str(r["id"]), "layerId": camada})
    return {"feitos": feitos, "writeAttribute": escrever}
