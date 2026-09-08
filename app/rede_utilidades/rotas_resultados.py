"""O que se faz com o resultado de um traçado (item L4-02-f-resultados-e-exportacao).

Quatro rotas, todas sobre o MESMO motor de traçado (`despacho.executar`), nunca um segundo:

  `POST /api/rede/{id}/tracar/exportar?formato=csv|geojson|gpkg` — traça e devolve o arquivo. O CSV abre com
  as colunas id, tipo, grupo, terminal, comprimento_m e nivel; o GeoJSON traz a geometria de cada elemento e
  a procedência do traçado; o GeoPackage é um arquivo SQLite legível por qualquer leitor de dado espacial.

  `POST /api/rede/{id}/tracar/camada` — traça e SALVA o resultado como item de catálogo (`camada_tracado`),
  com a procedência que o portão pede: rede, configuração, pontos de partida, versão da topologia e data. A
  camada guarda a geometria e a tabela do resultado daquele instante — é uma fotografia, e o campo
  `procedencia.topologia_construido_em` diz de quando.

  `GET /api/rede/{id}/tracados` — o histórico da PESSOA: os 20 últimos traçados dela nesta rede, com o pedido
  inteiro, para repetir.

  `POST /api/rede/{id}/tracados/{execucao_id}/repetir` — roda de novo o pedido guardado, sobre a rede como
  ela está HOJE. A contagem pode não ser a mesma da execução original: a rede muda, e é por isso que o
  histórico guarda o pedido e não o resultado.

Privilégio: traçar é leitura (mesmo privilégio de `POST .../tracar`); salvar como camada cria item de
catálogo e por isso exige `conteudo.criar`, como qualquer outra porta que escreve no catálogo."""

import json
import uuid as uuid_mod

import psycopg2
from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from app import db, limites
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import despacho, resultados
from app.rede_utilidades.modelos import CamadaDoTracadoEntrada, TracadoEntrada

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — resultado de traçado"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
CRIAR = {"x-auth": "S/T", "x-privilegio": "conteudo.criar"}


def _uuid_ok(valor: str, erro: str = "rede_inexistente", texto: str = "rede inexistente") -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, erro, texto) from e


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


def _config_id_ok(corpo: TracadoEntrada) -> None:
    if corpo.config_id is None:
        return
    try:
        corpo.config_id = str(uuid_mod.UUID(corpo.config_id))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, "config_inexistente", "configuração de traçado inexistente nesta rede") from e


def _procedencia(cur, rede_id: str, corpo: TracadoEntrada, resultado: dict) -> dict:
    """A procedência do resultado, com os campos que o portão do item nomeia. Campo que não se sabe fica
    nulo — nunca um valor inventado (regra da casa: procedência errada é pior que procedência nenhuma)."""
    cur.execute("SELECT nome, construido_em FROM plat.rede r "
                "LEFT JOIN plat.rede_topo_resumo t ON t.rede_id = r.id WHERE r.id = %s::uuid", (rede_id,))
    linha = cur.fetchone() or {}
    codigo = None
    if corpo.config_id:
        cur.execute("SELECT codigo FROM plat.rede_config_tracado WHERE id = %s::uuid", (corpo.config_id,))
        achado = cur.fetchone()
        codigo = achado["codigo"] if achado else None
    return {
        "rede_id": rede_id,
        "rede_nome": linha.get("nome"),
        "tipo": resultado.get("tipo") or corpo.tipo,
        "config_id": corpo.config_id,
        "config_codigo": codigo,
        "pontos_partida": [p.model_dump(mode="json", exclude_none=True) for p in corpo.pontos_partida],
        "barreiras": [b.model_dump(mode="json", exclude_none=True) for b in corpo.barreiras],
        "topologia_construido_em": iso(linha.get("construido_em")),
        "gerador": "plat rede_utilidades.resultados v1",
    }


