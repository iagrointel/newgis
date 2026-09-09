"""Rotas de ingestão vetorial (ADR 0005 seção 16; L0-04-b/c/d reduzidos a 4 formatos nesta passagem):
`POST /api/importacoes` cria a importação a partir de um item `arquivo` já enviado por `POST /api/arquivos`
(L0-11) e dispara o job `ingestao.inspecionar`; `GET` lista/detalha; `PUT .../confirmar` valida a proposta
editada CONTRA a proposta gravada (nunca contra o arquivo de novo) e dispara `ingestao.carregar`; `DELETE`
remove importações que nunca chegaram a carregar. Diferença assumida em relação ao ADR 0005 seção 3: como esta
passagem reaproveita o upload genérico do L0-11 (sem o campo `tipo_declarado` do envio em partes), o par
`{arquivo_id, formato}` de `POST /api/importacoes` é onde o tipo é declarado e conferido contra os bytes
(`app.ingestao.formatos.verificar_conteudo`) — documentado no handoff do item."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response
from pydantic import Field

from app import db, objetos
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import jsonb, registrar_evento, uuid_ok
from app.catalogo.modelos import UUID_PADRAO, JobCriado, Modelo
from app.erros import ErroAPI
from app.ingestao.formatos import FORMATOS, ConteudoNaoCorresponde
from app.ingestao.formatos import verificar_conteudo as _verificar_conteudo
from app.jobs import servico
from app.jobs.contexto import sessao_de

router = APIRouter(tags=["ingestao"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
PUBLICAR = {"x-auth": "S", "x-privilegio": "conteudo.publicar_camada"}

ESTADOS_APAGAVEIS = ("proposta", "falhou", "cancelada", "expirada")


class ImportacaoEntrada(Modelo):
    arquivo_id: str = Field(pattern=UUID_PADRAO)
    formato: str = Field(min_length=1, max_length=40)


class ConfirmarEntrada(Modelo):
    """O corpo é a proposta EDITADA (ADR 0005 seção 5): só os campos que a tela deixa mudar. Cada um é validado
    contra a proposta gravada dentro da rota (nunca um esquema fixo — a proposta é que dá as opções válidas)."""

    titulo: str | None = Field(default=None, min_length=1, max_length=250)
    crs: dict | None = None
    codificacao: dict | None = None
    geometria: dict | None = None
    campos: list[dict] | None = None
    validade: dict | None = None
    cad: dict | None = None   # DXF/DWG: unidade, camadas do desenho, blocos e pontos de controle (ADR 0020)


def _confirmar_cad(pedido: dict, proposta: dict, perguntas_pendentes: list) -> dict:
    """Valida as respostas de DXF/DWG CONTRA a proposta gravada (nunca contra o arquivo de novo, ADR 0005 §5):
    unidade da lista do formato, camadas entre as que o desenho tem, blocos como ponto ou explodidos, e de 2 a 4
    pontos de controle para a georreferência. O RMSE é calculado aqui para que a tela mostre o erro ANTES de
    disparar a carga — quem confirma vê o resíduo, não descobre depois."""
    from app.ingestao import cad as cad_mod
    from app.ingestao import georreferencia

    saida: dict = {}
    unidade = pedido.get("unidade")
    if unidade is not None:
        try:
            codigo = int(unidade)
        except (TypeError, ValueError):
            raise ErroAPI(422, "validacao", "cad.unidade deve ser o código $INSUNITS do DXF") from None
        if codigo not in cad_mod.UNIDADES or cad_mod.UNIDADES[codigo][1] is None:
            raise ErroAPI(422, "unidade_invalida", "unidade de desenho desconhecida",
                          {"opcoes": [{"codigo": c, "nome": n, "metros": m}
                                      for c, (n, m) in sorted(cad_mod.UNIDADES.items()) if m is not None]})
        saida["unidade"] = codigo
        saida["metros_por_unidade"] = cad_mod.UNIDADES[codigo][1]
        if "unidade" in perguntas_pendentes:
            perguntas_pendentes.remove("unidade")
    if pedido.get("blocos") is not None:
        if pedido["blocos"] not in ("ponto", "explodido"):
            raise ErroAPI(422, "validacao", "cad.blocos deve ser 'ponto' ou 'explodido'")
        saida["blocos"] = pedido["blocos"]
    if pedido.get("camadas") is not None:
        disponiveis = list(proposta.get("camadas_desenho") or [])
        escolhidas = [str(c) for c in pedido["camadas"]]
        faltando = [c for c in escolhidas if c not in disponiveis]
        if faltando:
            raise ErroAPI(422, "camada_desconhecida", f"camada {faltando[0][:80]!r} não está no desenho",
                          {"camadas": disponiveis})
        if not escolhidas:
            raise ErroAPI(422, "validacao", "escolha ao menos uma camada do desenho")
        saida["camadas"] = escolhidas
    pontos = (pedido.get("georreferencia") or {}).get("pontos")
    if pontos:
        try:
            origem = [(float(p["desenho"][0]), float(p["desenho"][1])) for p in pontos]
            destino = [(float(p["terreno"][0]), float(p["terreno"][1])) for p in pontos]
        except (KeyError, IndexError, TypeError, ValueError):
            raise ErroAPI(422, "validacao",
                          "cada ponto de controle precisa de desenho:[x,y] e terreno:[x,y]") from None
        try:
            ajuste = georreferencia.ajustar(origem, destino)
        except (georreferencia.PontosInsuficientes, georreferencia.AjusteImpossivel) as e:
            raise ErroAPI(422, "georreferencia_invalida", str(e)) from e
        saida["georreferencia"] = {"pontos": [{"desenho": list(o), "terreno": list(d)}
                                              for o, d in zip(origem, destino, strict=True)],
                                  "ajuste": ajuste}
    if "georreferencia" in perguntas_pendentes and (pontos or saida.get("unidade") is not None):
        perguntas_pendentes.remove("georreferencia")
    return saida


def _importacao_json(r: dict) -> dict:
    return {
        "id": str(r["id"]), "arquivo_id": str(r["arquivo_id"]), "item_id": str(r["item_id"]),
        "formato": r["formato"], "estado": r["estado"], "proposta": r["proposta"], "confirmacao": r["confirmacao"],
        "relatorio": r["relatorio"], "job_inspecao": str(r["job_inspecao"]) if r["job_inspecao"] else None,
        "job_carga": str(r["job_carga"]) if r["job_carga"] else None, "erro": r["erro"],
        "criado_em": r["criado_em"].isoformat() if r["criado_em"] else None,
    }


def _carregar(cur, auth: Auth, importacao_id: str) -> dict:
    iid = uuid_ok(importacao_id, "importacao_inexistente", "importação inexistente")
    cur.execute("SELECT * FROM plat.importacao WHERE id = %s::uuid", (iid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "importacao_inexistente", "importação inexistente")
    if r["usuario_id"] not in (None, auth.usuario_id) and not auth.tem("jobs.gerir_todos"):
        raise ErroAPI(404, "importacao_inexistente", "importação inexistente")
    return r


@router.post("/api/importacoes", status_code=202, openapi_extra=PUBLICAR)
def criar(corpo: ImportacaoEntrada, request: Request, auth: Auth = autenticado("conteudo.publicar_camada")):
    if corpo.formato not in FORMATOS:
        raise ErroAPI(
            422, "formato_nao_suportado",
            f"formato {corpo.formato!r} não suportado nesta instalação; aceitos: {sorted(FORMATOS)}",
            {"aceitos": sorted(FORMATOS)},
        )
    arquivo_id = uuid_ok(corpo.arquivo_id)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT id, dados FROM plat.item WHERE id = %s::uuid AND tipo = 'arquivo'", (arquivo_id,))
        arq = cur.fetchone()
        if arq is None:
            raise ErroAPI(404, "item_inexistente", "item de arquivo inexistente")
        chave = arq["dados"]["chave"]
    try:
        dados = objetos.ler(chave)
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise ErroAPI(404, "objeto_inexistente", "o objeto do arquivo não existe mais no armazenamento") from e
    try:
        _verificar_conteudo(corpo.formato, dados)
    except ConteudoNaoCorresponde as e:
        raise ErroAPI(422, "conteudo_nao_corresponde", str(e)) from e

    item_id = str(uuid.uuid4())
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "INSERT INTO plat.importacao(tenant_id, usuario_id, arquivo_id, item_id, formato) "
            "VALUES (%s, %s, %s::uuid, %s::uuid, %s) RETURNING id",
            (auth.tenant_id, auth.usuario_id, arquivo_id, item_id, corpo.formato),
        )
        importacao_id = str(cur.fetchone()["id"])
        registrar_evento(cur, request, "importacoes/criar", "item", arquivo_id,
                          {"importacao_id": importacao_id, "formato": corpo.formato})
    job = servico.criar(sessao_de(auth), "ingestao.inspecionar", {"importacao_id": importacao_id})
    with db.db(auth.contexto()) as cur:
        cur.execute("UPDATE plat.importacao SET job_inspecao = %s::uuid WHERE id = %s::uuid",
                     (job["id"], importacao_id))
    return {"importacao_id": importacao_id, "job_id": job["id"]}


@router.get("/api/importacoes", openapi_extra=LER)
def listar(limite: int = 50, deslocamento: int = 0, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    limite = max(1, min(200, limite))
    deslocamento = max(0, deslocamento)
    with db.db(auth.contexto()) as cur:
        if auth.tem("jobs.gerir_todos"):
            cur.execute("SELECT count(*) AS n FROM plat.importacao")
            cur.execute(
                "SELECT * FROM plat.importacao ORDER BY criado_em DESC LIMIT %s OFFSET %s", (limite, deslocamento)
            )
        else:
            cur.execute("SELECT count(*) AS n FROM plat.importacao WHERE usuario_id = %s", (auth.usuario_id,))
            cur.execute(
                "SELECT * FROM plat.importacao WHERE usuario_id = %s ORDER BY criado_em DESC LIMIT %s OFFSET %s",
                (auth.usuario_id, limite, deslocamento),
            )
        linhas = cur.fetchall()
    return {"itens": [_importacao_json(r) for r in linhas], "total": len(linhas)}


@router.get("/api/importacoes/formatos", openapi_extra=LER)
def formatos_aceitos():
    return [{"tipo": f.nome, "extensoes": list(f.extensoes), "rotulo": f.rotulo} for f in FORMATOS.values()]


@router.get("/api/importacoes/{id}", openapi_extra=LER)
def ver(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, id)
    return _importacao_json(r)


@router.put("/api/importacoes/{id}/confirmar", response_model=JobCriado, status_code=202, openapi_extra=PUBLICAR)
def confirmar(id: str, corpo: ConfirmarEntrada, request: Request,
              auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, id)
        if r["estado"] != "proposta":
            raise ErroAPI(409, "estado_invalido", f"importação em estado {r['estado']!r}; esperava 'proposta'")
        proposta = r["proposta"] or {}

        confirmacao: dict = {}
        perguntas_pendentes = list(proposta.get("perguntas") or [])

        if corpo.crs is not None:
            srid = corpo.crs.get("srid")
            if srid is not None:
                cur.execute("SELECT 1 FROM spatial_ref_sys WHERE srid = %s", (int(srid),))
                if cur.fetchone() is None:
                    raise ErroAPI(422, "srid_inexistente", f"SRID {srid} não existe em spatial_ref_sys")
                confirmacao["crs"] = {"srid": int(srid)}
                if "crs" in perguntas_pendentes:
                    perguntas_pendentes.remove("crs")
        if corpo.codificacao is not None and corpo.codificacao.get("valor"):
            confirmacao["codificacao"] = {"valor": corpo.codificacao["valor"]}
            if "codificacao" in perguntas_pendentes:
                perguntas_pendentes.remove("codificacao")
        if corpo.geometria is not None and corpo.geometria.get("escolhida"):
            opcoes_geom = proposta.get("geometria", {}).get("opcoes") or []
            escolhida = corpo.geometria["escolhida"]
            if opcoes_geom and escolhida not in opcoes_geom and escolhida != "Geometry":
                raise ErroAPI(422, "geometria_nao_permitida", f"opções válidas: {opcoes_geom}", {"opcoes": opcoes_geom})
            confirmacao["geometria"] = {"escolhida": escolhida}
            if "geometria" in perguntas_pendentes:
                perguntas_pendentes.remove("geometria")
        if corpo.validade is not None:
            acao = corpo.validade.get("acao")
            if acao not in (None, "corrigir", "descartar", "recusar"):
                raise ErroAPI(422, "validacao", "validade.acao deve ser corrigir, descartar ou recusar")
            if acao:
                confirmacao["validade"] = {"acao": acao}
        if corpo.campos is not None:
            nomes_validos = {c["nome"] for c in proposta.get("campos", [])}
            campos_saida = []
            for editado in corpo.campos:
                nome = editado.get("nome")
                if nome not in nomes_validos:
                    raise ErroAPI(422, "campo_desconhecido", f"campo {nome!r} não está na proposta", {"nome": nome})
                base = next(c for c in proposta["campos"] if c["nome"] == nome)
                tipo = editado.get("tipo", base["tipo"])
                if tipo not in base.get("opcoes_tipo", [base["tipo"]]):
                    raise ErroAPI(422, "tipo_nao_permitido", f"tipo {tipo!r} não permitido para o campo {nome!r}",
                                  {"opcoes": base.get("opcoes_tipo")})
                campos_saida.append({**base, "tipo": tipo, "importar": editado.get("importar", True)})
            # campos da proposta não mencionados no corpo mantêm o padrão (todos importados)
            mencionados = {c["nome"] for c in corpo.campos}
            for base in proposta.get("campos", []):
                if base["nome"] not in mencionados:
                    campos_saida.append({**base, "importar": True})
            confirmacao["campos"] = campos_saida
        if corpo.cad is not None:
            confirmacao["cad"] = _confirmar_cad(corpo.cad, proposta, perguntas_pendentes)
        if corpo.titulo:
            confirmacao["titulo"] = corpo.titulo
        # DXF/DWG: a pendência de georreferência é respondida de duas maneiras — o EPSG em que o desenho já
        # está, ou os pontos de controle. Confirmar o CRS basta.
        if "georreferencia" in perguntas_pendentes and "crs" in confirmacao:
            perguntas_pendentes.remove("georreferencia")

        if perguntas_pendentes:
            raise ErroAPI(422, "perguntas_pendentes", "há perguntas sem resposta na proposta",
                          {"perguntas": perguntas_pendentes})

        cur.execute(
            "UPDATE plat.importacao SET estado = 'confirmada', confirmacao = %s, atualizado_em = now() "
            "WHERE id = %s::uuid",
            (jsonb(confirmacao), r["id"]),
        )
        registrar_evento(cur, request, "importacoes/confirmar", "item", str(r["item_id"]), {"importacao_id": id})
    job = servico.criar(sessao_de(auth), "ingestao.carregar", {"importacao_id": str(r["id"])})
    with db.db(auth.contexto()) as cur:
        cur.execute("UPDATE plat.importacao SET job_carga = %s::uuid WHERE id = %s::uuid", (job["id"], r["id"]))
    return {"job_id": job["id"]}


@router.delete("/api/importacoes/{id}", status_code=204, response_class=Response, openapi_extra=PUBLICAR)
def apagar(id: str, auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, id)
        if r["estado"] not in ESTADOS_APAGAVEIS:
            raise ErroAPI(409, "estado_invalido", f"importação em estado {r['estado']!r} não pode ser apagada")
        cur.execute("DELETE FROM plat.importacao WHERE id = %s::uuid", (r["id"],))
    return Response(status_code=204)

