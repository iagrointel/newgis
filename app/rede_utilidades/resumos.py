"""Sumário por subrede (item L4-04-c-sumarios-por-subrede; ADR 20260907T2243).

O item irmão L4-04-a registra a subrede e guarda, em `plat.rede_subrede.resumo`, o que a ATUALIZAÇÃO fez
(quantos elementos o traçado alcançou, em quanto tempo). Aqui a pergunta é outra: quanto tem esta subrede.
Quilômetro por nível de tensão, transformadores e potência instalada, unidades consumidoras por classe,
energia anual faturada, dispositivos por categoria de rede, geração distribuída ligada e comprimento do
tronco. Uma linha por subrede em `plat.rede_subrede_resumo`, servida como tabela e como CSV
(subnetworks-table.htm: a tabela de subredes é objeto consultável, não relatório de tela).

DE ONDE VEM A FILIAÇÃO DE CADA ELEMENTO À SUBREDE. Do atributo que o arquivo usa para dizer a que subrede o
elemento pertence, declarado por tier em `ATRIBUTO_DE_SUBREDE_POR_TIER`. No pacote elétrico brasileiro
(BDGD Módulo 10) o tier de média tensão usa `ctmt` (o código do alimentador, que a distribuidora escreve em
cada trecho, transformador e unidade consumidora) e o de baixa tensão usa `uni_tr_mt` (o transformador de
onde a baixa tensão sai). É a MESMA convenção que `controladores.marcar_da_importacao` usa para nomear as
subredes: lá o nome da subrede de média tensão É o `ctmt`, e o da subrede de baixa tensão É o código do
transformador.

⛔ Isto é o que o ARQUIVO DECLARA, não o que a topologia alcança. Um trecho fisicamente ligado ao
alimentador vizinho, mas com o `ctmt` do primeiro escrito no cadastro, entra no sumário do primeiro. Esta
escolha é deliberada e é a razão de o sumário existir: ele é o retrato do cadastro, comparável com o que a
distribuidora declara ao regulador. A conferência contra o traçado topológico é o item L4-04-b, que grava
os elementos alcançados em `plat.rede_subrede_elemento`; quando essa tabela existir, a divergência entre as
duas leituras é o achado, e nenhuma das duas some.

UNIDADE DO COMPRIMENTO E DA ENERGIA (item L4-01-e). O dicionário do pacote declara COMP em quilômetro e
ENE_SUM em megawatt-hora, mas o arquivo de cada distribuidora pode vir em metro e em quilowatt-hora — e o
extrato de referência da casa vem. Por isso este sumário NÃO usa a unidade do dicionário: pede a
`unidades.fatores_da_rede` a unidade que a importação MEDIU no arquivo e converte com o fator de lá. A
origem (medida no arquivo ou declarada pelo dicionário, quando a rede não tem importação registrada) sai
na coluna `unidades` de cada linha, para que ninguém confunda medido com suposto.

COMPRIMENTO DECLARADO x COMPRIMENTO GEOMÉTRICO. Cada trecho traz o comprimento que o cadastro declara
(atributo `comp`) e tem a geometria carregada. Os dois são somados e guardados lado a lado, com a diferença
em porcento: é medida de qualidade de cadastro, e some se guardarmos só um dos dois.

TRONCO. `tronco_max_m` é a maior distância, andando pela rede, entre um controlador da subrede e um ponto
alcançável dela — o comprimento do tronco no sentido operacional (o quanto a subrede se estende a partir da
fonte). Exige topologia construída e controlador com nó; sem isso a coluna fica nula e `tronco_origem` diz
qual das duas faltou, em vez de gravar zero e parecer medida."""

import csv
import io
import json
import time
from heapq import heappop, heappush

from app.erros import ErroAPI
from app.rede_utilidades import unidades as unidades_mod

# Atributo que carrega o nome da subrede, por código de tier do pacote (ver docstring). Tier fora desta
# tabela não tem como filiar elemento nenhum e é recusado dizendo isso.
ATRIBUTO_DE_SUBREDE_POR_TIER = {
    "media_tensao": "ctmt",
    "baixa_tensao": "uni_tr_mt",
}
ATRIBUTO_COMPRIMENTO = "comp"          # comprimento do trecho declarado no cadastro
ATRIBUTO_POTENCIA_TRAFO = "pot_nom"    # potência nominal do transformador, em kVA
ATRIBUTO_CLASSE_UC = "clas_sub"        # classe/subclasse da unidade consumidora
ATRIBUTO_ENERGIA = "ene"               # energia anual faturada da unidade consumidora
ATRIBUTO_POTENCIA_GD = "pot"           # potência da geração distribuída, em kW

