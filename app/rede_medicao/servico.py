"""Núcleo do módulo rede_medicao (item L4-13-integracao-telemetria): publicação idempotente de leitura,
última leitura/série para a ficha do ativo, alarme declarado de carregamento e agregação a jusante.

Nada aqui presume que `ativo` existe em nenhuma tabela de feição (mesma decisão do módulo campo): é só um
uuid que o publicador e o leitor concordam em chamar de "este trafo". `app/rede_medicao/rotas.py` é a única
porta de entrada; erro sempre por `ErroAPI`, nunca por exceção crua do psycopg2 vazando para o cliente."""

from __future__ import annotations

import datetime
import math

import psycopg2

from app import limites
from app.auth import comum as auth_comum
from app.auth.sessao import iso
from app.catalogo.comum import jsonb, registrar_evento

ALARME_TIPO_CARREGAMENTO = "carregamento_30min"
GRANDEZAS_CORRENTE = ("corrente_a", "corrente_b", "corrente_c")
GRANDEZA_CARREGAMENTO = "carregamento_pct"
FONTE_MOTOR_ALARME = "motor_alarme"


def _agora() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _parse_ts(bruto: str) -> datetime.datetime:
    try:
        dt = datetime.datetime.fromisoformat(str(bruto).replace("Z", "+00:00"))
    except (ValueError, TypeError) as e:
        raise ValueError("ts inválido") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    return dt


def grandezas_catalogo(cur) -> dict[str, dict]:
    cur.execute("SELECT codigo, nome, unidade, tipo, descricao FROM plat.rede_medicao_grandeza")
    return {r["codigo"]: r for r in cur.fetchall()}


def _particoes_garantir(cur, meses: set[datetime.date]) -> None:
    for mes in meses:
        cur.execute("SELECT plat.rede_medicao_particao_garantir(%s)", (mes,))


def publicar_leituras(cur, auth, itens: list) -> dict:
    """Insere o lote com idempotência por (ativo, grandeza, ts): reenviar o mesmo trio não duplica (ON
    CONFLICT DO NOTHING) — nem erro, nem segunda linha. Recusa por item (não aborta o lote inteiro): ts no
    futuro além da tolerância do relógio do sensor, grandeza desconhecida, unidade que não bate com a do
    catálogo. Devolve {aceitas, duplicadas, rejeitadas:[{indice, ativo, erro, mensagem}]}."""
    catalogo = grandezas_catalogo(cur)
    agora = _agora()
    limite_futuro = agora + datetime.timedelta(seconds=limites.REDE_MEDICAO_JANELA_FUTURO_S)
    validos: list[tuple] = []
    rejeitadas: list[dict] = []
    meses: set[datetime.date] = set()
    ativos_tocados: dict[str, str | None] = {}
    for i, item in enumerate(itens):
        try:
            ts = _parse_ts(item.ts)
        except ValueError:
            rejeitadas.append({"indice": i, "ativo": item.ativo, "erro": "ts_invalido",
                                "mensagem": "ts não é um instante ISO-8601 válido"})
            continue
        if ts > limite_futuro:
            rejeitadas.append({"indice": i, "ativo": item.ativo, "erro": "ts_futuro",
                                "mensagem": f"ts está no futuro além da tolerância de "
                                f"{limites.REDE_MEDICAO_JANELA_FUTURO_S}s de relógio do sensor"})
            continue
        g = catalogo.get(item.grandeza)
        if g is None or g["tipo"] != "bruto":
            rejeitadas.append({"indice": i, "ativo": item.ativo, "erro": "grandeza_desconhecida",
                                "mensagem": f"grandeza {item.grandeza!r} não está no catálogo (ou é derivada: "
                                "ninguém publica carregamento_pct de fora)"})
            continue
        if item.unidade != g["unidade"]:
            rejeitadas.append({"indice": i, "ativo": item.ativo, "erro": "unidade_incompativel",
                                "mensagem": f"grandeza {item.grandeza!r} é medida em {g['unidade']!r}, "
                                f"não {item.unidade!r}"})
            continue
        meses.add(ts.date().replace(day=1))
        ativos_tocados[item.ativo] = item.cod_id or ativos_tocados.get(item.ativo)
        validos.append((auth.tenant_id, item.ativo, item.cod_id, ts, item.fonte, item.grandeza, item.valor,
                        item.unidade, jsonb(item.bruta)))
    if validos:
        _particoes_garantir(cur, meses)
        aceitas = 0
        for linha in validos:
            try:
                cur.execute(
                    "INSERT INTO plat.rede_medicao(tenant_id, ativo, cod_id, ts, fonte, grandeza, valor, "
                    "unidade, leitura) VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (tenant_id, ativo, grandeza, ts) DO NOTHING",
                    linha,
                )
            except psycopg2.Error as e:
                raise auth_comum.erro_do_banco(e) from e
            aceitas += cur.rowcount
        duplicadas = len(validos) - aceitas
    else:
        aceitas = duplicadas = 0
    return {"aceitas": aceitas, "duplicadas": duplicadas, "rejeitadas": rejeitadas,
            "ativos_tocados": list(ativos_tocados)}