def _tracar_para_saida(rid: str, corpo: TracadoEntrada, auth: Auth) -> tuple:
    """Traça e devolve (linhas da tabela, agregações, procedência) — o preparo comum de exportar e salvar."""
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        resultado = despacho.executar(cur, auth.tenant_id, rid, corpo, auth.usuario_id)
        linhas = resultados.tabela(cur, rid, resultado.get("elementos") or [])
        if len(linhas) > limites.TRACADO_EXPORTACAO_MAX:
            raise ErroAPI(413, "resultado_grande_demais",
                          f"o traçado devolveu {len(linhas)} elementos e o teto de exportação é "
                          f"{limites.TRACADO_EXPORTACAO_MAX}; estreite o traçado com barreiras ou filtro")
        return linhas, resultados.agregar(linhas), _procedencia(cur, rid, corpo, resultado), resultado


def _exportar_sincrono(rid: str, corpo: TracadoEntrada, formato: str, auth: Auth,
                       request: Request) -> tuple[bytes, int]:
    linhas, agregacoes, procedencia, _ = _tracar_para_saida(rid, corpo, auth)
    bruto = resultados.exportar(linhas, formato, procedencia | {"agregacoes": agregacoes})
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "redes/tracar_exportar", "rede", rid,
                         {"formato": formato, "contagem": len(linhas)})
    return bruto, len(linhas)


