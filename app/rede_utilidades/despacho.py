"""O despacho de um pedido de traçado ao motor certo (item L4-02-f-resultados-e-exportacao).

Estava dentro da rota `POST /api/rede/{id}/tracar` (`rotas_topologia.py`). Saiu para cá porque o item
L4-02-f acrescenta três portas que precisam do MESMO traçado: exportar o resultado em arquivo, salvar o
resultado como camada e repetir um traçado do histórico. Duplicar o despacho seria ter quatro motores com
um nome só; aqui ele é um, e as quatro rotas o chamam.

Nada mudou na escolha: `tracado.py` para conectado/subrede, `direcao.py` para montante/jusante, `lacos.py`
para laços, isolados e caminho mais curto, `config_tracado.py` quando o pedido vem de uma configuração
salva. O que este módulo acrescenta é o REGISTRO da execução no histórico da pessoa, uma linha por traçado
executado, guardando o PEDIDO (nunca o resultado, que envelheceria junto com a rede)."""

import json

import psycopg2

from app import limites
from app.auth import comum as auth_comum
from app.erros import ErroAPI
from app.rede_utilidades import config_tracado, direcao, fluxo, lacos, tracado

HISTORICO_LIMITE = limites.TRACADO_HISTORICO_MAX  # "os 20 últimos", portão do item L4-02-f


def executar(cur, tenant_id: int, rede_id: str, corpo, usuario_id: int) -> dict:
    """Roda o traçado descrito por `corpo` (o modelo `TracadoEntrada`) e devolve o resultado do motor."""
    barreiras = [b.model_dump() for b in corpo.barreiras]
    try:
        if corpo.config_id is not None:
            # item L4-02-e: o pedido inteiro (tipo, barreiras de condição e de filtro, filtro de saída,
            # funções e tipo de resultado) vem da configuração salva; do corpo só valem os pontos de
            # partida e as barreiras pontuais deste traçado.
            ficha = config_tracado.obter(cur, rede_id, corpo.config_id, usuario_id)
            return config_tracado.executar(
                cur, tenant_id, rede_id, ficha,
                [p.model_dump() for p in corpo.pontos_partida], barreiras)
        if corpo.tipo is None:
            raise ErroAPI(422, "tipo_obrigatorio",
                          "informe 'tipo' ou 'config_id' (a configuração salva traz o tipo)")
        if corpo.tipo in tracado.TIPOS_TRACADO:
            return tracado.tracar(
                cur, tenant_id, rede_id, corpo.tipo,
                [p.model_dump() for p in corpo.pontos_partida], barreiras,
            )
        if corpo.tipo in fluxo.TIPOS_FLUXO:
            # o sentido vem do controlador de subrede (L4-02-b) ou do atributo de fluxo (L4-18); quem
            # escolhe é `direcao.tracar_direcao`, e a resposta sempre diz qual foi em `origem_direcao`.
            return direcao.tracar_direcao(
                cur, tenant_id, rede_id, corpo.tipo,
                [p.model_dump() for p in corpo.pontos_partida], barreiras, corpo.origem_direcao,
            )
        if corpo.tipo == "lacos":
            return lacos.detectar_lacos(cur, tenant_id, rede_id, barreiras)
        if corpo.tipo == "isolados":
            return lacos.isolados(cur, tenant_id, rede_id, corpo.categoria_controlador, barreiras)
        if corpo.tipo == "caminho_curto":
            if len(corpo.pontos_partida) != 1:
                raise ErroAPI(422, "origem_invalida",
                              "caminho_curto exige exatamente um ponto em pontos_partida (a origem)")
            if corpo.destino is None:
                raise ErroAPI(422, "destino_obrigatorio", "caminho_curto exige o campo 'destino'")
            return lacos.caminho_curto(
                cur, tenant_id, rede_id, corpo.pontos_partida[0].model_dump(),
                corpo.destino.model_dump(), corpo.atributo_custo, corpo.k, barreiras,
            )
        # nunca alcançado — o pattern do pydantic já barrou; guarda por clareza
        raise ErroAPI(422, "tipo_invalido", f"tipo desconhecido: {corpo.tipo}")
    except psycopg2.Error as e:  # noqa: BLE001 — erro do banco vira mensagem legível, nunca 500 cru
        raise auth_comum.erro_do_banco(e) from e


def registrar(cur, tenant_id: int, rede_id: str, usuario_id: int, corpo, resultado: dict) -> str | None:
    """Grava a execução no histórico da pessoa e devolve o id da linha. Devolve `None` sem gravar quando o
    chamador não é usuário DESTE inquilino (superadmin lendo outro inquilino): a política de escrita da
    tabela exige o vínculo, e o histórico é da casa que traçou."""
    if not usuario_id:
        return None
    cur.execute("SELECT construido_em FROM plat.rede_topo_resumo WHERE rede_id = %s::uuid", (rede_id,))
    linha = cur.fetchone()
    cur.execute(
        "INSERT INTO plat.rede_tracado_execucao (tenant_id, rede_id, usuario_id, tipo, config_id, pedido, "
        "contagem, duracao_ms, topologia_construido_em) "
        "VALUES (%s, %s::uuid, %s, %s, %s::uuid, %s::jsonb, %s, %s, %s) RETURNING id",
        (tenant_id, rede_id, usuario_id, resultado.get("tipo") or corpo.tipo or "configuracao",
         corpo.config_id, json.dumps(corpo.model_dump(mode="json"), default=str),
         resultado.get("contagem"), resultado.get("duracao_ms"),
         linha["construido_em"] if linha else None),
    )
    return str(cur.fetchone()["id"])