# ---------------------------------------------------------------------- placa do ativo (nameplate)
def ativo_config_upsert(cur, auth, request, ativo: str, corpo) -> dict:
    cur.execute(
        "INSERT INTO plat.rede_medicao_ativo(tenant_id, ativo, cod_id, kva_nominal, tensao_nominal_v, "
        "atualizado_por) VALUES (%s, %s::uuid, %s, %s, %s, %s) "
        "ON CONFLICT (tenant_id, ativo) DO UPDATE SET "
        "cod_id = coalesce(EXCLUDED.cod_id, plat.rede_medicao_ativo.cod_id), "
        "kva_nominal = coalesce(EXCLUDED.kva_nominal, plat.rede_medicao_ativo.kva_nominal), "
        "tensao_nominal_v = coalesce(EXCLUDED.tensao_nominal_v, plat.rede_medicao_ativo.tensao_nominal_v), "
        "atualizado_por = EXCLUDED.atualizado_por, atualizado_em = now() "
        "RETURNING ativo, cod_id, kva_nominal, tensao_nominal_v, atualizado_em",
        (auth.tenant_id, ativo, corpo.cod_id, corpo.kva_nominal, corpo.tensao_nominal_v, auth.usuario_id),
    )
    r = cur.fetchone()
    registrar_evento(cur, request, "rede_medicao/ativo_configurar", "rede_medicao_ativo", ativo,
                     {"cod_id": r["cod_id"], "kva_nominal": r["kva_nominal"]})
    return r


def ativo_config_obter(cur, ativo: str) -> dict | None:
    cur.execute(
        "SELECT ativo, cod_id, kva_nominal, tensao_nominal_v, atualizado_em FROM plat.rede_medicao_ativo "
        "WHERE ativo = %s::uuid",
        (ativo,),
    )
    return cur.fetchone()


# ---------------------------------------------------------------------- ficha do ativo: última leitura + série
def ultima_leitura(cur, ativo: str) -> list[dict]:
    cur.execute(
        "SELECT DISTINCT ON (grandeza) grandeza, valor, unidade, ts, fonte, recebido_em "
        "FROM plat.rede_medicao WHERE ativo = %s::uuid ORDER BY grandeza, ts DESC",
        (ativo,),
    )
    return cur.fetchall()


def serie(cur, ativo: str, grandeza: str, desde: datetime.datetime, ate: datetime.datetime,
         limite: int) -> list[dict]:
    cur.execute(
        "SELECT ts, valor, unidade, fonte FROM plat.rede_medicao "
        "WHERE ativo = %s::uuid AND grandeza = %s AND ts BETWEEN %s AND %s "
        "ORDER BY ts LIMIT %s",
        (ativo, grandeza, desde, ate, limite),
    )
    return cur.fetchall()


# ---------------------------------------------------------------------- alarme: carregamento > 100% por 30 min
def _carregamento_pct(correntes: dict[str, float], tensao_nominal_v: float, kva_nominal: float) -> float:
    """S(kVA) trifásico estimado ≈ √3 × V_linha(V) × I_média(A) ÷ 1000, sobre a corrente MÉDIA das fases
    presentes (nem toda leitura tem as 3 fases). Fórmula simples e declarada, não um modelo de fluxo de
    carga: é exatamente o que um alarme "> 100% da placa" precisa, nada mais."""
    valores = [v for v in correntes.values() if v is not None]
    if not valores or tensao_nominal_v <= 0 or kva_nominal <= 0:
        raise ValueError("dado insuficiente para carregamento")
    i_media = sum(valores) / len(valores)
    s_kva = math.sqrt(3) * tensao_nominal_v * i_media / 1000.0
    return s_kva / kva_nominal * 100.0


