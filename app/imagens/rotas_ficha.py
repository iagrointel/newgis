"""Rotas da ficha de metadado e licença da imagem (item L1-27).

- `GET  /api/imagens/licencas` — a tabela de licenças da casa, lida de `app.imagens.ficha.LICENCAS`. A tela
  NUNCA repete a lista; é isto que garante a cláusula "lista de licenças lida do código (uma só tabela)".
- `GET  /api/imagens/{item_id}/ficha` — a ficha gravada, os avisos (D17) e o que falta preencher.
- `PUT  /api/imagens/{item_id}/ficha` — grava a ficha em `plat.item.dados['ficha']` (fonte da verdade) e
  PROJETA a mesma ficha nas propriedades do item STAC quando ele já existe, de modo que licença, data de
  aquisição, plataforma e instrumento sejam sempre o mesmo dado nos dois lugares.

Afrouxar licença exige administrador: trocar uma licença de redistribuição RESTRITA (contrato do fornecedor,
ou a ausência de licença escrita) por uma LIVRE muda o que a plataforma passa a permitir com o arquivo do
cliente — link público e exportação em massa. Quem não tem `org.configurar` recebe 403 e a troca fica
registrada no log de eventos, aprovada ou recusada (é exatamente a refutação exigida no item).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import exigir_edicao, item_ou_404, jsonb, registrar_evento
from app.catalogo.modelos import Modelo
from app.erros import ErroAPI
from app.imagens import ficha as fi
from app.imagens import pgstac as ps

router = APIRouter(tags=["imagens"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
ESCREVER = {"x-auth": "S", "x-privilegio": "proprio"}
SEM_CACHE = {"Cache-Control": "no-store, must-revalidate"}
PRIVILEGIO_AFROUXAR = "org.configurar"


class FichaEntrada(Modelo):
    plataforma: str = Field(max_length=120)
    instrumentos: list[str] = Field(max_length=20)
    gsd: float
    data_aquisicao: str = Field(max_length=40)
    fornecedor: str = Field(max_length=200)
    licenca: str = Field(max_length=60)
    fonte: str = Field(max_length=20)
    constelacao: str | None = Field(default=None, max_length=120)
    data_aquisicao_fim: str | None = Field(default=None, max_length=40)
    nuvem_pct: float | None = None
    angulo_off_nadir: float | None = None
    angulo_incidencia: float | None = None
    angulo_azimute: float | None = None
    sol_azimute: float | None = None
    sol_elevacao: float | None = None
    orbita_estado: str | None = Field(default=None, max_length=20)
    orbita_relativa: int | None = None
    orbita_absoluta: int | None = None
    atribuicao: str | None = Field(default=None, max_length=300)
    observacao: str | None = Field(default=None, max_length=1000)


def item_raster_ou_404(cur, item_id: str, para_editar: bool = False) -> dict:
    r = exigir_edicao(cur, item_id) if para_editar else item_ou_404(cur, item_id)
    if r["tipo"] != "raster":
        raise ErroAPI(404, "item_inexistente", "item de imagem inexistente")
    return r


def _corpo_da_ficha(r: dict) -> dict:
    f = fi.do_item(r["dados"])
    lic = fi.licenca(f.licenca if f else None)
    return {
        "item_id": str(r["id"]),
        "titulo": r["titulo"],
        "ficha": fi.para_json(f) if f else None,
        "propriedades_stac": fi.para_stac(f) if f else None,
        "licenca": {
            "codigo": lic.codigo, "rotulo": lic.rotulo, "stac": lic.stac, "url": lic.url,
            "redistribuicao": lic.redistribuicao, "exige_atribuicao": lic.exige_atribuicao,
            "vendavel": lic.vendavel,
        },
        "atribuicao": (f.atribuicao if f else None),
        "permite_link_publico": fi.permite_link_publico(f.licenca if f else None),
        "permite_exportacao_em_massa": fi.permite_exportacao_em_massa(f.licenca if f else None),
        "avisos": fi.avisos(f),
        "obrigatorios": list(fi.OBRIGATORIOS),
        "metadado_iso_url": f"/api/itens/{r['id']}/metadado.xml?perfil=imagem",
    }


@router.get("/api/imagens/licencas", openapi_extra=LER)
def licencas_listar(auth: Auth = autenticado(escopo_token="imagens:ler")):
    """A tabela de licenças da casa. Não depende do inquilino nem de nenhum item: é a lista fechada do
    código, e é daqui que a tela monta o seletor."""
    _ = auth
    return JSONResponse({"licencas": fi.catalogo_licencas(), "padrao": fi.LICENCA_PADRAO}, headers=SEM_CACHE)


@router.get("/api/imagens/{item_id}/ficha", openapi_extra=LER)
def ficha_ver(item_id: str, auth: Auth = autenticado(escopo_token="imagens:ler")):
    with db.db(auth.contexto()) as cur:
        r = item_raster_ou_404(cur, item_id)
    return JSONResponse(_corpo_da_ficha(r), headers=SEM_CACHE)


@router.put("/api/imagens/{item_id}/ficha", openapi_extra=ESCREVER)
def ficha_gravar(item_id: str, corpo: FichaEntrada, request: Request, auth: Auth = autenticado(so_sessao=True)):
    nova = fi.validar(corpo.model_dump())
    with db.db(auth.contexto()) as cur:
        r = item_raster_ou_404(cur, item_id, para_editar=True)
        antiga = fi.do_item(r["dados"])
        de = fi.licenca(antiga.licenca if antiga else None)
        para = fi.POR_CODIGO[nova.licenca]
        afrouxou = de.redistribuicao == "restrita" and para.redistribuicao == "livre"
        recusar = afrouxou and not auth.tem(PRIVILEGIO_AFROUXAR)
        if recusar:
            # a recusa é gravada numa transação PRÓPRIA, aberta depois desta: levantar aqui dentro desfaria a
            # inserção junto com o resto, e a auditoria perderia exatamente a tentativa que interessa
            item_recusado = str(r["id"])
        else:
            dados = dict(r["dados"] or {})
            dados["ficha"] = fi.para_json(nova)
            cur.execute(
                "UPDATE plat.item SET dados = %s, modificado_por = %s, modificado_em = now() WHERE id = %s::uuid",
                (jsonb(dados), auth.usuario_id, str(r["id"])),
            )
            projetado = _projetar_no_stac(cur, auth.tenant_id, dados, nova)
            if afrouxou:
                registrar_evento(
                    cur, request, "imagens/ficha_licenca_afrouxada", "item", r["id"],
                    {"de": de.codigo, "para": para.codigo, "privilegio": PRIVILEGIO_AFROUXAR},
                )
            registrar_evento(
                cur, request, "imagens/ficha_gravar", "item", r["id"],
                {"licenca": nova.licenca, "licenca_anterior": de.codigo if antiga else None,
                 "projetado_no_stac": projetado},
            )
            r = item_raster_ou_404(cur, item_id)
    if recusar:
        with db.db(auth.contexto()) as cur:
            registrar_evento(
                cur, request, "imagens/ficha_licenca_recusada", "item", item_recusado,
                {"de": de.codigo, "para": para.codigo, "exigido": PRIVILEGIO_AFROUXAR},
            )
        raise ErroAPI(
            403, "sem_permissao",
            "trocar uma licença restrita por uma livre exige o privilégio "
            f"{PRIVILEGIO_AFROUXAR}: a troca libera link público e exportação em massa do arquivo",
            {"exigido": PRIVILEGIO_AFROUXAR, "de": de.codigo, "para": para.codigo},
        )
    return JSONResponse(_corpo_da_ficha(r), headers=SEM_CACHE)


def _projetar_no_stac(cur, tenant_id: int, dados: dict, f: fi.Ficha) -> bool:
    """Escreve a ficha nas propriedades do item STAC. Devolve False quando o item ainda não foi ingerido
    (ficha preenchida antes da ingestão é caso normal, não erro)."""
    colecao, stac_id = dados.get("colecao") or "", dados.get("stac_id") or ""
    if not colecao or not stac_id or not ps.colecao_pertence(colecao, tenant_id):
        return False
    item = ps.item_obter(cur, tenant_id, colecao, stac_id)
    if item is None:
        return False
    props = dict(item.get("properties") or {})
    props.update(fi.para_stac(f))
    extensoes = list(dict.fromkeys([*(item.get("stac_extensions") or []), *fi.EXTENSOES_STAC]))
    links = [ligacao for ligacao in (item.get("links") or []) if ligacao.get("rel") != "license"]
    links.extend(fi.links_stac(f))
    novo = {**item, "properties": props, "stac_extensions": extensoes, "links": links}
    cur.execute("SELECT pgstac.update_item(%s::jsonb)", (jsonb(novo),))
    return True
