"""Rotas do item L2-02-e-simbolos-sprites-glifos: upload de ícone, galeria, sprite por inquilino e
glifos de fonte. `POST /api/simbolos` recebe o SVG como TEXTO dentro do corpo JSON (não multipart) —
sob cookie de sessão a escrita só aceita `application/json` (ADR 0002 seção 5.3, `checar_escrita_sob_cookie`);
como o ícone cabe folgado em 64 kB, não há razão para negociar upload binário/token de serviço só para
isto (Ponytail: reduzir ao caminho mais simples que já funciona no resto do produto — o logotipo da
organização, `app/auth/rotas_org.py`, já manda imagem em JSON)."""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Response
from pydantic import Field

from app import db, limites
from app.auth.sessao import Auth, autenticado
from app.catalogo.modelos import Modelo
from app.erros import ErroAPI
from app.simbolos import biblioteca, fontes, sprite, validador

router = APIRouter(prefix="/api/simbolos", tags=["simbolos"])


class SimboloEntrada(Modelo):
    nome: str = Field(min_length=1, max_length=limites.SIMBOLO_NOME_MAX)
    categoria: str = Field(default="personalizado", max_length=limites.SIMBOLO_CATEGORIA_MAX)
    conteudo_svg: str = Field(min_length=1, max_length=limites.SIMBOLO_SVG_BYTES_MAX)


@router.get("", openapi_extra={"x-auth": "S", "x-privilegio": "rls:visibilidade"})
def galeria(auth: Auth = autenticado(), busca: str = "", categoria: str = ""):
    """Ícones embutidos + do inquilino, para a galeria do editor (busca por nome/categoria)."""
    busca = (busca or "").strip().lower()[: limites.SIMBOLO_GALERIA_BUSCA_MAX]
    categoria = (categoria or "").strip().lower()
    itens = [
        {"nome": d.nome, "categoria": d.categoria, "fonte": "embutido", "tipo": "icone"}
        for d in biblioteca.catalogo()
    ]
    itens += [
        {"nome": nome, "categoria": "padroes", "fonte": "embutido", "tipo": "padrao_preenchimento"}
        for nome in biblioteca.padroes()
    ]
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT nome, categoria FROM plat.simbolo_upload WHERE tenant_id = %s ORDER BY nome",
            (auth.tenant_id,),
        )
        itens += [
            {"nome": f"personalizado/{r['nome']}", "categoria": r["categoria"], "fonte": "inquilino", "tipo": "icone"}
            for r in cur.fetchall()
        ]
    if busca:
        itens = [i for i in itens if busca in i["nome"].lower()]
    if categoria:
        itens = [i for i in itens if i["categoria"].lower() == categoria]
    categorias = {**biblioteca.CATEGORIAS, "padroes": {"rotulo": "Padrões", "cor": "#333333"},
                  "personalizado": {"rotulo": "Personalizado", "cor": "#333333"}}
    return {"itens": itens, "total": len(itens), "categorias": categorias}


@router.post("", status_code=201, openapi_extra={"x-auth": "S/T", "x-privilegio": "conteudo.criar"})
def enviar_icone(corpo: SimboloEntrada, auth: Auth = autenticado("conteudo.criar")):
    try:
        nome = validador.validar_nome(corpo.nome)
    except validador.SvgRecusado as e:
        raise ErroAPI(422, e.motivo, e.detalhe, {"campo": "nome"}) from e
    bruto = corpo.conteudo_svg.encode("utf-8")
    try:
        texto_saneado = validador.sanear_svg(bruto)
    except validador.SvgRecusado as e:
        raise ErroAPI(422, e.motivo, e.detalhe, {"campo": "conteudo_svg"}) from e
    categoria = (corpo.categoria or "personalizado").strip().lower() or "personalizado"
    sha = hashlib.sha256(texto_saneado.encode("utf-8")).hexdigest()
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "INSERT INTO plat.simbolo_upload (tenant_id, nome, categoria, conteudo_svg, bytes, sha256, criado_por) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (tenant_id, nome) DO UPDATE SET categoria = excluded.categoria, "
            "conteudo_svg = excluded.conteudo_svg, bytes = excluded.bytes, sha256 = excluded.sha256 "
            "RETURNING id, criado_em",
            (auth.tenant_id, nome, categoria, texto_saneado, len(bruto), sha, auth.usuario_id),
        )
        linha = cur.fetchone()
    return {
        "id": str(linha["id"]), "nome": f"personalizado/{nome}", "categoria": categoria,
        "bytes": len(bruto), "sha256": sha, "criado_em": linha["criado_em"].isoformat(),
    }