def avaliar_alarme_carregamento(cur, auth, request, ativo: str) -> dict | None:
    """Roda depois de toda ingestão que tocou `ativo` (chamado pela rota de leituras — é o que dá o
    "última leitura em ≤ 5 s" e o alarme quase em tempo real, sem depender de um job periódico separado):

    1. lê a placa (kVA/tensão nominal) — sem ela não há carregamento a calcular, devolve None (não é erro:
       nem todo ativo tem placa cadastrada);
    2. lê a corrente mais recente de cada fase publicada, calcula carregamento_pct e GRAVA como leitura
       derivada (fonte=motor_alarme) — é o que a ficha do ativo e o gráfico de 7 dias mostram;
    3. olha os últimos REDE_MEDICAO_ALARME_LOOKBACK_MIN minutos da série carregamento_pct (a que acabou de
       ganhar o ponto novo) e acha o INÍCIO do surto contínuo acima de 100% (a corrida volta ao primeiro
       ponto, a partir do fim, que ainda está acima de 100%); se esse início já tem
       REDE_MEDICAO_ALARME_JANELA_MIN minutos e o ponto mais recente continua acima de 100%, o alarme está
       ativo — dispara `rede_medicao/alarme_disparado` só na TRANSIÇÃO (rodar de novo com o alarme já ativo
       não escreve um segundo evento); volta a ≤100% dispara `rede_medicao/alarme_resolvido`."""
    placa = ativo_config_obter(cur, ativo)
    if placa is None or placa["kva_nominal"] is None or placa["tensao_nominal_v"] is None:
        return None
    cur.execute(
        "SELECT DISTINCT ON (grandeza) grandeza, valor, ts FROM plat.rede_medicao "
        "WHERE ativo = %s::uuid AND grandeza = ANY(%s) ORDER BY grandeza, ts DESC",
        (ativo, list(GRANDEZAS_CORRENTE)),
    )
    linhas = cur.fetchall()
    if not linhas:
        return None
    correntes = {r["grandeza"]: r["valor"] for r in linhas}
    ts_leitura = max(r["ts"] for r in linhas)
    try:
        pct = _carregamento_pct(correntes, float(placa["tensao_nominal_v"]), float(placa["kva_nominal"]))
    except ValueError:
        return None
    cur.execute("SELECT plat.rede_medicao_particao_garantir(%s)", (ts_leitura.date().replace(day=1),))
    cur.execute(
        "INSERT INTO plat.rede_medicao(tenant_id, ativo, cod_id, ts, fonte, grandeza, valor, unidade, leitura) "
        "VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (tenant_id, ativo, grandeza, ts) DO NOTHING",
        (auth.tenant_id, ativo, placa["cod_id"], ts_leitura, FONTE_MOTOR_ALARME, GRANDEZA_CARREGAMENTO, pct,
         "%", jsonb({"correntes_a": correntes, "kva_nominal": float(placa["kva_nominal"]),
                     "tensao_nominal_v": float(placa["tensao_nominal_v"])})),
    )

    desde = ts_leitura - datetime.timedelta(minutes=limites.REDE_MEDICAO_ALARME_LOOKBACK_MIN)
    cur.execute(
        "SELECT ts, valor FROM plat.rede_medicao WHERE ativo = %s::uuid AND grandeza = %s "
        "AND ts BETWEEN %s AND %s ORDER BY ts",
        (ativo, GRANDEZA_CARREGAMENTO, desde, ts_leitura),
    )
    pontos = cur.fetchall()
    inicio_surto = None
    if pontos and pontos[-1]["valor"] > 100:
        inicio_surto = pontos[-1]["ts"]
        for p in reversed(pontos):
            if p["valor"] <= 100:
                break
            inicio_surto = p["ts"]
    ativo_agora = (inicio_surto is not None
                  and (ts_leitura - inicio_surto) >= datetime.timedelta(minutes=limites.REDE_MEDICAO_ALARME_JANELA_MIN))

    cur.execute(
        "SELECT disparado, desde FROM plat.rede_medicao_alarme_estado "
        "WHERE tenant_id = %s AND ativo = %s::uuid AND tipo = %s",
        (auth.tenant_id, ativo, ALARME_TIPO_CARREGAMENTO),
    )
    estado_anterior = cur.fetchone()
    ja_disparado = bool(estado_anterior and estado_anterior["disparado"])

    cur.execute(
        "INSERT INTO plat.rede_medicao_alarme_estado(tenant_id, ativo, tipo, disparado, desde, ultimo_valor) "
        "VALUES (%s, %s::uuid, %s, %s, %s, %s) "
        "ON CONFLICT (tenant_id, ativo, tipo) DO UPDATE SET disparado = EXCLUDED.disparado, "
        "desde = CASE WHEN EXCLUDED.disparado THEN coalesce(plat.rede_medicao_alarme_estado.desde, EXCLUDED.desde) "
        "ELSE NULL END, ultimo_valor = EXCLUDED.ultimo_valor, atualizado_em = now()",
        (auth.tenant_id, ativo, ALARME_TIPO_CARREGAMENTO, ativo_agora, inicio_surto if ativo_agora else None, pct),
    )

    disparou_agora = ativo_agora and not ja_disparado
    resolveu_agora = ja_disparado and not ativo_agora
    if disparou_agora:
        registrar_evento(cur, request, "rede_medicao/alarme_disparado", "rede_medicao_ativo", ativo,
                         {"tipo": ALARME_TIPO_CARREGAMENTO, "carregamento_pct": pct,
                          "desde": iso(inicio_surto), "janela_min": limites.REDE_MEDICAO_ALARME_JANELA_MIN})
    elif resolveu_agora:
        registrar_evento(cur, request, "rede_medicao/alarme_resolvido", "rede_medicao_ativo", ativo,
                         {"tipo": ALARME_TIPO_CARREGAMENTO, "carregamento_pct": pct})
    return {"carregamento_pct": pct, "alarme_ativo": ativo_agora, "disparou_agora": disparou_agora,
            "resolveu_agora": resolveu_agora, "desde": iso(inicio_surto) if ativo_agora else None}