GRUPO_TRAFO = "transformador_de_distribuicao"
GRUPO_UC = "unidade_consumidora"
GRUPO_GD = "geracao_distribuida"

# As colunas da tabela, na ordem em que a tabela e o CSV as mostram. É a descrição que um painel liga a um
# elemento (nome para o rótulo, tipo para o formato, unidade para o eixo) — por isso vive aqui, ao lado do
# cálculo, e não escrita à mão na tela.
COLUNAS = (
    {"codigo": "subrede", "nome": "Subrede", "tipo": "texto", "unidade": None},
    {"codigo": "tier", "nome": "Tier", "tipo": "texto", "unidade": None},
    {"codigo": "elementos", "nome": "Elementos", "tipo": "inteiro", "unidade": None},
    {"codigo": "km_declarado", "nome": "Extensão declarada", "tipo": "real", "unidade": "km"},
    {"codigo": "km_geometria", "nome": "Extensão pela geometria", "tipo": "real", "unidade": "km"},
    {"codigo": "divergencia_pct", "nome": "Diferença declarado x geometria", "tipo": "real", "unidade": "%"},
    {"codigo": "trafos", "nome": "Transformadores", "tipo": "inteiro", "unidade": None},
    {"codigo": "kva_instalado", "nome": "Potência instalada", "tipo": "real", "unidade": "kVA"},
    {"codigo": "ucs", "nome": "Unidades consumidoras", "tipo": "inteiro", "unidade": None},
    {"codigo": "energia_anual_kwh", "nome": "Energia anual faturada", "tipo": "real", "unidade": "kWh"},
    {"codigo": "gd_unidades", "nome": "Geração distribuída", "tipo": "inteiro", "unidade": None},
    {"codigo": "gd_potencia_kw", "nome": "Potência de geração distribuída", "tipo": "real", "unidade": "kW"},
    {"codigo": "tronco_max_m", "nome": "Tronco (maior distância pela rede)", "tipo": "real", "unidade": "m"},
    {"codigo": "tronco_origem", "nome": "Origem do tronco", "tipo": "texto", "unidade": None},
    {"codigo": "km_por_nivel", "nome": "Extensão por nível", "tipo": "mapa", "unidade": "km"},
    {"codigo": "km_por_nivel_geometria", "nome": "Extensão por nível (geometria)", "tipo": "mapa",
     "unidade": "km"},
    {"codigo": "ucs_por_classe", "nome": "Unidades consumidoras por classe", "tipo": "mapa", "unidade": None},
    {"codigo": "dispositivos_por_categoria", "nome": "Dispositivos por categoria", "tipo": "mapa",
     "unidade": None},
    {"codigo": "atributo_de_subrede", "nome": "Atributo de filiação", "tipo": "texto", "unidade": None},
    {"codigo": "unidades", "nome": "Unidade do arquivo (comprimento e energia)", "tipo": "mapa",
     "unidade": None},
    {"codigo": "calculado_em", "nome": "Calculado em", "tipo": "data", "unidade": None},
    {"codigo": "duracao_ms", "nome": "Duração do cálculo", "tipo": "inteiro", "unidade": "ms"},
)

# Número guardado em jsonb pode ter chegado como número (carga por SQL) ou como texto (edição pela API, que
# aceita o atributo como veio do arquivo). As duas formas contam; o que não é número não vira zero, fica de
# fora da soma.
def _num(campo: str) -> str:
    return (f"CASE WHEN jsonb_typeof({campo} -> %(chave)s) = 'number' "
            f"     THEN ({campo} ->> %(chave)s)::double precision "
            f"     WHEN {campo} ->> %(chave)s ~ '^-?[0-9]+([.][0-9]+)?$' "
            f"     THEN ({campo} ->> %(chave)s)::double precision END")


