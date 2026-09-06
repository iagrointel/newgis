"""Rotas de domínio de atributo e subtipo (item L2-10-a-dominios-subtipos).

`/api/dominios` é o objeto do inquilino (criar, listar, ver, alterar, apagar, uso, CSV, importar de serviço
Esri); `/api/camadas/{item_id}/dominios` é a ligação campo -> domínio dessa camada, com override por subtipo;
`/api/camadas/{item_id}/subtipos` designa o campo inteiro de subtipo e a lista de códigos.

Duas regras que aparecem em quase toda rota:
1. Toda escrita que muda ligação ou subtipo termina em `servico.aplicar()`, na MESMA transação — é ela que
   instala ou remove o gatilho `tg_dominio` na tabela da camada.
2. Item que não é camada vetorial do inquilino da sessão responde 404, nunca 403 nem 500: é o que faz
   "ligar domínio do inquilino A a campo de camada do inquilino B" dar 404 (a RLS esconde os dois lados)."""

from __future__ import annotations

import csv
import io

import psycopg2
from fastapi import APIRouter, Query, Request, Response

from app import db
from app.auth.comum import paginacao
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import jsonb, registrar_evento, uuid_ok
from app.dominios import esri, servico
from app.dominios.modelos import (
    CODIGOS_MAX,
    CsvEntrada,
    DominioEntrada,
    DominioPagina,
    DominioSaida,
    ImportarEntrada,
    ImportarSaida,
    LigacaoEntrada,
    LigacaoSaida,
    SubtipoEntrada,
    SubtipoSaida,
    UsoSaida,
)
from app.erros import ErroAPI