# ---------------------------------------------------------------------- agregação a jusante (topologia)
def agregado_jusante(cur, tenant_id: int, rede_id: str, ativo: str, grandeza: str,
                     janela_min: int, terminal: int | None = None) -> dict:
    """Soma a leitura mais recente (até `janela_min` min atrás) de `grandeza` entre todos os transformadores
    de distribuição alcançados a JUSANTE de `ativo` pela topologia derivada (item L4-01-b) — reusa
    `app.rede_utilidades.fluxo.tracar_fluxo` tal como está: sem `direcao_fluxo` gravado em nenhum trecho, a
    direção default é 'digitalizada' (ordem dos vértices), a mesma regra que o item de traçado já documenta.
    Exemplo do portão: soma das correntes dos trafos de um alimentador, a partir de um ponto do tronco MT."""
    from app.rede_utilidades import fluxo
    from app.rede_utilidades.controladores import GRUPO_TRAFO

    ponto = {"feicao_id": ativo}
    if terminal is not None:
        ponto["terminal"] = terminal
    resultado = fluxo.tracar_fluxo(cur, tenant_id, rede_id, "jusante", [ponto], [])
    trafo_ids = sorted({e["feicao_id"] for e in resultado["elementos"]
                        if e.get("grupo") == GRUPO_TRAFO and e["feicao_id"] != ativo})
    if not trafo_ids:
        return {"trafos_a_jusante": 0, "trafos_com_leitura": 0, "soma": 0.0, "unidade": None,
                "avisos": resultado["avisos"], "ids": []}
    corte = _agora() - datetime.timedelta(minutes=janela_min)
    cur.execute(
        "SELECT DISTINCT ON (ativo) ativo, valor, unidade FROM plat.rede_medicao "
        "WHERE ativo = ANY(%s::uuid[]) AND grandeza = %s AND ts >= %s ORDER BY ativo, ts DESC",
        (trafo_ids, grandeza, corte),
    )
    linhas = cur.fetchall()
    unidade = linhas[0]["unidade"] if linhas else None
    return {"trafos_a_jusante": len(trafo_ids), "trafos_com_leitura": len(linhas),
            "soma": sum(r["valor"] for r in linhas), "unidade": unidade, "avisos": resultado["avisos"],
            "ids": trafo_ids}


__all__ = [
    "grandezas_catalogo", "publicar_leituras", "ativo_config_upsert", "ativo_config_obter", "ultima_leitura",
    "serie", "avaliar_alarme_carregamento", "agregado_jusante",
]
