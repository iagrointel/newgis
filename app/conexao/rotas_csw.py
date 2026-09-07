"""Rotas de descoberta por catálogo CSW 2.0.2 (item L6-06-descoberta-csw). `POST /api/csw/buscar` procura por
texto e/ou bbox num catálogo de terceiros (a INDE, um geoportal) e devolve os registros ISO 19139 lidos, cada um
com os serviços WMS/WFS/WMTS que declara com endereço. `POST /api/csw/conexoes` lê um registro por id
(`GetRecordById`) e cria, num clique, uma `plat.conexao` por serviço declarado — com a ficha de procedência
preenchida do ISO em `config.procedencia` (o `publicar` da conexão completa a ficha com o que o serviço vivo
declarar; o que o serviço não disser vem do registro). Registro sem `OnlineResource` WMS/WFS/WMTS com endereço
devolve 422 `sem_servico_ligado` e NÃO cria conexão nenhuma (refutação do item: "sem serviço ligado, nunca uma
conexão vazia").

Toda leitura do catálogo passa por `seguranca.buscar_seguro` (SSRF, bytes e tempo limitados, redirecionamento
revalidado) — a URL do catálogo é validada ANTES de qualquer conexão, e a URL de cada serviço declarado é validada
antes de virar conexão (serviço que aponta para rede interna vira aviso, nunca conexão). Mesmo privilégio do
`POST /api/conexoes` (`conteudo.registrar_fonte`) para criar; a busca exige `conteudo.criar` (quem pode criar
conteúdo pode consultar um catálogo público por trás do proxy da casa)."""

from __future__ import annotations

import datetime
import json

import psycopg2
from fastapi import APIRouter, Request
from pydantic import Field

from app import db, limites
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.conexao import csw, seguranca
from app.conexao.modelos import Conexao, Modelo, Saida
from app.conexao.rotas import _carregar, _config_ok, _json, _url_ok
from app.erros import ErroAPI

router = APIRouter(prefix="/api/csw", tags=["conexoes"])
BUSCAR = {"x-auth": "S/T", "x-privilegio": "conteudo.criar"}
CRIAR = {"x-auth": "S/T", "x-privilegio": "conteudo.registrar_fonte"}
TIPOS_PADRAO = ("wms", "wfs", "wmts")


class BuscaEntrada(Modelo):
    url: str = Field(min_length=1, max_length=limites.CONEXAO_URL_MAX, description="endereço do CSW 2.0.2")
    texto: str | None = Field(default=None, max_length=limites.CSW_TEXTO_BUSCA_MAX)
    bbox: list[float] | None = Field(
        default=None, min_length=4, max_length=4, description="[oeste, sul, leste, norte] em graus"
    )
    inicio: int = Field(default=1, ge=1, le=1_000_000)
    maximo: int = Field(default=10, ge=1, le=limites.CSW_MAX_REGISTROS)


class ServicoSaida(Saida):
    tipo: str
    url: str
    camada: str | None = None
    url_declarada: str
    protocolo: str


class RegistroSaida(Saida):
    identificador: str | None = None
    titulo: str | None = None
    resumo: str | None = None
    organizacao: str | None = None
    data_do_dado: str | None = None
    data_metadado: str | None = None
    palavras_chave: list[str]
    bbox: list[float] | None = None
    licenca: str | None = None
    restricoes: list[str]
    frequencia: str | None = None
    servicos: list[ServicoSaida]
    sem_servico: bool
    avisos: list[str]


class BuscaSaida(Saida):
    url_pedida: str
    total: int
    devolvidos: int
    inicio: int
    proximo: int | None = None
    registros: list[RegistroSaida]


class CriarEntrada(Modelo):
    url: str = Field(min_length=1, max_length=limites.CONEXAO_URL_MAX)
    identificador: str = Field(min_length=1, max_length=500)
    tipos: list[str] | None = Field(default=None, description="subconjunto de wms/wfs/wmts; padrão = todos")