def _resposta_json(corpo: dict, versao: str) -> Response:
    import json as _json
    return Response(content=_json.dumps(corpo), media_type="application/json",
                     headers={"Cache-Control": "no-store", "X-Plat-Sprite-Versao": versao})


def _resposta_png(conteudo: bytes, versao: str) -> Response:
    return Response(content=conteudo, media_type="image/png",
                     headers={"Cache-Control": "no-store", "X-Plat-Sprite-Versao": versao})


def _sprite_do_slug(slug: str, auth: Auth) -> sprite.SpriteComposto:
    """A refutação do item pede exatamente isto: token do inquilino A não pode ler o sprite de B."""
    if slug != auth.tenant_slug:
        raise ErroAPI(403, "inquilino_divergente", "o sprite pedido não é do inquilino autenticado")
    with db.db(auth.contexto()) as cur:
        return sprite.montar_sprite_tenant(cur, auth.tenant_id)



# ordem importa: o FastAPI casa rotas na ordem de registro, e "{slug}" é guloso — "/sprite/{slug}.png"
# bateria em "demo@2x.png" (slug="demo@2x") se viesse ANTES da rota @2x explícita (achado ao rodar os
# testes: as duas rotas de 2x nunca eram alcançadas). As variantes @2x têm que vir primeiro.
@router.get("/sprite/{slug}@2x.json", openapi_extra={"x-auth": "S/T", "x-privilegio": "rls:visibilidade"})
def sprite_json_2x(slug: str, auth: Auth = autenticado()):
    s = _sprite_do_slug(slug, auth)
    return _resposta_json(s.json_2x, s.versao)


@router.get("/sprite/{slug}@2x.png", openapi_extra={"x-auth": "S/T", "x-privilegio": "rls:visibilidade"})
def sprite_png_2x(slug: str, auth: Auth = autenticado()):
    s = _sprite_do_slug(slug, auth)
    return _resposta_png(s.png_2x, s.versao)


@router.get("/sprite/{slug}.json", openapi_extra={"x-auth": "S/T", "x-privilegio": "rls:visibilidade"})
def sprite_json_1x(slug: str, auth: Auth = autenticado()):
    s = _sprite_do_slug(slug, auth)
    return _resposta_json(s.json_1x, s.versao)


@router.get("/sprite/{slug}.png", openapi_extra={"x-auth": "S/T", "x-privilegio": "rls:visibilidade"})
def sprite_png_1x(slug: str, auth: Auth = autenticado()):
    s = _sprite_do_slug(slug, auth)
    return _resposta_png(s.png_1x, s.versao)


@router.get("/fontes/{fontstack}/{faixa}.pbf", openapi_extra={"x-auth": "S/T", "x-privilegio": "rls:visibilidade"})
def glifos(fontstack: str, faixa: str, auth: Auth = autenticado()):
    try:
        inicio_s, fim_s = faixa.split("-", 1)
        inicio, fim = int(inicio_s), int(fim_s)
    except ValueError as e:
        raise ErroAPI(422, "faixa_invalida", "faixa precisa ser <inicio>-<fim>, ex. 0-255") from e
    conteudo = fontes.glifos_pbf(fontstack, inicio, fim)
    return Response(
        content=conteudo, media_type="application/x-protobuf", headers={"Cache-Control": "public, max-age=86400"}
    )