def _subredes_alvo(cur, rede_id: str, subrede_id: str | None, tier: str | None) -> list[dict]:
    cur.execute(
        "SELECT s.id, s.nome, s.tier_id, t.codigo AS tier FROM plat.rede_subrede s "
        "JOIN plat.rede_tier t ON t.id = s.tier_id "
        "WHERE s.rede_id = %s::uuid AND (%s::uuid IS NULL OR s.id = %s::uuid) "
        "AND (%s::text IS NULL OR t.codigo = %s) ORDER BY t.ordem, s.nome",
        (rede_id, subrede_id, subrede_id, tier, tier),
    )
    return [dict(r) for r in cur.fetchall()]


def atributo_do_tier(tier_codigo: str) -> str:
    atributo = ATRIBUTO_DE_SUBREDE_POR_TIER.get(tier_codigo)
    if not atributo:
        raise ErroAPI(
            422, "tier_sem_atributo_de_subrede",
            f"o tier '{tier_codigo}' não declara qual atributo do arquivo carrega o nome da subrede: "
            "sem isso não há como dizer que elemento pertence a que subrede",
        )
    return atributo


# --- as somas de uma subrede --------------------------------------------------------------------------

def _linhas(cur, rede_id: str, atributo: str, nome: str, fator_comp: float = 1.0) -> dict:
    cur.execute(
        "SELECT g.codigo AS grupo, count(*) AS n, "
        "       sum(" + _num("f.atributos") + ") AS declarado_m, "
        "       sum(ST_Length(f.geom::geography)) AS geometria_m "
        "FROM plat.rede_feicao_linha f JOIN plat.rede_tipo tp ON tp.id = f.tipo_id "
        "JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE f.rede_id = %(rede)s::uuid AND f.atributos ->> %(atr)s = %(nome)s GROUP BY 1 ORDER BY 1",
        {"rede": rede_id, "atr": atributo, "nome": nome, "chave": ATRIBUTO_COMPRIMENTO},
    )
    km, km_geo, elementos, total_m, total_geo_m = {}, {}, 0, 0.0, 0.0
    for r in cur.fetchall():
        elementos += r["n"]
        declarado = float(r["declarado_m"] or 0.0) * fator_comp
        geometria = float(r["geometria_m"] or 0.0)
        total_m += declarado
        total_geo_m += geometria
        km[r["grupo"]] = round(declarado / 1000.0, 6)
        km_geo[r["grupo"]] = round(geometria / 1000.0, 6)
    return {"km_por_nivel": km, "km_por_nivel_geometria": km_geo, "elementos": elementos,
            "km_declarado": round(total_m / 1000.0, 6), "km_geometria": round(total_geo_m / 1000.0, 6)}


def _pontos(cur, rede_id: str, atributo: str, nome: str) -> dict:
    cur.execute(
        "SELECT g.codigo AS grupo, count(*) AS n, "
        "       sum(" + _num("f.atributos") + ") AS potencia "
        "FROM plat.rede_feicao_ponto f JOIN plat.rede_tipo tp ON tp.id = f.tipo_id "
        "JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE f.rede_id = %(rede)s::uuid AND f.atributos ->> %(atr)s = %(nome)s GROUP BY 1 ORDER BY 1",
        {"rede": rede_id, "atr": atributo, "nome": nome, "chave": ATRIBUTO_POTENCIA_TRAFO},
    )
    trafos, kva, elementos = 0, None, 0
    for r in cur.fetchall():
        elementos += r["n"]
        if r["grupo"] == GRUPO_TRAFO:
            trafos = r["n"]
            kva = round(float(r["potencia"]), 6) if r["potencia"] is not None else None
    return {"trafos": trafos, "kva_instalado": kva, "elementos": elementos}


def _consumidores(cur, rede_id: str, atributo: str, nome: str, fator_ene: float = 1.0) -> dict:
    cur.execute(
        "SELECT coalesce(f.atributos ->> %(classe)s, 'sem_classe') AS classe, count(*) AS n, "
        "       sum(" + _num("f.atributos") + ") AS energia "
        "FROM plat.rede_feicao_ponto f JOIN plat.rede_tipo tp ON tp.id = f.tipo_id "
        "JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE f.rede_id = %(rede)s::uuid AND g.codigo = %(grupo)s "
        "AND f.atributos ->> %(atr)s = %(nome)s GROUP BY 1 ORDER BY 1",
        {"rede": rede_id, "atr": atributo, "nome": nome, "grupo": GRUPO_UC,
         "classe": ATRIBUTO_CLASSE_UC, "chave": ATRIBUTO_ENERGIA},
    )
    por_classe, total, energia, tem_energia = {}, 0, 0.0, False
    for r in cur.fetchall():
        por_classe[r["classe"]] = r["n"]
        total += r["n"]
        if r["energia"] is not None:
            energia += float(r["energia"]) * fator_ene
            tem_energia = True
    return {"ucs": total, "ucs_por_classe": por_classe,
            "energia_anual_kwh": round(energia, 6) if tem_energia else None}


