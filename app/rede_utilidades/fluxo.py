"""Traçado de MONTANTE e JUSANTE por direção de fluxo declarada em atributo (item
L4-18-rede-simples-trace-network).

O que decide o sentido é um ATRIBUTO do trecho, não uma regra de negócio nem um controlador de subrede: cada
aresta da topologia (`plat.rede_topo_aresta`) carrega, em `atributos`, a chave `direcao_fluxo` com um de três
valores — `digitalizada` (o fluxo segue a ordem dos vértices, do primeiro para o último), `contra` (segue ao
contrário) e `indeterminada` (não se sabe). É o mesmo vocabulário fechado do Trace Network da Esri
(digitized / against digitized / indeterminate), e a carga da rede simples (`simples.py`) grava esse atributo
traduzindo o campo que o inquilino declarou.

Regra da indeterminada, que é a refutação exigida do item: uma aresta indeterminada NÃO conduz, em sentido
nenhum. O traçado PARA nela e o resultado sai com um aviso por aresta, dizendo qual trecho e em que nó parou.
Nunca se escolhe um sentido "provável": a alternativa (tratar indeterminada como bidirecional) faria o
montante de um rio devolver afluentes que estão a jusante, e o silêncio seria pior que o resultado curto.

Valor fora do vocabulário (alguém gravou outra coisa por `applyEdits`) é lido como `indeterminada` — a mesma
parada com aviso, nunca uma adivinhação.

Grafo: o MESMO da topologia derivada (L4-01-b), com as barreiras do chamador removidas antes de montar, como
em `tracado.py`. A rede simples não tem dispositivo com caminho válido, então não há aresta virtual a somar;
numa rede de utilidades, montante/jusante deste item andam pelos TRECHOS — atravessar o dispositivo por
direção de fluxo depende do terminal `montante` de cada configuração e fica fora desta passagem (fronteira
escrita em docs/rede/REDE_SIMPLES.md)."""

import time

from app.erros import ErroAPI
from app.rede_utilidades import lacos as _lac
from app.rede_utilidades import tracado as _tr

TIPOS_FLUXO = ("montante", "jusante")
DIRECOES = ("digitalizada", "contra", "indeterminada")
CHAVE_DIRECAO = "direcao_fluxo"
PADRAO = "digitalizada"


