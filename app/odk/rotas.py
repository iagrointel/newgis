"""Rotas da ponte com o ODK Central (item L2-07-e-odk-central-ponte).

A ponte é opcional e sempre por CONEXÃO registrada (L6-02-a): a URL do Central passa pela mesma defesa de SSRF
das outras conexões e a credencial (token do Central) fica cifrada em `plat.conexao`, nunca aqui. Quatro rotas:

  POST /api/odk/pontes                       publica o XLSForm num projeto do Central e cria a ponte
  GET  /api/odk/pontes                       lista as pontes do inquilino
  GET  /api/odk/pontes/{id}                  a ponte + o que o Central diz do formulário AGORA (prova viva)
  POST /api/odk/pontes/{id}/sincronizar      puxa os envios por OData e grava as feições (idempotente)
  GET  /api/odk/pontes/{id}/entidades/{ds}   Entities do dataset como lista de escolhas do formulário

Falha de credencial contra o Central marca a saúde da conexão pela MESMA função do L6-02-l
(`plat.conexao_saude_registrar`), então o erro aparece na tela de conexões sem tela nova."""

from __future__ import annotations

import base64
import binascii

import psycopg2
from fastapi import APIRouter, Depends, Request
from pydantic import Field

from app import db, limites
from app.auth import escopos as esc
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo import comum
from app.coleta import xlsform
from app.conexao import credencial as credencial_mod
from app.edicao.modelos import UUID_PADRAO, Modelo, Saida
from app.erros import ErroAPI
from app.odk import ponte as ponte_mod
from app.odk.central import Central, ErroCentral
from app.seguranca_rotacao import decifrar_com_rotacao
from app.settings import settings