def _geracao(cur, rede_id: str, atributo: str, nome: str) -> dict:
    cur.execute(
        "SELECT count(*) AS n, sum(" + _num("f.atributos") + ") AS potencia "
        "FROM plat.rede_feicao_ponto f JOIN plat.rede_tipo tp ON tp.id = f.tipo_id "
        "JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE f.rede_id = %(rede)s::uuid AND g.codigo = %(grupo)s "
        "AND f.atributos ->> %(atr)s = %(nome)s",
        {"rede": rede_id, "atr": atributo, "nome": nome, "grupo": GRUPO_GD, "chave": ATRIBUTO_POTENCIA_GD},
    )
    r = cur.fetchone()
    potencia = r["potencia"]
    return {"gd_unidades": r["n"], "gd_potencia_kw": round(float(potencia), 6) if potencia is not None else None}


def _por_categoria(cur, rede_id: str, atributo: str, nome: str) -> dict:
    """Quantos dispositivos de cada CATEGORIA DE REDE (o vocabulário do pacote: proteção, seccionamento,
    medição, geração...) a subrede tem. Um tipo com duas categorias conta nas duas — a categoria é
    etiqueta de comportamento, não classificação exclusiva."""
    cur.execute(
        "SELECT c.codigo, count(*) AS n FROM plat.rede_feicao_ponto f "
        "JOIN plat.rede_tipo tp ON tp.id = f.tipo_id "
        "JOIN plat.rede_tipo_categoria tc ON tc.tipo_id = tp.id "
        "JOIN plat.rede_categoria c ON c.id = tc.categoria_id "
        "WHERE f.rede_id = %(rede)s::uuid AND f.atributos ->> %(atr)s = %(nome)s GROUP BY 1 ORDER BY 1",
        {"rede": rede_id, "atr": atributo, "nome": nome},
    )
    return {r["codigo"]: r["n"] for r in cur.fetchall()}