router = APIRouter(tags=["dominios"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "conteudo.publicar_camada"}
CSV_CABECALHO = ["dominio", "tipo", "tipo_campo", "descricao_dominio", "codigo", "descricao", "ordem",
                 "ativo", "min", "max"]
CSV_SEPARADOR = ";"  # planilha em pt-BR abre direto; a saída leva BOM pelo mesmo motivo


def _valores_json(entrada: DominioEntrada) -> list | dict:
    if entrada.tipo == "codificado":
        return [
            {"codigo": v.codigo, "descricao": v.descricao,
             "ordem": v.ordem if v.ordem is not None else i, "ativo": v.ativo}
            for i, v in enumerate(entrada.valores)
        ]
    return {"min": entrada.valores.min, "max": entrada.valores.max}


def _ligacoes_do_dominio(cur, dominio_id: str) -> list[dict]:
    cur.execute(
        "SELECT dc.item_id, dc.campo, i.dados AS dados FROM plat.dominio_campo dc "
        "JOIN plat.item i ON i.id = dc.item_id WHERE dc.dominio_id = %s::uuid",
        (dominio_id,),
    )
    return cur.fetchall()


# --------------------------------------------------------------------------------- CSV (antes de /{id})
@router.get("/api/dominios.csv", openapi_extra=LER)
def exportar_csv(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Uma linha por valor codificado; domínio de intervalo sai numa linha só, com min/max preenchidos e
    código vazio. É o mesmo formato que `POST /api/dominios/csv` lê de volta."""
    buffer = io.StringIO()
    w = csv.writer(buffer, delimiter=CSV_SEPARADOR, lineterminator="\n")
    w.writerow(CSV_CABECALHO)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT * FROM plat.dominio ORDER BY nome")
        for d in cur.fetchall():
            if d["tipo"] == "intervalo":
                w.writerow([d["nome"], d["tipo"], d["tipo_campo"], d["descricao"] or "", "", "", "", "",
                            d["valores"]["min"], d["valores"]["max"]])
                continue
            for v in sorted(d["valores"], key=lambda v: (v.get("ordem") or 0)):
                w.writerow([d["nome"], d["tipo"], d["tipo_campo"], d["descricao"] or "", v["codigo"],
                            v["descricao"], v.get("ordem", 0), "sim" if v.get("ativo", True) else "nao", "", ""])
    corpo = "﻿" + buffer.getvalue()
    return Response(
        corpo, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="dominios.csv"', "Cache-Control": "no-store"},
    )


@router.post("/api/dominios/csv", openapi_extra=EDITAR)
def importar_csv(corpo: CsvEntrada, request: Request, auth: Auth = autenticado("conteudo.publicar_camada")):
    """Edição em massa: o campo `csv` traz o arquivo inteiro. Cada domínio do arquivo é criado ou substituído
    por completo — o arquivo é a lista final de valores, não um delta. Domínio ausente do arquivo não é
    tocado (remover é `DELETE /api/dominios/{id}`, que confere uso).

    Por que o CSV vem dentro de um JSON e não como `text/csv` no corpo: escrita sob cookie exige
    `Content-Type: application/json` (ADR 0002 seção 5.3, defesa de CSRF) — um corpo `text/csv` é recusado
    com 415 antes de chegar aqui, e a tela não tem como mudar isso."""
    bruto = corpo.csv.lstrip("\ufeff")
    if not bruto.strip():
        raise ErroAPI(422, "csv_vazio", "o CSV veio vazio")
    leitor = csv.DictReader(io.StringIO(bruto), delimiter=CSV_SEPARADOR)
    if not leitor.fieldnames or "dominio" not in leitor.fieldnames:
        raise ErroAPI(422, "csv_sem_cabecalho", f"o CSV precisa do cabeçalho {CSV_SEPARADOR.join(CSV_CABECALHO)}")
    juntos: dict[str, dict] = {}
    for n, linha in enumerate(leitor, start=2):
        nome = (linha.get("dominio") or "").strip()
        if not nome:
            continue
        d = juntos.setdefault(nome, {
            "nome": nome, "tipo": (linha.get("tipo") or "codificado").strip(),
            "tipo_campo": (linha.get("tipo_campo") or "text").strip(),
            "descricao": (linha.get("descricao_dominio") or "").strip() or None, "valores": [],
        })
        if d["tipo"] == "intervalo":
            try:
                d["valores"] = {"min": float(linha.get("min") or 0), "max": float(linha.get("max") or 0)}
            except ValueError as e:
                raise ErroAPI(422, "csv_linha_invalida", f"linha {n}: min/max não numéricos",
                              {"linha": n}) from e
            continue
        codigo = (linha.get("codigo") or "").strip()
        if not codigo:
            raise ErroAPI(422, "csv_linha_invalida", f"linha {n}: código vazio em domínio codificado",
                          {"linha": n})
        ordem = (linha.get("ordem") or "").strip()
        d["valores"].append({
            "codigo": codigo, "descricao": (linha.get("descricao") or codigo).strip(),
            "ordem": int(ordem) if ordem.isdigit() else len(d["valores"]),
            "ativo": (linha.get("ativo") or "sim").strip().lower() not in ("nao", "não", "false", "0"),
        })
    if not juntos:
        raise ErroAPI(422, "csv_sem_dominios", "o CSV não trouxe nenhum domínio")
    saida = {"criados": [], "atualizados": []}
    with db.db(auth.contexto()) as cur:
        for nome, d in juntos.items():
            entrada = DominioEntrada.model_validate(d)  # mesma validação da rota de criar
            valores = _valores_json(entrada)
            try:
                cur.execute("SELECT id FROM plat.dominio WHERE lower(nome) = lower(%s)", (nome,))
                existente = cur.fetchone()
                if existente:
                    cur.execute(
                        "UPDATE plat.dominio SET tipo = %s, tipo_campo = %s, descricao = %s, valores = %s, "
                        "atualizado_por = %s WHERE id = %s RETURNING id",
                        (entrada.tipo, entrada.tipo_campo, entrada.descricao, jsonb(valores),
                         auth.usuario_id, existente["id"]),
                    )
                    saida["atualizados"].append({"id": str(existente["id"]), "nome": nome})
                else:
                    cur.execute(
                        "INSERT INTO plat.dominio (tenant_id, nome, tipo, tipo_campo, descricao, valores, "
                        "criado_por, atualizado_por) VALUES (plat.tenant_atual(), %s, %s, %s, %s, %s, %s, %s) "
                        "RETURNING id",
                        (nome, entrada.tipo, entrada.tipo_campo, entrada.descricao, jsonb(valores),
                         auth.usuario_id, auth.usuario_id),
                    )
                    saida["criados"].append({"id": str(cur.fetchone()["id"]), "nome": nome})
            except psycopg2.Error as e:
                raise servico.erro_do_banco(e) from e
        registrar_evento(cur, request, "dominios/editar", "dominio", None,
                         {"csv": True, "criados": len(saida["criados"]), "atualizados": len(saida["atualizados"])})
    return saida


@router.post("/api/dominios/importar", response_model=ImportarSaida, openapi_extra=EDITAR)
def importar_de_servico(corpo: ImportarEntrada, request: Request,
                        auth: Auth = autenticado("conteudo.publicar_camada")):
    """Importa os domínios de um `fields`/`types` de FeatureServer ou FGDB (o mesmo objeto que a Esri
    publica em `/FeatureServer/0?f=json`). Domínio com nome já existente no inquilino é REAPROVEITADO, nunca
    duplicado nem sobrescrito — o que ele já vale continua valendo. Com `item_id`, as ligações campo ->
    domínio (e o subtipo, se o objeto trouxer `types`) são criadas na camada."""
    criados, reaproveitados, ligados, ignorados = [], [], [], []
    subtipo_saida = None
    prefixo = (corpo.prefixo + " ") if corpo.prefixo else ""
    with db.db(auth.contexto()) as cur:
        item = servico.camada_ou_404(cur, corpo.item_id) if corpo.item_id else None
        campos_item = servico.campos_declarados(item) if item else {}

        def garantir(objeto: dict, tipo_campo_esri: str | None) -> str | None:
            d = esri.dominio_de_esri(objeto)
            if d is None:
                ignorados.append({"motivo": "domínio não representável nesta versão",
                                  "objeto": (objeto or {}).get("name") or (objeto or {}).get("type")})
                return None
            nome = prefixo + d["nome"]
            tipo_campo = esri.TIPO_PG.get(tipo_campo_esri or "", "text")
            if d["tipo"] == "intervalo" and tipo_campo in ("text", "date"):
                tipo_campo = "double precision"
            cur.execute("SELECT id, tipo FROM plat.dominio WHERE lower(nome) = lower(%s)", (nome,))
            ja = cur.fetchone()
            if ja:
                reaproveitados.append({"id": str(ja["id"]), "nome": nome})
                return str(ja["id"])
            try:
                cur.execute(
                    "INSERT INTO plat.dominio (tenant_id, nome, tipo, tipo_campo, descricao, valores, "
                    "criado_por, atualizado_por) VALUES (plat.tenant_atual(), %s, %s, %s, %s, %s, %s, %s) "
                    "RETURNING id",
                    (nome, d["tipo"], tipo_campo, d.get("descricao"), jsonb(d["valores"]),
                     auth.usuario_id, auth.usuario_id),
                )
            except psycopg2.Error as e:
                raise servico.erro_do_banco(e) from e
            novo = str(cur.fetchone()["id"])
            criados.append({"id": novo, "nome": nome})
            return novo

        def ligar(campo: str, dominio_id: str, subtipo_codigo: int | None) -> None:
            if item is None:
                return
            if campo not in campos_item:
                ignorados.append({"motivo": "a camada não tem o campo", "campo": campo})
                return
            cur.execute(
                "INSERT INTO plat.dominio_campo (tenant_id, item_id, campo, subtipo_codigo, dominio_id) "
                "VALUES (plat.tenant_atual(), %s::uuid, %s, %s, %s::uuid) "
                "ON CONFLICT (item_id, campo, coalesce(subtipo_codigo, -2147483648)) "
                "DO UPDATE SET dominio_id = EXCLUDED.dominio_id RETURNING id",
                (str(item["id"]), campo, subtipo_codigo, dominio_id),
            )
            ligados.append({"campo": campo, "subtipo_codigo": subtipo_codigo, "dominio_id": dominio_id})

        for f in corpo.fields:
            if not isinstance(f, dict) or not f.get("domain"):
                continue
            did = garantir(f["domain"], f.get("type"))
            if did:
                ligar(str(f.get("name") or "").lower(), did, None)

        if corpo.types and item is not None:
            campo_sub = str(corpo.types[0].get("campo_subtipo") or "").lower() or None
            valores_sub = []
            for t in corpo.types:
                if not isinstance(t, dict) or t.get("id") is None:
                    continue
                padroes = {}
                for tpl in t.get("templates") or []:
                    padroes.update(((tpl or {}).get("prototype") or {}).get("attributes") or {})
                valores_sub.append({"codigo": int(t["id"]), "nome": str(t.get("name") or t["id"]),
                                    "padroes": padroes})
                for campo, objeto in (t.get("domains") or {}).items():
                    if not isinstance(objeto, dict) or objeto.get("type") == "inherited":
                        continue
                    did = garantir(objeto, None)
                    if did:
                        ligar(str(campo).lower(), did, int(t["id"]))
            if campo_sub and valores_sub:
                cur.execute(
                    "INSERT INTO plat.camada_subtipo (item_id, tenant_id, campo, valores) "
                    "VALUES (%s::uuid, plat.tenant_atual(), %s, %s) "
                    "ON CONFLICT (item_id) DO UPDATE SET campo = EXCLUDED.campo, valores = EXCLUDED.valores, "
                    "atualizado_em = now()",
                    (str(item["id"]), campo_sub, jsonb(valores_sub)),
                )
                subtipo_saida = {"campo": campo_sub, "valores": valores_sub}
            elif valores_sub:
                ignorados.append({"motivo": "types sem campo_subtipo: os subtipos não foram gravados",
                                  "quantos": len(valores_sub)})
        if item is not None:
            servico.aplicar(cur, str(item["id"]))
        registrar_evento(cur, request, "dominios/importar", "item", corpo.item_id,
                         {"criados": len(criados), "reaproveitados": len(reaproveitados),
                          "ligados": len(ligados), "ignorados": len(ignorados)})
    return {"criados": criados, "reaproveitados": reaproveitados, "ligados": ligados,
            "subtipos": subtipo_saida, "ignorados": ignorados}


# --------------------------------------------------------------------------------- domínio
@router.get("/api/dominios", response_model=DominioPagina, openapi_extra=LER)
def listar(
    q: str | None = Query(default=None, max_length=200),
    tipo: str | None = Query(default=None, pattern="^(codificado|intervalo)$"),
    limite: int | None = None,
    deslocamento: int | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    lim, desl = paginacao(limite, deslocamento)
    onde, params = ["true"], []
    if q:
        onde.append("(nome ILIKE %s OR coalesce(descricao, '') ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    if tipo:
        onde.append("tipo = %s")
        params.append(tipo)
    filtro = " AND ".join(onde)
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.dominio WHERE {filtro}", params)
        total = cur.fetchone()["n"]
        cur.execute(f"SELECT * FROM plat.dominio WHERE {filtro} ORDER BY nome LIMIT %s OFFSET %s",
                    [*params, lim, desl])
        itens = [servico.dominio_json(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens}


@router.post("/api/dominios", response_model=DominioSaida, status_code=201, openapi_extra=EDITAR)
def criar(corpo: DominioEntrada, request: Request, auth: Auth = autenticado("conteudo.publicar_camada")):
    valores = _valores_json(corpo)
    with db.db(auth.contexto()) as cur:
        try:
            cur.execute(
                "INSERT INTO plat.dominio (tenant_id, nome, tipo, tipo_campo, descricao, valores, criado_por, "
                "atualizado_por) VALUES (plat.tenant_atual(), %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (corpo.nome, corpo.tipo, corpo.tipo_campo, corpo.descricao, jsonb(valores),
                 auth.usuario_id, auth.usuario_id),
            )
        except psycopg2.errors.UniqueViolation as e:
            raise ErroAPI(409, "dominio_duplicado", f"já existe um domínio chamado {corpo.nome!r}") from e
        except psycopg2.Error as e:
            raise servico.erro_do_banco(e) from e
        r = cur.fetchone()
        registrar_evento(cur, request, "dominios/criar", "dominio", r["id"],
                         {"nome": corpo.nome, "tipo": corpo.tipo,
                          "valores": len(valores) if isinstance(valores, list) else 2})
    return servico.dominio_json(r)


@router.get("/api/dominios/{dominio_id}", response_model=DominioSaida, openapi_extra=LER)
def ver(dominio_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        return servico.dominio_json(servico.dominio_ou_404(cur, dominio_id))


@router.get("/api/dominios/{dominio_id}/uso", response_model=UsoSaida, openapi_extra=LER)
def uso(dominio_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """As camadas que usam o domínio e quantas feições usam cada código — é o que a tela de edição mostra
    ANTES de deixar remover um valor."""
    with db.db(auth.contexto()) as cur:
        d = servico.dominio_ou_404(cur, dominio_id)
        return servico.uso_do_dominio(cur, str(d["id"]))


@router.put("/api/dominios/{dominio_id}", response_model=DominioSaida, openapi_extra=EDITAR)
def alterar(dominio_id: str, corpo: DominioEntrada, request: Request,
            auth: Auth = autenticado("conteudo.publicar_camada")):
    """Substitui o domínio inteiro. Duas recusas próprias desta rota, antes de qualquer escrita: trocar o
    tipo de campo para um incompatível com algum campo já ligado (409) e remover valor em uso (409, com a
    contagem — quem levanta é o gatilho do banco, para valer também para quem escreve por fora da API)."""
    valores = _valores_json(corpo)
    with db.db(auth.contexto()) as cur:
        atual = servico.dominio_ou_404(cur, dominio_id)
        if corpo.tipo_campo != atual["tipo_campo"]:
            for lig in _ligacoes_do_dominio(cur, str(atual["id"])):
                campos = {c["nome"]: c.get("tipo", "") for c in ((lig["dados"] or {}).get("campos") or [])}
                tipo_pg = campos.get(lig["campo"], "")
                if tipo_pg and not servico.tipos_compativeis(tipo_pg, corpo.tipo_campo):
                    raise ErroAPI(
                        409, "dominio_tipo_em_uso",
                        f"o domínio está ligado ao campo {lig['campo']!r}, do tipo {tipo_pg}; "
                        f"não dá para mudá-lo para {corpo.tipo_campo}",
                        {"item_id": str(lig["item_id"]), "campo": lig["campo"], "tipo_do_campo": tipo_pg},
                    )
        try:
            cur.execute(
                "UPDATE plat.dominio SET nome = %s, tipo = %s, tipo_campo = %s, descricao = %s, valores = %s, "
                "atualizado_por = %s WHERE id = %s RETURNING *",
                (corpo.nome, corpo.tipo, corpo.tipo_campo, corpo.descricao, jsonb(valores),
                 auth.usuario_id, atual["id"]),
            )
        except psycopg2.errors.UniqueViolation as e:
            raise ErroAPI(409, "dominio_duplicado", f"já existe um domínio chamado {corpo.nome!r}") from e
        except psycopg2.Error as e:
            raise servico.erro_do_banco(e) from e
        r = cur.fetchone()
        registrar_evento(cur, request, "dominios/editar", "dominio", r["id"], {"nome": corpo.nome})
    return servico.dominio_json(r)


@router.delete("/api/dominios/{dominio_id}", status_code=204, openapi_extra=EDITAR)
def apagar(dominio_id: str, request: Request, auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        d = servico.dominio_ou_404(cur, dominio_id)
        cur.execute("SELECT count(*) AS n FROM plat.dominio_campo WHERE dominio_id = %s", (d["id"],))
        ligadas = cur.fetchone()["n"]
        if ligadas:
            raise ErroAPI(
                409, "dominio_ligado",
                f"o domínio está ligado a {ligadas} campo(s) de camada; desligue antes de apagar",
                {"ligacoes": ligadas},
            )
        cur.execute("DELETE FROM plat.dominio WHERE id = %s", (d["id"],))
        registrar_evento(cur, request, "dominios/apagar", "dominio", d["id"], {"nome": d["nome"]})
    return Response(status_code=204)


# --------------------------------------------------------------------------------- ligação por camada
@router.get("/api/camadas/{item_id}/dominios", openapi_extra=LER)
def listar_ligacoes(item_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        item = servico.camada_ou_404(cur, item_id)
        cur.execute(
            "SELECT dc.id, dc.item_id, dc.campo, dc.subtipo_codigo, dc.dominio_id, d.nome AS dominio_nome, "
            "d.tipo, d.tipo_campo, d.valores "
            "FROM plat.dominio_campo dc JOIN plat.dominio d ON d.id = dc.dominio_id "
            "WHERE dc.item_id = %s::uuid ORDER BY dc.campo, dc.subtipo_codigo NULLS FIRST",
            (str(item["id"]),),
        )
        ligacoes = [
            {"id": str(r["id"]), "item_id": str(r["item_id"]), "campo": r["campo"],
             "subtipo_codigo": r["subtipo_codigo"], "dominio_id": str(r["dominio_id"]),
             "dominio_nome": r["dominio_nome"], "tipo": r["tipo"], "tipo_campo": r["tipo_campo"],
             "valores": r["valores"]}
            for r in cur.fetchall()
        ]
        cur.execute("SELECT campo, valores FROM plat.camada_subtipo WHERE item_id = %s::uuid", (str(item["id"]),))
        s = cur.fetchone()
    return {
        "item_id": str(item["id"]),
        "campos": [{"nome": n, "tipo": t} for n, t in servico.campos_declarados(item).items()],
        "ligacoes": ligacoes,
        "subtipo": ({"campo": s["campo"], "valores": s["valores"]} if s else None),
    }


@router.post("/api/camadas/{item_id}/dominios", response_model=LigacaoSaida, status_code=201,
             openapi_extra=EDITAR)
def ligar(item_id: str, corpo: LigacaoEntrada, request: Request,
          auth: Auth = autenticado("conteudo.publicar_camada")):
    """Liga um campo da camada a um domínio. Sem subtipo é a ligação padrão; com `subtipo_codigo` é o
    override daquele subtipo, e o código precisa estar na lista de subtipos da camada."""
    with db.db(auth.contexto()) as cur:
        item = servico.camada_ou_404(cur, item_id)
        tipo_pg = servico.exigir_campo(item, corpo.campo)
        d = servico.dominio_ou_404(cur, corpo.dominio_id)
        if tipo_pg and not servico.tipos_compativeis(tipo_pg, d["tipo_campo"]):
            raise ErroAPI(
                422, "tipo_incompativel",
                f"o campo {corpo.campo!r} é {tipo_pg} e o domínio {d['nome']!r} é para {d['tipo_campo']}",
                {"tipo_do_campo": tipo_pg, "tipo_do_dominio": d["tipo_campo"]},
            )
        if corpo.subtipo_codigo is not None:
            cur.execute("SELECT campo, valores FROM plat.camada_subtipo WHERE item_id = %s::uuid",
                        (str(item["id"]),))
            s = cur.fetchone()
            codigos = {int(v["codigo"]) for v in (s["valores"] if s else [])}
            if corpo.subtipo_codigo not in codigos:
                raise ErroAPI(
                    422, "subtipo_inexistente",
                    f"a camada não tem o subtipo {corpo.subtipo_codigo}",
                    {"subtipos": sorted(codigos)},
                )
        try:
            cur.execute(
                "INSERT INTO plat.dominio_campo (tenant_id, item_id, campo, subtipo_codigo, dominio_id) "
                "VALUES (plat.tenant_atual(), %s::uuid, %s, %s, %s::uuid) "
                "ON CONFLICT (item_id, campo, coalesce(subtipo_codigo, -2147483648)) "
                "DO UPDATE SET dominio_id = EXCLUDED.dominio_id RETURNING id",
                (str(item["id"]), corpo.campo, corpo.subtipo_codigo, str(d["id"])),
            )
        except psycopg2.Error as e:
            raise servico.erro_do_banco(e) from e
        ligacao_id = str(cur.fetchone()["id"])
        servico.aplicar(cur, str(item["id"]))
        registrar_evento(cur, request, "dominios/ligar", "item", item["id"],
                         {"campo": corpo.campo, "dominio": d["nome"], "subtipo": corpo.subtipo_codigo})
    return {"id": ligacao_id, "item_id": str(item["id"]), "campo": corpo.campo,
            "subtipo_codigo": corpo.subtipo_codigo, "dominio_id": str(d["id"]), "dominio_nome": d["nome"]}


@router.delete("/api/camadas/{item_id}/dominios/{ligacao_id}", status_code=204, openapi_extra=EDITAR)
def desligar(item_id: str, ligacao_id: str, request: Request,
             auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        item = servico.camada_ou_404(cur, item_id)
        lid = uuid_ok(ligacao_id, "ligacao_inexistente", "ligação inexistente")
        cur.execute("DELETE FROM plat.dominio_campo WHERE id = %s::uuid AND item_id = %s::uuid RETURNING campo",
                    (lid, str(item["id"])))
        r = cur.fetchone()
        if r is None:
            raise ErroAPI(404, "ligacao_inexistente", "ligação inexistente")
        servico.aplicar(cur, str(item["id"]))
        registrar_evento(cur, request, "dominios/desligar", "item", item["id"], {"campo": r["campo"]})
    return Response(status_code=204)


# --------------------------------------------------------------------------------- subtipos
@router.get("/api/camadas/{item_id}/subtipos", openapi_extra=LER)
def ver_subtipos(item_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        item = servico.camada_ou_404(cur, item_id)
        cur.execute("SELECT campo, valores FROM plat.camada_subtipo WHERE item_id = %s::uuid", (str(item["id"]),))
        s = cur.fetchone()
    if s is None:
        return {"item_id": str(item["id"]), "campo": None, "valores": []}
    return {"item_id": str(item["id"]), "campo": s["campo"], "valores": s["valores"]}


@router.put("/api/camadas/{item_id}/subtipos", response_model=SubtipoSaida, openapi_extra=EDITAR)
def definir_subtipos(item_id: str, corpo: SubtipoEntrada, request: Request,
                     auth: Auth = autenticado("conteudo.publicar_camada")):
    """Designa o campo de subtipo e a lista de códigos. O campo tem de existir na camada e ser inteiro —
    subtipo por texto não existe (é a regra da Esri e a que o gatilho consegue conferir com um cast)."""
    with db.db(auth.contexto()) as cur:
        item = servico.camada_ou_404(cur, item_id)
        tipo_pg = servico.exigir_campo(item, corpo.campo)
        if tipo_pg not in ("smallint", "integer", "bigint"):
            raise ErroAPI(422, "subtipo_campo_nao_inteiro",
                          f"o campo de subtipo precisa ser inteiro; {corpo.campo!r} é {tipo_pg}",
                          {"tipo_do_campo": tipo_pg})
        codigos = {v.codigo for v in corpo.valores}
        cur.execute(
            "SELECT DISTINCT subtipo_codigo FROM plat.dominio_campo "
            "WHERE item_id = %s::uuid AND subtipo_codigo IS NOT NULL",
            (str(item["id"]),),
        )
        orfaos = sorted({r["subtipo_codigo"] for r in cur.fetchall()} - codigos)
        if orfaos:
            raise ErroAPI(
                409, "subtipo_com_ligacao",
                f"há ligações de domínio nos subtipos {orfaos}; desligue-as antes de removê-los",
                {"subtipos": orfaos},
            )
        valores = [{"codigo": v.codigo, "nome": v.nome, "padroes": v.padroes} for v in corpo.valores]
        cur.execute(
            "INSERT INTO plat.camada_subtipo (item_id, tenant_id, campo, valores) "
            "VALUES (%s::uuid, plat.tenant_atual(), %s, %s) "
            "ON CONFLICT (item_id) DO UPDATE SET campo = EXCLUDED.campo, valores = EXCLUDED.valores, "
            "atualizado_em = now() RETURNING campo, valores",
            (str(item["id"]), corpo.campo, jsonb(valores)),
        )
        r = cur.fetchone()
        servico.aplicar(cur, str(item["id"]))
        registrar_evento(cur, request, "subtipos/definir", "item", item["id"],
                         {"campo": corpo.campo, "quantos": len(valores)})
    return {"item_id": str(item["id"]), "campo": r["campo"], "valores": r["valores"]}


@router.delete("/api/camadas/{item_id}/subtipos", status_code=204, openapi_extra=EDITAR)
def apagar_subtipos(item_id: str, request: Request, auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        item = servico.camada_ou_404(cur, item_id)
        cur.execute("SELECT count(*) AS n FROM plat.dominio_campo WHERE item_id = %s::uuid "
                    "AND subtipo_codigo IS NOT NULL", (str(item["id"]),))
        if cur.fetchone()["n"]:
            raise ErroAPI(409, "subtipo_com_ligacao",
                          "há ligações de domínio por subtipo nesta camada; desligue-as antes")
        cur.execute("DELETE FROM plat.camada_subtipo WHERE item_id = %s::uuid", (str(item["id"]),))
        servico.aplicar(cur, str(item["id"]))
        registrar_evento(cur, request, "subtipos/definir", "item", item["id"], {"apagado": True})
    return Response(status_code=204)


@router.get("/api/dominios-limites", openapi_extra=LER)
def limites_dos_dominios(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """O teto de códigos que a tela precisa saber sem descobrir por tentativa e erro (é o mesmo número do
    gatilho `plat.dominio_sincronizar`)."""
    return {"codigos_por_dominio": CODIGOS_MAX}