class ConexaoCriada(Conexao):
    criada: bool  # False = já existia uma conexão igual (tipo, url, camada) e foi reaproveitada


class CriarSaida(Saida):
    registro: RegistroSaida
    conexoes: list[ConexaoCriada]
    avisos: list[str]


def _bbox_ok(bbox: list[float] | None) -> list[float] | None:
    if bbox is None:
        return None
    oeste, sul, leste, norte = bbox
    if not (-180 <= oeste <= 180 and -180 <= leste <= 180 and -90 <= sul <= 90 and -90 <= norte <= 90
            and oeste < leste and sul < norte):
        raise ErroAPI(
            422, "bbox_invalida", "bbox precisa ser [oeste, sul, leste, norte] em graus, com oeste<leste e sul<norte"
        )
    return bbox


def _ler(alvo: str) -> bytes:
    """GET seguro ao catálogo; qualquer falha de rede/HTTP vira 502 `csw_indisponivel` com o motivo — nunca 500."""
    r = seguranca.buscar_seguro(
        alvo, timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=limites.CSW_LER_TIMEOUT_S,
        max_bytes=limites.CONEXAO_RESPOSTA_MAX_BYTES, guardar_corpo=True,
    )
    if not r.ok or not r.corpo:
        raise ErroAPI(
            502, "csw_indisponivel", f"o catálogo não respondeu de forma utilizável: {r.mensagem}",
            {"url": alvo, "status": r.status, "mensagem": r.mensagem, "latencia_ms": r.latencia_ms},
        )
    return r.corpo


def _erro_csw(e: csw.ErroCSW, alvo: str) -> ErroAPI:
    return ErroAPI(
        502, "csw_resposta_invalida", f"a resposta do catálogo não é um CSW 2.0.2 utilizável: {e.motivo}",
        {"url": alvo, "motivo": e.motivo, "detalhe": e.detalhe},
    )


@router.post("/buscar", response_model=BuscaSaida, openapi_extra=BUSCAR)
def buscar(corpo: BuscaEntrada, auth: Auth = autenticado("conteudo.criar")):
    _url_ok(corpo.url)
    bbox = _bbox_ok(corpo.bbox)
    if not (corpo.texto and corpo.texto.strip()) and bbox is None:
        raise ErroAPI(422, "busca_vazia", "informe um texto e/ou uma bbox")
    alvo = csw.url_getrecords(corpo.url, corpo.texto, bbox, corpo.inicio, corpo.maximo)
    bruto = _ler(alvo)
    try:
        res = csw.analisar_getrecords(bruto)
    except csw.ErroCSW as e:
        raise _erro_csw(e, alvo) from e
    return {
        "url_pedida": alvo, "total": res.total, "devolvidos": res.devolvidos, "inicio": corpo.inicio,
        "proximo": res.proximo, "registros": [csw.registro_json(r) for r in res.registros],
    }


def _existente(cur, tipo: str, url: str, camada: str | None):
    cur.execute(
        "SELECT id FROM plat.conexao WHERE tipo = %s AND url = %s AND config->>'camada' IS NOT DISTINCT FROM %s "
        "ORDER BY criado_em LIMIT 1",
        (tipo, url, camada),
    )
    r = cur.fetchone()
    return str(r["id"]) if r else None


def _nome(registro: csw.Registro, servico: csw.Servico, tentativa: int) -> str:
    base = " ".join((registro.titulo or registro.identificador or servico.url).split())
    tipo = servico.tipo.upper()
    sufixo = f" ({tipo})" if tentativa == 0 else f" ({tipo} {servico.camada or tentativa})"
    corte = limites.CONEXAO_NOME_MAX - len(sufixo)
    return base[:corte].rstrip() + sufixo


