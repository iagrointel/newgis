"""Núcleo das réplicas (item L2-13-b): criar o recorte, gerar o pacote, sincronizar.

Três decisões que valem ler antes de mexer:

1. O RELÓGIO É `plat.feicao_historico.id`. Não existe tabela de rastreio nova. O gatilho de histórico do
   L2-03-edicao já grava toda escrita (inclusive o DELETE, que a tabela de camada não guarda), e o
   `bigserial` dessa tabela é um contador monotônico por inquilino. "O que mudou desde a geração G" é
   `id > G` sobre um índice — nunca uma varredura da camada.

2. A ESCRITA PASSA PELA PORTA ÚNICA. `_aplicar_*` chamam `app.edicao.servico`, o mesmo caminho de
   `POST /api/camadas/{id}/edicoes` (L2-03-a): mesma validação de tipo, domínio, geometria, RLS e
   "só as próprias feições". A réplica acrescenta a POLÍTICA DE CONFLITO em volta, não uma segunda
   porta de escrita.

3. O QUE VOLTA PARA O CLIENTE NÃO ECOA O QUE ELE ACABOU DE SUBIR. As mudanças baixadas excluem os
   `globalid` tocados no próprio lote. Limitação honesta: `id` é atribuído no INSERT e não na confirmação
   da transação, então uma transação concorrente que confirme depois da nossa leitura pode ter `id` menor
   que a geração nova e só ser vista na sincronização SEGUINTE. Isso atrasa uma mudança, nunca a perde
   (o ponteiro só avança até o que foi lido), e é o preço de não segurar trava sobre a camada inteira.
"""

from __future__ import annotations

import datetime
import json
import re
import uuid
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import Request

from app import limites, objetos
from app.auth.sessao import Auth
from app.catalogo import comum
from app.edicao import servico as edicao
from app.edicao.modelos import EdicoesEntrada, FeicaoApagar, FeicaoAtualizar
from app.erros import ErroAPI
from app.replica import pacote
from app.replica.modelos import (
    CamadaBaixada,
    Conflito,
    MudancaServidor,
    ReplicaEntrada,
    SincronizarEntrada,
    SincronizarSaida,
)

CONTENT_TYPE = "application/geopackage+sqlite3"
_RE_NOME_GPKG = re.compile(r"^[a-z][a-z0-9_]{0,58}$")