router = APIRouter(prefix="/api/odk", tags=["odk"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
CRIAR = {"x-auth": "S/T", "x-privilegio": "conteudo.registrar_fonte"}
SINCRONIZAR = {"x-auth": "S/T", "x-privilegio": "feicoes.editar|feicoes.editar_total"}
CAMPOS = ("p.id, p.conexao_id, p.formulario_id, p.projeto, p.xml_form_id, p.versao, p.hash_central, "
          "p.publicado_em, p.sincronizado_em, p.dono_id, p.criado_em, c.nome AS conexao_nome, c.url AS conexao_url")


class PonteEntrada(Modelo):
    conexao: str = Field(pattern=UUID_PADRAO)
    formulario: str = Field(pattern=UUID_PADRAO)
    projeto: int = Field(ge=1)
    conteudo: str = Field(min_length=1)  # base64 do MESMO XLSForm que gerou o formulário (JSON sob cookie)


class PonteSaida(Saida):
    id: str
    conexao: str
    conexao_nome: str
    formulario: str
    projeto: int
    xml_form_id: str
    versao: str | None = None
    hash_central: str | None = None
    publicado_em: str | None = None
    sincronizado_em: str | None = None


class PontePagina(Saida):
    total: int
    itens: list[PonteSaida]


class _FalhaDoCentral(Exception):
    """Carrega a falha do Central para FORA do `with db.db(...)`: só depois que a transação do pedido fechou é
    que a saúde da conexão pode ser gravada (senão o `rollback` da exceção leva a gravação junto)."""

    def __init__(self, conexao_id: str, erro: ErroCentral):
        self.conexao_id = conexao_id
        self.erro = erro
        super().__init__(erro.motivo)


def _auth_editor(auth: Auth = autenticado(escopo_token="camada:editar")) -> Auth:  # noqa: B008
    if not (auth.tem("feicoes.editar") or auth.tem("feicoes.editar_total")):
        raise ErroAPI(403, "sem_privilegio", "a operação exige o privilégio feicoes.editar ou feicoes.editar_total",
                      {"exigido": "feicoes.editar|feicoes.editar_total"})
    return auth


def _saida(r: dict) -> PonteSaida:
    return PonteSaida(
        id=str(r["id"]), conexao=str(r["conexao_id"]), conexao_nome=r["conexao_nome"],
        formulario=str(r["formulario_id"]), projeto=r["projeto"], xml_form_id=r["xml_form_id"],
        versao=r["versao"], hash_central=r["hash_central"], publicado_em=iso(r["publicado_em"]),
        sincronizado_em=iso(r["sincronizado_em"]),
    )


def _ponte_ou_404(cur, pid: str) -> dict:
    cur.execute(f"SELECT {CAMPOS} FROM plat.odk_ponte p JOIN plat.conexao c ON c.id = p.conexao_id "  # noqa: S608
                "WHERE p.id = %s::uuid", (pid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "ponte_inexistente", "ponte inexistente")
    return r


def _conexao_odk(cur, cid: str) -> dict:
    cur.execute("SELECT id, tipo, url, credencial_cifrada FROM plat.conexao WHERE id = %s::uuid", (cid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "conexao_inexistente", "conexão inexistente")
    if r["tipo"] != "odk_central":
        raise ErroAPI(422, "conexao_nao_e_odk", "a conexão tem de ser do tipo odk_central",
                      {"tipo": r["tipo"]})
    return r


def _central(r: dict) -> Central:
    """Decifra a credencial só em memória, só aqui (mesmo padrão de `app/conexao/rotas.py::testar`)."""
    token = None
    if r["credencial_cifrada"]:
        try:
            token = decifrar_com_rotacao(
                credencial_mod.decifrar, r["credencial_cifrada"], settings.PLAT_SECRET,
                settings.PLAT_SECRET_ANTERIOR,
            )
        except Exception:  # noqa: BLE001 — PLAT_SECRET trocado ou dado corrompido: fala sem token e o Central 401
            token = None
    return Central(url_base=r["url"], token=token)


def _registrar_saude(auth: Auth, conexao_id: str, e: ErroCentral) -> None:
    """Grava a falha na saúde da conexão (L6-02-l) em transação PRÓPRIA, depois de a transação do pedido ter
    fechado. Feita dentro dela, a gravação sumiria no `rollback` que a exceção provoca — foi exatamente o que
    aconteceu na primeira versão deste item: a rota devolvia 409 e a tela de conexões continuava
    "nunca_testada"."""
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT plat.conexao_saude_registrar(%s::uuid, false, %s, %s, NULL)",
                    (str(conexao_id), e.status, f"odk:{e.motivo}"[:200]))


def _erro_do_central(auth: Auth, conexao_id: str, e: ErroCentral) -> ErroAPI:
    _registrar_saude(auth, conexao_id, e)
    status = 409 if e.motivo == "credencial_recusada" else 502
    return ErroAPI(status, f"odk_{e.motivo}", f"o ODK Central respondeu: {e.motivo}",
                   {"status_central": e.status})


def _formulario_ou_404(cur, iid: str) -> dict:
    r = comum.item_ou_404(cur, iid)
    if r["tipo"] != "formulario":
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    return r


@router.get("/pontes", response_model=PontePagina, openapi_extra=LER)
def listar(auth: Auth = autenticado(escopo_token="catalogo:ler")) -> PontePagina:
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT {CAMPOS} FROM plat.odk_ponte p JOIN plat.conexao c ON c.id = p.conexao_id "  # noqa: S608
                    "ORDER BY p.criado_em DESC LIMIT 200")
        itens = [_saida(r) for r in cur.fetchall()]
    return PontePagina(total=len(itens), itens=itens)


@router.post("/pontes", status_code=201, response_model=PonteSaida, openapi_extra=CRIAR)
def criar(corpo: PonteEntrada, request: Request, auth: Auth = autenticado("conteudo.registrar_fonte")):
    try:
        conteudo = base64.b64decode(corpo.conteudo, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ErroAPI(422, "conteudo_invalido", "conteúdo não é base64 válido") from e
    if len(conteudo) > limites.XLSFORM_TAMANHO_MAX:
        raise ErroAPI(422, "xlsform_grande", f"planilha acima de {limites.XLSFORM_TAMANHO_MAX} bytes")
    try:
        with db.db(auth.contexto()) as cur:
            formulario = _formulario_ou_404(cur, comum.uuid_ok(corpo.formulario))
            conexao = _conexao_odk(cur, comum.uuid_ok(corpo.conexao))
            doc = formulario["dados"] or {}
            # o nome só serve para a importação reconhecer a extensão (.xlsx); o título do item pode ser qualquer coisa
            enviado = xlsform.importar(conteudo, f"{doc.get('nome') or 'formulario'}.xlsx")
            _mesmo_formulario(doc, enviado)
            central = _central(conexao)
            try:
                publicado = central.publicar_xlsform(corpo.projeto, conteudo, doc.get("nome") or "formulario")
            except ErroCentral as e:
                raise _FalhaDoCentral(str(conexao["id"]), e) from e
            xml_form_id = str(publicado.get("xmlFormId") or doc.get("nome") or "")[:255]
            if not xml_form_id.strip():
                raise ErroAPI(502, "odk_sem_xml_form_id", "o Central publicou sem devolver xmlFormId")
            cur.execute(
                "INSERT INTO plat.odk_ponte(tenant_id, conexao_id, formulario_id, projeto, xml_form_id, versao, "
                "hash_central, publicado_em, dono_id) VALUES (plat.tenant_atual(), %s::uuid, %s::uuid, %s, %s, %s, "
                "%s, now(), plat.usuario_atual()) RETURNING id",
                (str(conexao["id"]), str(formulario["id"]), corpo.projeto, xml_form_id,
                 str(publicado.get("version") or "")[:100] or None,
                 str(publicado.get("hash") or "")[:100] or None),
            )
            pid = str(cur.fetchone()["id"])
            comum.registrar_evento(cur, request, "odk/publicar", "item", str(formulario["id"]),
                                   {"ponte": pid, "projeto": corpo.projeto, "xml_form_id": xml_form_id})
            return _saida(_ponte_ou_404(cur, pid))
    except _FalhaDoCentral as f:
        raise _erro_do_central(auth, f.conexao_id, f.erro) from f.erro
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


def _mesmo_formulario(doc: dict, enviado: dict) -> None:
    """A planilha enviada tem de ser a que gerou o formulário: mesmos campos-folha. Sem esta conferência, um
    formulário nosso apontaria para um formulário DIFERENTE no Central e a sincronização traria dado que não
    casa com a camada de destino (nenhum campo bateria e as feições viriam vazias, sem erro nenhum)."""
    from app.coleta.documento import folhas

    nossos = {c["nome"] for c, _r in folhas(doc.get("campos") or [])}
    dele = {c["nome"] for c, _r in folhas(enviado.get("campos") or [])}
    if nossos != dele:
        raise ErroAPI(422, "xlsform_diferente", "a planilha não é a que gerou este formulário",
                      {"so_no_formulario": sorted(nossos - dele)[:20], "so_na_planilha": sorted(dele - nossos)[:20]})


@router.get("/pontes/{id}", openapi_extra=LER)
def ver(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")) -> dict:
    pid = comum.uuid_ok(id, "ponte_inexistente", "ponte inexistente")
    with db.db(auth.contexto()) as cur:
        r = _ponte_ou_404(cur, pid)
        conexao = _conexao_odk(cur, str(r["conexao_id"]))
        try:
            central = _central(conexao).formulario(r["projeto"], r["xml_form_id"])
            falha = None
        except ErroCentral as e:
            central, falha = {"erro": e.motivo, "status": e.status}, e
        cur.execute("SELECT count(*) FILTER (WHERE feicao_id IS NOT NULL) AS aplicados, "
                    "count(*) FILTER (WHERE feicao_id IS NULL) AS recusados "
                    "FROM plat.odk_envio WHERE ponte_id = %s::uuid", (pid,))
        contagem = cur.fetchone()
    if falha is not None:
        _registrar_saude(auth, str(r["conexao_id"]), falha)
    return {"ponte": _saida(r).model_dump(), "central": central,
            "envios": {"aplicados": contagem["aplicados"], "recusados": contagem["recusados"]}}


@router.post("/pontes/{id}/sincronizar", openapi_extra=SINCRONIZAR)
def sincronizar(id: str, request: Request, auth: Auth = Depends(_auth_editor)) -> dict:
    pid = comum.uuid_ok(id, "ponte_inexistente", "ponte inexistente")
    try:
        with db.db(auth.contexto()) as cur:
            r = _ponte_ou_404(cur, pid)
            formulario = _formulario_ou_404(cur, str(r["formulario_id"]))
            camada = (formulario["dados"] or {}).get("camada_destino")
            if camada:
                esc.exigir_escopo(auth, "camada:editar", camada)
            conexao = _conexao_odk(cur, str(r["conexao_id"]))
            try:
                relatorio = ponte_mod.sincronizar(cur, request, auth, r, formulario, _central(conexao))
            except ErroCentral as e:
                raise _FalhaDoCentral(str(conexao["id"]), e) from e
            comum.registrar_evento(cur, request, "odk/sincronizar", "item", pid, {
                "lidos": relatorio["lidos"], "aplicados": relatorio["aplicados"],
                "repetidos": relatorio["repetidos"], "recusados": len(relatorio["recusados"]),
            })
            return relatorio
    except _FalhaDoCentral as f:
        raise _erro_do_central(auth, f.conexao_id, f.erro) from f.erro
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.get("/pontes/{id}/entidades/{dataset}", openapi_extra=LER)
def entidades(id: str, dataset: str, auth: Auth = autenticado(escopo_token="catalogo:ler")) -> dict:
    pid = comum.uuid_ok(id, "ponte_inexistente", "ponte inexistente")
    if not dataset.strip() or len(dataset) > 255:
        raise ErroAPI(422, "dataset_invalido", "nome de dataset inválido")
    with db.db(auth.contexto()) as cur:
        r = _ponte_ou_404(cur, pid)
        conexao = _conexao_odk(cur, str(r["conexao_id"]))
        try:
            brutas = _central(conexao).entidades(r["projeto"], dataset)
        except ErroCentral as e:
            falha = (str(conexao["id"]), e)
            brutas = None
        else:
            falha = None
    if falha is not None:
        raise _erro_do_central(auth, falha[0], falha[1])
    opcoes = ponte_mod.escolhas_de_entidades(brutas)
    colunas = sorted({k for o in opcoes for k in o if k not in ("nome", "rotulo")})
    return {"lista": dataset, "total": len(opcoes), "colunas": colunas, "opcoes": opcoes}