def _tronco(cur, rede_id: str, subrede_id: str, atributo: str, nome: str) -> dict:
    """Maior distância, andando pela rede, de um controlador da subrede até um nó alcançável dela.

    Dijkstra sobre as arestas da topologia cujo trecho de origem é filiado a esta subrede, partindo dos nós
    dos controladores. Sem topologia ou sem controlador com nó não há tronco a medir: a coluna fica nula e
    `tronco_origem` diz qual dos dois faltou."""
    cur.execute(
        "SELECT (SELECT n.id FROM plat.rede_topo_no n WHERE n.rede_id = c.rede_id AND ("
        "   (c.feicao_id IS NOT NULL AND n.origem_id = c.feicao_id AND n.terminal_num = c.terminal_num) "
        "   OR (c.feicao_id IS NULL AND n.geom = c.geom)) LIMIT 1) AS no_id "
        "FROM plat.rede_controlador c WHERE c.rede_id = %s::uuid AND c.subrede_id = %s::uuid",
        (rede_id, subrede_id),
    )
    partidas = [str(r["no_id"]) for r in cur.fetchall() if r["no_id"]]
    if not partidas:
        return {"tronco_max_m": None, "tronco_origem": "sem_controlador"}
    cur.execute(
        "SELECT a.no_origem_id::text AS o, a.no_destino_id::text AS d, a.comprimento_m AS c "
        "FROM plat.rede_topo_aresta a JOIN plat.rede_feicao_linha f ON f.id = a.origem_id "
        "WHERE a.rede_id = %s::uuid AND f.atributos ->> %s = %s "
        "AND a.no_origem_id IS NOT NULL AND a.no_destino_id IS NOT NULL",
        (rede_id, atributo, nome),
    )
    vizinhos: dict[str, list] = {}
    for r in cur.fetchall():
        vizinhos.setdefault(r["o"], []).append((r["d"], float(r["c"])))
        vizinhos.setdefault(r["d"], []).append((r["o"], float(r["c"])))
    if not vizinhos:
        return {"tronco_max_m": None, "tronco_origem": "sem_topologia"}
    # Cada terminal de um dispositivo é um nó PRÓPRIO na topologia e nada os liga sozinho (`tracado.py`):
    # sem a aresta virtual do `caminho_valido` declarado no terminal do pacote, o caminho para no primeiro
    # disjuntor e o tronco de todo alimentador daria zero. A aresta virtual tem comprimento zero (o
    # dispositivo é um ponto) e só entra para dispositivo FILIADO a esta subrede e não aberto — chave
    # aberta não conduz, mesma regra do traçado.
    cur.execute(
        "SELECT n1.id::text AS o, n2.id::text AS d FROM plat.rede_feicao_ponto f "
        "JOIN plat.rede_tipo t ON t.id = f.tipo_id "
        "JOIN plat.rede_terminal_config tc ON tc.id = t.terminal_id "
        "CROSS JOIN LATERAL jsonb_to_recordset(tc.caminhos_validos) AS cv(de int, para int, nome text) "
        "JOIN plat.rede_topo_no n1 ON n1.rede_id = %(rede)s::uuid AND n1.papel = 'terminal' "
        "  AND n1.origem_id = f.id AND n1.terminal_num = cv.de "
        "JOIN plat.rede_topo_no n2 ON n2.rede_id = %(rede)s::uuid AND n2.papel = 'terminal' "
        "  AND n2.origem_id = f.id AND n2.terminal_num = cv.para "
        "WHERE f.rede_id = %(rede)s::uuid AND f.atributos ->> %(atr)s = %(nome)s "
        "  AND coalesce(f.atributos ->> 'estado', 'fechado') <> 'aberto'",
        {"rede": rede_id, "atr": atributo, "nome": nome},
    )
    for r in cur.fetchall():
        vizinhos.setdefault(r["o"], []).append((r["d"], 0.0))
        vizinhos.setdefault(r["d"], []).append((r["o"], 0.0))
    distancia: dict[str, float] = {}
    fila = []
    for no in partidas:
        distancia[no] = 0.0
        heappush(fila, (0.0, no))
    maior = 0.0
    while fila:
        d, no = heappop(fila)
        if d > distancia.get(no, float("inf")):
            continue
        maior = max(maior, d)
        for vizinho, peso in vizinhos.get(no, ()):
            nova = d + peso
            if nova < distancia.get(vizinho, float("inf")):
                distancia[vizinho] = nova
                heappush(fila, (nova, vizinho))
    return {"tronco_max_m": round(maior, 3), "tronco_origem": "topologia"}


# --- cálculo e gravação -------------------------------------------------------------------------------