# ---------------------------------------------------------------- leitura
def _replica_ou_404(cur, replica_id: str, para_escrita: bool = False) -> dict:
    """A RLS de `plat.replica` já isola por inquilino: réplica de outro inquilino é 404, não 403."""
    trava = " FOR UPDATE" if para_escrita else ""
    cur.execute(f"SELECT *, ST_AsGeoJSON(extensao) AS extensao_geojson FROM plat.replica WHERE id = %s::uuid{trava}",
                (replica_id,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "replica_inexistente", "réplica inexistente")
    return dict(r)


def _exigir_dono(auth: Auth, replica: dict) -> None:
    """A réplica é do dispositivo de UMA pessoa: só o dono, ou quem administra conteúdo, mexe nela."""
    if replica["dono_id"] != auth.usuario_id and not auth.tem("conteudo.editar_tudo"):
        raise ErroAPI(403, "replica_de_outro_usuario", "esta réplica é de outro usuário")


def _camadas_da_replica(cur, replica: dict) -> list[dict]:
    cur.execute(
        "SELECT camada_id, nome_gpkg, filtro, geracao_servidor, feicoes FROM plat.replica_camada "
        "WHERE replica_id = %s::uuid ORDER BY nome_gpkg",
        (replica["id"],),
    )
    saida = []
    for linha in cur.fetchall():
        _item, dados = edicao.camada_ou_404(cur, str(linha["camada_id"]))
        saida.append({**dict(linha), "camada_id": str(linha["camada_id"]), "dados": dados})
    return saida


def serializar(replica: dict, camadas: list[dict]) -> dict:
    return {
        "id": str(replica["id"]),
        "nome": replica["nome"],
        "estado": replica["estado"],
        "geracao": replica["geracao"],
        "politica_conflito": replica["politica_conflito"],
        "dispositivo": replica["dispositivo"],
        "com_anexos": replica["com_anexos"],
        "dono_id": replica["dono_id"],
        "job_id": str(replica["job_id"]) if replica.get("job_id") else None,
        "pacote_bytes": replica.get("pacote_bytes"),
        "pacote_sha256": replica.get("pacote_sha256"),
        "erro": replica.get("erro"),
        "criada_em": replica["criada_em"],
        "expira_em": replica["expira_em"],
        "expirada": expirada(replica),
        "ultima_sincronizacao": replica.get("ultima_sincronizacao"),
        "extensao": json.loads(replica["extensao_geojson"]) if replica.get("extensao_geojson") else None,
        "camadas": [
            {"camada_id": c["camada_id"], "nome_gpkg": c["nome_gpkg"], "filtro": c["filtro"],
             "geracao_servidor": c["geracao_servidor"], "feicoes": c["feicoes"]}
            for c in camadas
        ],
    }


def expirada(replica: dict) -> bool:
    return replica["expira_em"] <= datetime.datetime.now(datetime.UTC)


def _exigir_viva(replica: dict) -> None:
    """Réplica vencida NÃO sincroniza: além da validade, o rastreio de que ela depende pode já ter sido
    expurgado (limites.REPLICA_RASTREIO_RETENCAO_DIAS), e uma sincronização com rastreio incompleto
    devolveria um conjunto de mudanças menor do que o real, em silêncio. O caminho é criar réplica nova."""
    if expirada(replica):
        raise ErroAPI(
            409, "replica_expirada",
            f"a réplica venceu em {replica['expira_em'].isoformat()}; crie uma réplica nova "
            f"(o rastreio é retido por {limites.REPLICA_RASTREIO_RETENCAO_DIAS} dias)",
            {"expira_em": replica["expira_em"].isoformat(),
             "validade_dias": limites.REPLICA_VALIDADE_DIAS,
             "retencao_rastreio_dias": limites.REPLICA_RASTREIO_RETENCAO_DIAS},
        )
    if replica["estado"] != "pronta":
        raise ErroAPI(409, "replica_nao_pronta",
                      f"a réplica está em {replica['estado']}; só réplica pronta sincroniza",
                      {"estado": replica["estado"]})


# ---------------------------------------------------------------- criação
def _nome_gpkg(titulo: str, usados: set[str]) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", (titulo or "camada").lower()).strip("_")[:50] or "camada"
    if not base[0].isalpha():
        base = "c_" + base
    nome, n = base, 1
    while nome in usados or not _RE_NOME_GPKG.match(nome):
        n += 1
        nome = f"{base[:50]}_{n}"
    usados.add(nome)
    return nome


def criar(cur, request: Request, auth: Auth, corpo: ReplicaEntrada) -> dict:
    cur.execute("SELECT count(*) AS n FROM plat.replica WHERE dono_id = %s AND expira_em > now()",
                (auth.usuario_id,))
    if int(cur.fetchone()["n"]) >= limites.REPLICA_POR_USUARIO:
        raise ErroAPI(413, "replicas_demais",
                      f"o usuário já tem {limites.REPLICA_POR_USUARIO} réplicas vivas; apague uma antes",
                      {"teto": limites.REPLICA_POR_USUARIO})

    extensao_txt = json.dumps(corpo.extensao) if corpo.extensao else None
    if extensao_txt:
        cur.execute("SELECT ST_GeometryType(ST_GeomFromGeoJSON(%s)) AS tipo", (extensao_txt,))
        if cur.fetchone()["tipo"] != "ST_Polygon":
            raise ErroAPI(422, "extensao_invalida", "a extensão da réplica tem de ser um Polygon GeoJSON")

    replica_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO plat.replica(id, tenant_id, nome, dono_id, dispositivo, politica_conflito, extensao, "
        "com_anexos, expira_em) VALUES (%s::uuid, plat.tenant_atual(), %s, %s, %s, %s, "
        "CASE WHEN %s IS NULL THEN NULL ELSE ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) END, %s, "
        "now() + make_interval(days => %s)) RETURNING *",
        (replica_id, corpo.nome, auth.usuario_id, corpo.dispositivo, corpo.politica_conflito,
         extensao_txt, extensao_txt, corpo.anexos, limites.REPLICA_VALIDADE_DIAS),
    )
    replica = dict(cur.fetchone())

    usados: set[str] = set()
    for entrada in corpo.camadas:
        item, dados = edicao.camada_ou_404(cur, comum.uuid_ok(entrada.camada_id))
        # o filtro é analisado AGORA (não na hora do job): filtro inválido tem de reprovar a chamada do
        # usuário, com 422, não virar job que falha meia hora depois
        pacote.sql_da_camada(cur, dados, entrada.filtro, extensao_txt)
        nome = entrada.nome_gpkg or _nome_gpkg(item["titulo"], usados)
        if entrada.nome_gpkg:
            if entrada.nome_gpkg in usados:
                raise ErroAPI(422, "nome_gpkg_repetido",
                              f"duas camadas com o mesmo nome no pacote: {entrada.nome_gpkg}")
            usados.add(entrada.nome_gpkg)
        cur.execute(
            "INSERT INTO plat.replica_camada(replica_id, camada_id, tenant_id, nome_gpkg, filtro) "
            "VALUES (%s::uuid, %s::uuid, plat.tenant_atual(), %s, %s)",
            (replica_id, entrada.camada_id, nome, entrada.filtro),
        )
    comum.registrar_evento(
        cur, request, "replicas/criar", "replica", replica_id,
        {"camadas": len(corpo.camadas), "politica_conflito": corpo.politica_conflito,
         "com_anexos": corpo.anexos, "com_extensao": extensao_txt is not None},
    )
    return replica


def relogio(cur, dados: dict) -> int:
    """Alto da marca do relógio lógico desta camada: maior `plat.feicao_historico.id` já gravado para a
    tabela física. Zero quando a camada nunca foi escrita depois do gatilho de histórico existir."""
    cur.execute(
        "SELECT coalesce(max(id), 0) AS g FROM plat.feicao_historico WHERE schema_dado = %s AND tabela_dado = %s",
        (dados["schema"], dados["tabela"]),
    )
    return int(cur.fetchone()["g"])


def gerar_pacote(cur, replica_id: str, progresso=None) -> dict:
    """Gera o GeoPackage e guarda no armazenamento de objetos. Chamada pela tarefa `replicas.criar`
    (app/replica/tarefas.py); é aqui, e não na tarefa, que mora a lógica — a tarefa só empresta o job."""
    import tempfile
    from pathlib import Path

    replica = _replica_ou_404(cur, replica_id, para_escrita=True)
    camadas = _camadas_da_replica(cur, replica)
    # o relógio é lido ANTES de exportar: o que mudar durante a exportação volta na primeira
    # sincronização (entrega ao menos uma vez), nunca se perde
    for camada in camadas:
        camada["geracao_servidor"] = relogio(cur, camada["dados"])
    if progresso:
        progresso(20, f"exportando {len(camadas)} camada(s)")

    with tempfile.TemporaryDirectory(prefix="plat-replica-") as tmp:
        destino = Path(tmp) / "replica.gpkg"
        contagens = pacote.escrever(cur, replica, camadas, destino)
        if progresso:
            progresso(80, "guardando o pacote")
        conteudo = destino.read_bytes()
    guardado = objetos.guardar(cur, "replica", conteudo, CONTENT_TYPE, item_id=replica_id)

    for camada in camadas:
        cur.execute(
            "UPDATE plat.replica_camada SET geracao_servidor = %s, feicoes = %s "
            "WHERE replica_id = %s::uuid AND camada_id = %s::uuid",
            (camada["geracao_servidor"], contagens.get(camada["camada_id"], 0), replica_id, camada["camada_id"]),
        )
    cur.execute(
        "UPDATE plat.replica SET estado = 'pronta', erro = NULL, pacote_chave = %s, pacote_bytes = %s, "
        "pacote_sha256 = %s WHERE id = %s::uuid",
        (guardado["chave"], guardado["bytes"], guardado["sha256"], replica_id),
    )
    if cur.rowcount != 1:  # RLS sem contexto de inquilino tocaria ZERO linha em silêncio
        raise ErroAPI(500, "replica_nao_atualizada", "a réplica não foi marcada como pronta")
    return {"replica_id": replica_id, "camadas": len(camadas), "feicoes": sum(contagens.values()),
            "bytes": guardado["bytes"], "sha256": guardado["sha256"]}


# ---------------------------------------------------------------- sincronização
def _versao_atual(cur, dados: dict, globalid: str) -> dict | None:
    cur.execute(
        f'SELECT fid, globalid, versao, criado_por FROM "{dados["schema"]}"."{dados["tabela"]}" '
        f"WHERE globalid = %s FOR UPDATE",
        (globalid,),
    )
    return cur.fetchone()


def _aplicar_camada(
    cur, request: Request, auth: Auth, replica: dict, camada: dict, mudancas, saida: SincronizarSaida
) -> set[str]:
    """Aplica um lote de uma camada pela porta única do L2-03-a, resolvendo conflito pela política da
    réplica. Devolve os `globalid` tocados (para não os devolver na descida)."""
    dados = camada["dados"]
    politica = replica["politica_conflito"]
    tocados: set[str] = set()
    corpo_base = EdicoesEntrada(modo="parcial", corrigir_geometria=True)

    # ADICIONAR: sem versão anterior com que discordar; a defesa contra duplicar é a idempotência do LOTE
    for feicao in mudancas.adicionar:
        resultado, _avisos = edicao.inserir(cur, auth, dados, corpo_base, feicao)
        saida.subidas["adicionadas"] = saida.subidas.get("adicionadas", 0) + 1
        tocados.add(str(resultado.id))

    for feicao in mudancas.atualizar:
        atual = _versao_atual(cur, dados, feicao.id)
        if atual is None:
            # apagada no servidor enquanto o cliente editava: é conflito, nunca um insert silencioso
            saida.conflitos.append(Conflito(
                camada_id=camada["camada_id"], id=feicao.id, operacao="atualizar",
                versao_cliente=feicao.versao, versao_servidor=None,
                resolucao="servidor" if politica != "cliente_vence" else "pendente",
            ))
            continue
        if atual["versao"] != feicao.versao:
            resolucao = {"servidor_vence": "servidor", "cliente_vence": "cliente", "pergunta": "pendente"}[politica]
            saida.conflitos.append(Conflito(
                camada_id=camada["camada_id"], id=feicao.id, operacao="atualizar",
                versao_cliente=feicao.versao, versao_servidor=atual["versao"], resolucao=resolucao,
                atual=edicao.obter_feicao(cur, camada["camada_id"], feicao.id),
            ))
            if resolucao != "cliente":
                continue
            feicao = FeicaoAtualizar(**{**feicao.model_dump(), "versao": atual["versao"]})
        edicao.atualizar(cur, auth, dados, corpo_base, feicao)
        saida.subidas["atualizadas"] = saida.subidas.get("atualizadas", 0) + 1
        tocados.add(feicao.id)

    for feicao in mudancas.apagar:
        atual = _versao_atual(cur, dados, feicao.id)
        if atual is None:
            continue  # já não existe: apagar duas vezes é a mesma coisa que apagar uma
        if feicao.versao is not None and atual["versao"] != feicao.versao:
            resolucao = {"servidor_vence": "servidor", "cliente_vence": "cliente", "pergunta": "pendente"}[politica]
            saida.conflitos.append(Conflito(
                camada_id=camada["camada_id"], id=feicao.id, operacao="apagar",
                versao_cliente=feicao.versao, versao_servidor=atual["versao"], resolucao=resolucao,
                atual=edicao.obter_feicao(cur, camada["camada_id"], feicao.id),
            ))
            if resolucao != "cliente":
                continue
        edicao.apagar(cur, auth, dados, corpo_base, FeicaoApagar(id=feicao.id))
        saida.subidas["apagadas"] = saida.subidas.get("apagadas", 0) + 1
        tocados.add(feicao.id)
    return tocados


def _baixar_camada(cur, camada: dict, ate: int, excluir: set[str], extensao_geojson: str | None) -> CamadaBaixada:
    """Mudanças do servidor desde a geração do cliente: os `globalid` que aparecem no rastreio no intervalo
    (desde, ate], lidos DEPOIS no estado atual da tabela. Ler o estado atual (e não reproduzir o histórico
    passo a passo) é o que faz três edições seguidas da mesma feição virarem UMA mudança para o campo.

    Feição que saiu do recorte (filtro ou extensão) vai como `apagar`: da janela desta réplica, ela deixou
    de existir — é o mesmo que a Esri faz com `extract-changes` sobre um replica filter."""
    dados = camada["dados"]
    desde = int(camada["geracao_servidor"])
    cur.execute(
        "SELECT DISTINCT globalid FROM plat.feicao_historico WHERE schema_dado = %s AND tabela_dado = %s "
        "AND id > %s AND id <= %s ORDER BY globalid LIMIT %s",
        (dados["schema"], dados["tabela"], desde, ate, limites.REPLICA_BAIXAR_MAX + 1),
    )
    ids = [str(r["globalid"]) for r in cur.fetchall() if str(r["globalid"]) not in excluir]
    truncado = len(ids) > limites.REPLICA_BAIXAR_MAX
    ids = ids[: limites.REPLICA_BAIXAR_MAX]

    saida = CamadaBaixada(camada_id=camada["camada_id"], nome_gpkg=camada["nome_gpkg"], desde=desde, ate=ate,
                          truncado=truncado)
    if not ids:
        return saida
    dentro = pacote.sql_da_camada(cur, dados, camada["filtro"], extensao_geojson)
    tem_geom = dados.get("geometria") not in (None, "nenhuma")
    extra = ", ST_AsGeoJSON(t.geom) AS __geom_geojson" if tem_geom else ""
    cur.execute(f"SELECT t.*{extra} FROM ({dentro}) t WHERE t.globalid::text = ANY(%s)", (ids,))
    vivas = {str(r["globalid"]): r for r in cur.fetchall()}
    campos = [c["nome"] for c in dados.get("campos") or []]
    for globalid in ids:
        linha = vivas.get(globalid)
        if linha is None:
            saida.mudancas.append(MudancaServidor(operacao="apagar", id=globalid))
            continue
        geometria = json.loads(linha["__geom_geojson"]) if linha.get("__geom_geojson") else None
        saida.mudancas.append(MudancaServidor(
            operacao="atualizar" if linha["versao"] > 1 else "inserir",
            id=globalid, fid=linha["fid"], versao=linha["versao"],
            atributos={c: linha.get(c) for c in campos if c in linha}, geometria=geometria,
        ))
    return saida


def sincronizar(cur, request: Request, auth: Auth, replica_id: str, corpo: SincronizarEntrada) -> SincronizarSaida:
    replica = _replica_ou_404(cur, replica_id, para_escrita=True)
    _exigir_dono(auth, replica)

    cur.execute(
        "SELECT resposta, geracao_depois FROM plat.replica_sincronizacao "
        "WHERE replica_id = %s::uuid AND idempotencia = %s",
        (replica_id, corpo.idempotencia),
    )
    ja = cur.fetchone()
    if ja is not None:
        # lote repetido: devolve a MESMA resposta e aplica ZERO. `repetida` é a bandeira que o cliente lê
        # para não contar duas vezes; a geração não avança.
        anterior = SincronizarSaida(**ja["resposta"])
        anterior.repetida = True
        return anterior

    _exigir_viva(replica)
    camadas = {c["camada_id"]: c for c in _camadas_da_replica(cur, replica)}
    saida = SincronizarSaida(replica_id=replica_id, geracao=replica["geracao"],
                             subidas={"adicionadas": 0, "atualizadas": 0, "apagadas": 0})

    tocados: dict[str, set[str]] = {}
    for mudancas in corpo.camadas:
        camada = camadas.get(mudancas.camada_id)
        if camada is None:
            # camada que não é desta réplica: 404 mesmo que exista e seja legível — o pacote do campo não
            # pode virar porta para escrever em camada fora do recorte declarado
            raise ErroAPI(404, "camada_fora_da_replica", "a camada não faz parte desta réplica",
                          {"camada_id": mudancas.camada_id})
        edicao.exigir_camada_editavel(auth, camada["dados"])
        tocados[mudancas.camada_id] = _aplicar_camada(cur, request, auth, replica, camada, mudancas, saida)

    if corpo.baixar:
        for camada in camadas.values():
            ate = relogio(cur, camada["dados"])
            baixada = _baixar_camada(cur, camada, ate, tocados.get(camada["camada_id"], set()),
                                     replica.get("extensao_geojson"))
            saida.baixadas.append(baixada)
            if not baixada.truncado:
                cur.execute(
                    "UPDATE plat.replica_camada SET geracao_servidor = %s WHERE replica_id = %s::uuid "
                    "AND camada_id = %s::uuid",
                    (ate, replica_id, camada["camada_id"]),
                )
                if cur.rowcount != 1:
                    raise ErroAPI(500, "geracao_nao_avancou", "o ponteiro da camada da réplica não foi gravado")
            else:
                saida.avisos.append(
                    f"a camada {camada['nome_gpkg']} tem mais de {limites.REPLICA_BAIXAR_MAX} mudanças "
                    f"pendentes; o ponteiro não avançou, sincronize de novo para receber o resto"
                )

    cur.execute(
        "UPDATE plat.replica SET geracao = geracao + 1, ultima_sincronizacao = now() WHERE id = %s::uuid "
        "RETURNING geracao",
        (replica_id,),
    )
    if cur.rowcount != 1:
        raise ErroAPI(500, "geracao_nao_avancou", "a geração da réplica não avançou")
    saida.geracao = int(cur.fetchone()["geracao"])

    cur.execute(
        "INSERT INTO plat.replica_sincronizacao(tenant_id, replica_id, idempotencia, geracao_antes, "
        "geracao_depois, resposta) VALUES (plat.tenant_atual(), %s::uuid, %s, %s, %s, %s)",
        (replica_id, corpo.idempotencia, replica["geracao"], saida.geracao,
         psycopg2.extras.Json(json.loads(saida.model_dump_json()))),
    )
    comum.registrar_evento(
        cur, request, "replicas/sincronizar", "replica", replica_id,
        {**saida.subidas, "conflitos": len(saida.conflitos),
         "baixadas": sum(len(b.mudancas) for b in saida.baixadas), "geracao": saida.geracao},
    )
    return saida


# ---------------------------------------------------------------- listar / apagar
def listar(cur, auth: Auth) -> list[dict]:
    condicao = "" if auth.tem("conteudo.ver_tudo") else " WHERE dono_id = %s"
    parametros: list[Any] = [] if auth.tem("conteudo.ver_tudo") else [auth.usuario_id]
    cur.execute(
        "SELECT *, ST_AsGeoJSON(extensao) AS extensao_geojson FROM plat.replica" + condicao
        + " ORDER BY criada_em DESC",
        parametros,
    )
    replicas = [dict(r) for r in cur.fetchall()]
    return [serializar(r, _camadas_da_replica(cur, r)) for r in replicas]


def apagar(cur, request: Request, auth: Auth, replica_id: str) -> None:
    replica = _replica_ou_404(cur, replica_id, para_escrita=True)
    _exigir_dono(auth, replica)
    chave = replica.get("pacote_chave")
    cur.execute("DELETE FROM plat.replica WHERE id = %s::uuid", (replica_id,))
    if cur.rowcount != 1:
        raise ErroAPI(500, "replica_nao_apagada", "a réplica não foi apagada")
    comum.registrar_evento(cur, request, "replicas/apagar", "replica", replica_id, {"tinha_pacote": bool(chave)})
    if chave:
        try:
            objetos.apagar(chave)
        except (objetos.ChaveInvalida, FileNotFoundError, psycopg2.Error):
            pass  # o registro já saiu; objeto órfão é varrido pelo expurgo do armazenamento