def _montar_arestas_dirigidas(cur, rede_id: str) -> None:
    """`TEMP TABLE fluxo_aresta (aresta_id, feicao_id, tipo_id, de, para, indeterminada)`: uma linha por
    aresta da topologia cujas DUAS pontas sobreviveram às barreiras (o JOIN em `tracado_mapa` é o que garante
    isso), já orientada pela direção declarada."""
    rede_lit = cur.mogrify("%s::uuid", (rede_id,)).decode("utf-8")
    chave_lit = cur.mogrify("%s", (CHAVE_DIRECAO,)).decode("utf-8")
    padrao_lit = cur.mogrify("%s", (PADRAO,)).decode("utf-8")
    validas_lit = cur.mogrify("%s", (list(DIRECOES),)).decode("utf-8")
    cur.execute("CREATE TEMP TABLE IF NOT EXISTS fluxo_aresta ("
                "aresta_id uuid PRIMARY KEY, feicao_id uuid, tipo_id uuid, de uuid, para uuid, "
                "indeterminada boolean NOT NULL)")
    cur.execute("TRUNCATE fluxo_aresta")
    cur.execute(
        "INSERT INTO fluxo_aresta (aresta_id, feicao_id, tipo_id, de, para, indeterminada) "
        "SELECT a.id, a.origem_id, a.tipo_id, "
        "  CASE WHEN v.dir = 'contra' THEN a.no_destino_id ELSE a.no_origem_id END, "
        "  CASE WHEN v.dir = 'contra' THEN a.no_origem_id ELSE a.no_destino_id END, "
        "  v.dir = 'indeterminada' "
        "FROM plat.rede_topo_aresta a "
        "JOIN tracado_mapa m1 ON m1.no_id = a.no_origem_id "
        "JOIN tracado_mapa m2 ON m2.no_id = a.no_destino_id "
        # a direção é atributo DA FEIÇÃO (camada editável), não do índice derivado: lida aqui pelo join com
        # `rede_feicao_linha`, mudar a direção por applyEdits muda o traçado na hora, sem reconstruir a
        # topologia. A cópia gravada na aresta serve de reserva (aresta sem feição viva não existe hoje).
        "LEFT JOIN plat.rede_feicao_linha lf ON lf.id = a.origem_id "
        "CROSS JOIN LATERAL (SELECT CASE WHEN d.bruta = ANY(" + validas_lit + ") THEN d.bruta "
        "                    ELSE 'indeterminada' END AS dir "
        "                    FROM (SELECT coalesce(lf.atributos ->> " + chave_lit + ", "
        "a.atributos ->> " + chave_lit + ", " + padrao_lit + ") AS bruta) d) v "
        "WHERE a.rede_id = " + rede_lit + " AND a.no_origem_id IS NOT NULL AND a.no_destino_id IS NOT NULL"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS ix_fluxo_aresta_de ON fluxo_aresta (de)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_fluxo_aresta_para ON fluxo_aresta (para)")
    cur.execute("ANALYZE fluxo_aresta")


def tracar_fluxo(cur, tenant_id: int, rede_id: str, tipo: str, pontos_partida: list[dict],
                 barreiras: list[dict]) -> dict:
    """`tipo='jusante'` anda no sentido do fluxo a partir dos pontos de partida; `tipo='montante'` anda no
    sentido contrário. Devolve o mesmo formato dos outros traçados (elementos, geometria, contagem) mais
    `avisos` (as arestas indeterminadas em que o traçado parou) e `parou_em_indeterminada`."""
    if tipo not in TIPOS_FLUXO:
        raise ErroAPI(422, "tipo_invalido", f"tipo deve ser um de {TIPOS_FLUXO}")
    if not pontos_partida:
        raise ErroAPI(422, "sem_ponto_de_partida", "informe ao menos um ponto de partida")
    inicio = time.perf_counter()

    tolerancia_rede, ids_barreira = _lac._preparar_mapa(cur, rede_id, barreiras)
    ids_inicio = [_tr._resolver_ponto(cur, rede_id, tolerancia_rede, p) for p in pontos_partida]
    if [i for i in ids_inicio if i in ids_barreira]:
        raise ErroAPI(422, "inicio_e_barreira", "um ponto de partida não pode também ser barreira")
    _montar_arestas_dirigidas(cur, rede_id)

    # jusante segue de->para; montante segue para->de. O resto do cálculo é idêntico: por isso as duas
    # colunas viram nomes ('avanca', 'recua') e só a consulta troca qual é qual.
    avanca, recua = ("de", "para") if tipo == "jusante" else ("para", "de")
    cur.execute(
        "WITH RECURSIVE alc(no) AS ("
        "  SELECT unnest(%s::uuid[])"
        "  UNION"
        f"  SELECT f.{recua} FROM fluxo_aresta f JOIN alc ON f.{avanca} = alc.no WHERE NOT f.indeterminada"
        ") SELECT no FROM alc",
        (ids_inicio,),
    )
    alcancados = {str(r["no"]) for r in cur.fetchall()}

    # aviso por aresta indeterminada ENCOSTADA no resultado, dos DOIS lados: ela não conduz em sentido
    # nenhum, então tanto faz se o traçado chegou pela ponta de origem ou pela de destino — nos dois casos
    # ele parou ali e o resultado pode estar curto. Reportar só um dos lados esconderia metade das paradas
    # (medido: o traçado a jusante parava num trecho digitalizado ao contrário e saía sem aviso nenhum).
    cur.execute(
        "SELECT f.aresta_id, f.feicao_id, "
        "  CASE WHEN f.de = ANY(%(alc)s::uuid[]) THEN f.de ELSE f.para END AS no_parada "
        "FROM fluxo_aresta f WHERE f.indeterminada "
        "  AND (f.de = ANY(%(alc)s::uuid[]) OR f.para = ANY(%(alc)s::uuid[])) "
        "ORDER BY f.aresta_id",
        {"alc": list(alcancados)},
    )
    avisos = [
        {"codigo": "direcao_indeterminada",
         "mensagem": "o traçado parou neste trecho: a direção de fluxo dele é indeterminada",
         "aresta_id": str(r["aresta_id"]), "feicao_id": str(r["feicao_id"]),
         "no_id": str(r["no_parada"])}
        for r in cur.fetchall()
    ]

    elementos, geometria = _tr.elementos_e_geometria(cur, rede_id, alcancados)
    return {
        "tipo": tipo, "elementos": elementos, "contagem": len(elementos), "geometria": geometria,
        "duracao_ms": int((time.perf_counter() - inicio) * 1000), "nos_alcancados": len(alcancados),
        "avisos": avisos, "parou_em_indeterminada": bool(avisos),
    }


def arestas_dirigidas(cur, rede_id: str) -> list[dict]:
    """As arestas já orientadas, para conferência independente (o teste do item as reconstrói em networkx).
    Monta o mesmo grafo do traçado, sem barreira nenhuma."""
    _lac._preparar_mapa(cur, rede_id, [])
    _montar_arestas_dirigidas(cur, rede_id)
    cur.execute("SELECT aresta_id, feicao_id, de, para, indeterminada FROM fluxo_aresta")
    return [{"aresta_id": str(r["aresta_id"]), "feicao_id": str(r["feicao_id"]), "de": str(r["de"]),
             "para": str(r["para"]), "indeterminada": r["indeterminada"]} for r in cur.fetchall()]