def calcular(cur, tenant_id: int, rede_id: str, subrede: dict) -> dict:
    """Calcula e grava o sumário de UMA subrede (a linha de `plat.rede_subrede_resumo`)."""
    inicio = time.perf_counter()
    atributo = atributo_do_tier(subrede["tier"])
    nome = subrede["nome"]
    # a unidade do comprimento e da energia vem do que a IMPORTAÇÃO mediu no arquivo, nunca do dicionário
    # do pacote (item L4-01-e); sem importação registrada o fator é 1 e a origem diz `nao_medida`
    fatores = unidades_mod.fatores_da_rede(cur, rede_id)
    linhas = _linhas(cur, rede_id, atributo, nome, fatores["comp"]["fator_para_base"])
    pontos = _pontos(cur, rede_id, atributo, nome)
    consumidores = _consumidores(cur, rede_id, atributo, nome, fatores["ene"]["fator_para_base"])
    geracao = _geracao(cur, rede_id, atributo, nome)
    categorias = _por_categoria(cur, rede_id, atributo, nome)
    tronco = _tronco(cur, rede_id, str(subrede["id"]), atributo, nome)

    km_declarado, km_geometria = linhas["km_declarado"], linhas["km_geometria"]
    divergencia = (round(100.0 * (km_geometria - km_declarado) / km_declarado, 6)
                   if km_declarado else None)
    linha = {
        "subrede_id": str(subrede["id"]),
        "tenant_id": tenant_id,
        "rede_id": rede_id,
        "tier_id": str(subrede["tier_id"]),
        "subrede_nome": nome,
        "atributo_de_subrede": atributo,
        "unidades": {familia: {"unidade_do_arquivo": f.get("unidade"), "base": f["base"],
                               "fator_para_base": f["fator_para_base"], "origem": f["origem"],
                               "declarada_no_dicionario": f["declarada"]}
                     for familia, f in fatores.items()},
        "elementos": linhas["elementos"] + pontos["elementos"],
        "km_por_nivel": linhas["km_por_nivel"],
        "km_por_nivel_geometria": linhas["km_por_nivel_geometria"],
        "km_declarado": km_declarado,
        "km_geometria": km_geometria,
        "divergencia_pct": divergencia,
        "trafos": pontos["trafos"],
        "kva_instalado": pontos["kva_instalado"],
        "ucs": consumidores["ucs"],
        "ucs_por_classe": consumidores["ucs_por_classe"],
        "energia_anual_kwh": consumidores["energia_anual_kwh"],
        "dispositivos_por_categoria": categorias,
        "gd_unidades": geracao["gd_unidades"],
        "gd_potencia_kw": geracao["gd_potencia_kw"],
        "tronco_max_m": tronco["tronco_max_m"],
        "tronco_origem": tronco["tronco_origem"],
        "duracao_ms": int((time.perf_counter() - inicio) * 1000),
    }
    cur.execute(
        "INSERT INTO plat.rede_subrede_resumo (subrede_id, tenant_id, rede_id, tier_id, subrede_nome, "
        " atributo_de_subrede, unidades, elementos, km_por_nivel, km_por_nivel_geometria, km_declarado, km_geometria, "
        " divergencia_pct, trafos, kva_instalado, ucs, ucs_por_classe, energia_anual_kwh, "
        " dispositivos_por_categoria, gd_unidades, gd_potencia_kw, tronco_max_m, tronco_origem, duracao_ms, "
        " calculado_em) "
        "VALUES (%(subrede_id)s::uuid, %(tenant_id)s, %(rede_id)s::uuid, %(tier_id)s::uuid, "
        " %(subrede_nome)s, %(atributo_de_subrede)s, %(unidades)s::jsonb, %(elementos)s, %(km_por_nivel)s::jsonb, "
        " %(km_por_nivel_geometria)s::jsonb, %(km_declarado)s, %(km_geometria)s, %(divergencia_pct)s, "
        " %(trafos)s, %(kva_instalado)s, %(ucs)s, %(ucs_por_classe)s::jsonb, %(energia_anual_kwh)s, "
        " %(dispositivos_por_categoria)s::jsonb, %(gd_unidades)s, %(gd_potencia_kw)s, %(tronco_max_m)s, "
        " %(tronco_origem)s, %(duracao_ms)s, now()) "
        "ON CONFLICT (subrede_id) DO UPDATE SET "
        " tier_id = EXCLUDED.tier_id, subrede_nome = EXCLUDED.subrede_nome, "
        " atributo_de_subrede = EXCLUDED.atributo_de_subrede, unidades = EXCLUDED.unidades, "
        " elementos = EXCLUDED.elementos, "
        " km_por_nivel = EXCLUDED.km_por_nivel, km_por_nivel_geometria = EXCLUDED.km_por_nivel_geometria, "
        " km_declarado = EXCLUDED.km_declarado, km_geometria = EXCLUDED.km_geometria, "
        " divergencia_pct = EXCLUDED.divergencia_pct, trafos = EXCLUDED.trafos, "
        " kva_instalado = EXCLUDED.kva_instalado, ucs = EXCLUDED.ucs, "
        " ucs_por_classe = EXCLUDED.ucs_por_classe, energia_anual_kwh = EXCLUDED.energia_anual_kwh, "
        " dispositivos_por_categoria = EXCLUDED.dispositivos_por_categoria, "
        " gd_unidades = EXCLUDED.gd_unidades, gd_potencia_kw = EXCLUDED.gd_potencia_kw, "
        " tronco_max_m = EXCLUDED.tronco_max_m, tronco_origem = EXCLUDED.tronco_origem, "
        " duracao_ms = EXCLUDED.duracao_ms, calculado_em = now()",
        {**linha,
         "unidades": json.dumps(linha["unidades"]),
         "km_por_nivel": json.dumps(linha["km_por_nivel"]),
         "km_por_nivel_geometria": json.dumps(linha["km_por_nivel_geometria"]),
         "ucs_por_classe": json.dumps(linha["ucs_por_classe"]),
         "dispositivos_por_categoria": json.dumps(linha["dispositivos_por_categoria"])},
    )
    return linha