@router.post("/{rede_id}/tracar/exportar", status_code=200, openapi_extra=LER)
async def exportar_tracado(rede_id: str, corpo: TracadoEntrada, request: Request, formato: str = "csv",
                           auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """O mesmo pedido de `POST .../tracar`, devolvido como arquivo. `formato=csv` (padrão), `geojson` ou
    `gpkg`. Nenhum elemento se perde entre os três: os três saem da MESMA lista de linhas."""
    rid = _uuid_ok(rede_id)
    if formato not in resultados.FORMATOS:
        raise ErroAPI(422, "formato_desconhecido",
                      f"formato tem de ser um de {', '.join(resultados.FORMATOS)}")
    _config_id_ok(corpo)
    bruto, contagem = await run_in_threadpool(_exportar_sincrono, rid, corpo, formato, auth, request)
    return Response(
        content=bruto, media_type=resultados.MEDIA_TYPE[formato],
        headers={"Cache-Control": "no-store", "X-Plat-Contagem": str(contagem),
                 "Content-Disposition": f'attachment; filename="tracado.{resultados.EXTENSAO[formato]}"'},
    )


def _camada_sincrono(rid: str, corpo: CamadaDoTracadoEntrada, auth: Auth, request: Request) -> dict:
    pedido = TracadoEntrada(**corpo.model_dump(exclude={"titulo"}))
    linhas, agregacoes, procedencia, resultado = _tracar_para_saida(rid, pedido, auth)
    geometrias = [linha["geometria"] for linha in linhas if linha["geometria"]]
    dados = {
        "fonte": "tracado_de_rede",
        "procedencia": procedencia,
        "agregacoes": agregacoes,
        "contagem": len(linhas),
        "elementos": [{coluna: linha[coluna] for coluna in resultados.COLUNAS_TABELA} for linha in linhas],
        "geometria": {"type": "GeometryCollection", "geometries": geometrias} if geometrias else None,
    }
    with db.db(auth.contexto()) as cur:
        try:
            cur.execute(
                "INSERT INTO plat.item (tenant_id, tipo, titulo, dono_id, dados, criado_por, modificado_por) "
                "VALUES (%s, 'camada_tracado', %s, %s, %s::jsonb, %s, %s) RETURNING id, titulo, criado_em",
                (auth.tenant_id, corpo.titulo.strip()[:250], auth.usuario_id,
                 json.dumps(dados, ensure_ascii=False, default=str), auth.usuario_id, auth.usuario_id),
            )
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        item = cur.fetchone()
        registrar_evento(cur, request, "redes/tracar_camada", "item", str(item["id"]),
                         {"rede_id": rid, "contagem": len(linhas),
                          "tipo": resultado.get("tipo") or pedido.tipo})
    return {"item_id": str(item["id"]), "titulo": item["titulo"], "criado_em": iso(item["criado_em"]),
            "contagem": len(linhas), "agregacoes": agregacoes, "procedencia": procedencia}


@router.post("/{rede_id}/tracar/camada", status_code=201, openapi_extra=CRIAR)
async def salvar_tracado_como_camada(rede_id: str, corpo: CamadaDoTracadoEntrada, request: Request,
                                     auth: Auth = autenticado("conteudo.criar")):
    """Traça e guarda o resultado como item de catálogo do tipo `camada_tracado`, com procedência."""
    rid = _uuid_ok(rede_id)
    pedido = TracadoEntrada(**corpo.model_dump(exclude={"titulo"}))
    _config_id_ok(pedido)
    corpo.config_id = pedido.config_id
    return await run_in_threadpool(_camada_sincrono, rid, corpo, auth, request)


def _historico_sincrono(rid: str, limite: int, auth: Auth) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute(
            "SELECT id, tipo, config_id, pedido, contagem, duracao_ms, topologia_construido_em, criado_em "
            "FROM plat.rede_tracado_execucao WHERE rede_id = %s::uuid AND usuario_id = %s "
            "ORDER BY criado_em DESC, id DESC LIMIT %s",
            (rid, auth.usuario_id, limite),
        )
        itens = [{
            "id": str(r["id"]), "tipo": r["tipo"],
            "config_id": str(r["config_id"]) if r["config_id"] else None,
            "pedido": r["pedido"], "contagem": r["contagem"], "duracao_ms": r["duracao_ms"],
            "topologia_construido_em": iso(r["topologia_construido_em"]), "criado_em": iso(r["criado_em"]),
        } for r in cur.fetchall()]
    return {"itens": itens, "limite": limite}


@router.get("/{rede_id}/tracados", openapi_extra=LER)
async def listar_tracados(rede_id: str, limite: int = despacho.HISTORICO_LIMITE,
                          auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Os últimos traçados de QUEM PEDE nesta rede (padrão e teto: 20), do mais novo ao mais velho, com o
    pedido inteiro para repetir."""
    rid = _uuid_ok(rede_id)
    if not 1 <= limite <= despacho.HISTORICO_LIMITE:
        raise ErroAPI(422, "limite_invalido", f"limite entre 1 e {despacho.HISTORICO_LIMITE}")
    return await run_in_threadpool(_historico_sincrono, rid, limite, auth)


def _repetir_sincrono(rid: str, execucao_id: str, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute("SELECT pedido, contagem FROM plat.rede_tracado_execucao "
                    "WHERE id = %s::uuid AND rede_id = %s::uuid AND usuario_id = %s",
                    (execucao_id, rid, auth.usuario_id))
        linha = cur.fetchone()
        if linha is None:
            raise ErroAPI(404, "execucao_inexistente", "traçado inexistente no seu histórico desta rede")
        corpo = TracadoEntrada(**linha["pedido"])
        resultado = despacho.executar(cur, auth.tenant_id, rid, corpo, auth.usuario_id)
        resultado["agregacoes"] = resultados.agregar(
            resultados.tabela(cur, rid, resultado.get("elementos") or [], com_geometria=False))
        resultado["contagem_anterior"] = linha["contagem"]
        if auth.leitura_inquilino is None:
            resultado["execucao_id"] = despacho.registrar(
                cur, auth.tenant_id, rid, auth.usuario_id, corpo, resultado)
        registrar_evento(cur, request, "redes/tracar", "rede", rid,
                         {"tipo": resultado.get("tipo") or corpo.tipo, "repetido_de": execucao_id,
                          "contagem": resultado.get("contagem")})
    return resultado


@router.post("/{rede_id}/tracados/{execucao_id}/repetir", status_code=200, openapi_extra=LER)
async def repetir_tracado(rede_id: str, execucao_id: str, request: Request,
                          auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Roda de novo o pedido guardado, sobre a rede de HOJE. A resposta traz `contagem_anterior` ao lado da
    contagem nova: se a rede mudou desde então, os dois números divergem, e é isso que se quer ver."""
    rid = _uuid_ok(rede_id)
    eid = _uuid_ok(execucao_id, "execucao_inexistente", "traçado inexistente no seu histórico desta rede")
    return await run_in_threadpool(_repetir_sincrono, rid, eid, auth, request)