@router.post("/conexoes", response_model=CriarSaida, status_code=201, openapi_extra=CRIAR)
def criar_conexoes(corpo: CriarEntrada, request: Request, auth: Auth = autenticado("conteudo.criar")):
    if not auth.tem("conteudo.registrar_fonte"):
        raise ErroAPI(
            403, "sem_privilegio", "a operação exige o privilégio conteudo.registrar_fonte",
            {"exigido": "conteudo.registrar_fonte"},
        )
    _url_ok(corpo.url)
    tipos = tuple(t for t in (corpo.tipos or TIPOS_PADRAO) if t in TIPOS_PADRAO) or TIPOS_PADRAO
    alvo = csw.url_getrecordbyid(corpo.url, corpo.identificador)
    bruto = _ler(alvo)
    try:
        registro = csw.analisar_getrecordbyid(bruto)
    except csw.ErroCSW as e:
        raise _erro_csw(e, alvo) from e
    if registro is None:
        raise ErroAPI(
            404, "registro_inexistente", "o catálogo não tem registro com esse identificador",
            {"identificador": corpo.identificador},
        )
    servicos = [s for s in registro.servicos if s.tipo in tipos]
    if not servicos:
        raise ErroAPI(
            422, "sem_servico_ligado",
            "sem serviço ligado: o registro não declara OnlineResource WMS/WFS/WMTS com endereço; "
            "nenhuma conexão criada",
            {"identificador": corpo.identificador, "avisos": registro.avisos},
        )

    avisos = list(registro.avisos)
    hoje = datetime.datetime.now(datetime.UTC).date().isoformat()
    saida: list[dict] = []
    for servico in servicos:
        try:
            seguranca.validar_url(servico.url)
        except seguranca.ErroURLInsegura as e:
            avisos.append(f"serviço {servico.tipo.upper()} {servico.url} recusado: {e.motivo}")
            continue
        config = {
            "camada": servico.camada,
            "csw": {"url": corpo.url, "identificador": registro.identificador},
            "procedencia": csw.ficha(registro, servico, corpo.url, bruto, hoje),
        }
        _config_ok(config)
        with db.db(auth.contexto()) as cur:
            cid = _existente(cur, servico.tipo, servico.url, servico.camada)
            criada = cid is None
            if criada:
                for tentativa in range(3):
                    try:
                        cur.execute("SAVEPOINT conexao_csw")
                        cur.execute(
                            "INSERT INTO plat.conexao(tenant_id, tipo, modo, nome, url, config, dono_id) "
                            "VALUES (%s, %s, 'referenciada', %s, %s, %s::jsonb, %s) RETURNING id",
                            (
                                auth.tenant_id, servico.tipo, _nome(registro, servico, tentativa), servico.url,
                                json.dumps(config, ensure_ascii=False), auth.usuario_id,
                            ),
                        )
                        cid = str(cur.fetchone()["id"])
                        cur.execute("RELEASE SAVEPOINT conexao_csw")
                        break
                    except psycopg2.errors.UniqueViolation:
                        cur.execute("ROLLBACK TO SAVEPOINT conexao_csw")  # nome já usado: tenta com a camada no nome
                    except psycopg2.Error as e:
                        raise auth_comum.erro_do_banco(e) from e
                if cid is None:
                    raise ErroAPI(
                        409, "nome_existente", "já existe uma conexão com esse nome (3 variações tentadas)"
                    )
                registrar_evento(
                    cur, request, "conexoes/criar", "conexao", cid,
                    {"tipo": servico.tipo, "nome": _nome(registro, servico, 0), "modo": "referenciada",
                     "origem": "csw", "identificador": registro.identificador},
                )
            linha = _json(_carregar(cur, cid))
        linha["criada"] = criada
        saida.append(linha)
    if not saida:
        raise ErroAPI(
            422, "sem_servico_ligado",
            "sem serviço ligado: todo serviço declarado no registro foi recusado pela validação de endereço",
            {"identificador": corpo.identificador, "avisos": avisos},
        )
    return {"registro": csw.registro_json(registro), "conexoes": saida, "avisos": avisos}