def calcular_todas(cur, tenant_id: int, rede_id: str, tier: str | None = None,
                   subrede_id: str | None = None) -> dict:
    """Recalcula o sumário das subredes da rede (ou de um tier, ou de uma subrede). Tier sem atributo de
    filiação declarado não trava as outras: entra na lista `sem_atributo` e o resto é calculado."""
    alvos = _subredes_alvo(cur, rede_id, subrede_id, tier)
    if not alvos:
        return {"subredes": 0, "calculadas": 0, "sem_atributo": [], "duracao_ms": 0}
    inicio = time.perf_counter()
    calculadas, sem_atributo = 0, []
    for alvo in alvos:
        try:
            atributo_do_tier(alvo["tier"])
        except ErroAPI:
            if alvo["tier"] not in sem_atributo:
                sem_atributo.append(alvo["tier"])
            continue
        calcular(cur, tenant_id, rede_id, alvo)
        calculadas += 1
    return {"subredes": len(alvos), "calculadas": calculadas, "sem_atributo": sem_atributo,
            "duracao_ms": int((time.perf_counter() - inicio) * 1000)}


# --- leitura ------------------------------------------------------------------------------------------

def listar(cur, rede_id: str, limite: int, tier: str | None = None) -> list[dict]:
    cur.execute(
        "SELECT r.*, t.codigo AS tier, t.nome AS tier_nome, t.ordem AS tier_ordem "
        "FROM plat.rede_subrede_resumo r JOIN plat.rede_tier t ON t.id = r.tier_id "
        "WHERE r.rede_id = %s::uuid AND (%s::text IS NULL OR t.codigo = %s) "
        "ORDER BY t.ordem, r.subrede_nome LIMIT %s",
        (rede_id, tier, tier, limite),
    )
    itens = []
    for r in cur.fetchall():
        itens.append({
            "subrede_id": str(r["subrede_id"]),
            "subrede": r["subrede_nome"],
            "tier": r["tier"],
            "tier_nome": r["tier_nome"],
            "elementos": r["elementos"],
            "km_declarado": r["km_declarado"],
            "km_geometria": r["km_geometria"],
            "divergencia_pct": r["divergencia_pct"],
            "trafos": r["trafos"],
            "kva_instalado": r["kva_instalado"],
            "ucs": r["ucs"],
            "energia_anual_kwh": r["energia_anual_kwh"],
            "gd_unidades": r["gd_unidades"],
            "gd_potencia_kw": r["gd_potencia_kw"],
            "tronco_max_m": r["tronco_max_m"],
            "tronco_origem": r["tronco_origem"],
            "km_por_nivel": r["km_por_nivel"],
            "km_por_nivel_geometria": r["km_por_nivel_geometria"],
            "ucs_por_classe": r["ucs_por_classe"],
            "dispositivos_por_categoria": r["dispositivos_por_categoria"],
            "atributo_de_subrede": r["atributo_de_subrede"],
            "unidades": r["unidades"] or {},
            "calculado_em": r["calculado_em"],
            "duracao_ms": r["duracao_ms"],
        })
    return itens


def csv_de(itens: list[dict]) -> str:
    """O mesmo conteúdo da tabela em CSV, uma coluna por entrada de `COLUNAS`. As colunas de mapa (por
    nível, por classe, por categoria) saem como JSON compacto numa célula: quem abre em planilha vê o
    conteúdo, quem lê por programa desserializa."""
    saida = io.StringIO()
    escritor = csv.writer(saida, lineterminator="\n")
    escritor.writerow([c["codigo"] if c["unidade"] is None else f"{c['codigo']}_{c['unidade']}"
                       for c in COLUNAS])
    for item in itens:
        linha = []
        for coluna in COLUNAS:
            valor = item.get(coluna["codigo"])
            if coluna["tipo"] == "mapa":
                linha.append(json.dumps(valor or {}, ensure_ascii=False, sort_keys=True))
            elif coluna["tipo"] == "data" and valor is not None:
                linha.append(valor.isoformat() if hasattr(valor, "isoformat") else str(valor))
            else:
                linha.append("" if valor is None else valor)
        escritor.writerow(linha)
    return saida.getvalue()
