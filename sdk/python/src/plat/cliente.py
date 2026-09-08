"""Camada ergonômica escrita à mão sobre `plat_gerado` (o cliente gerado do OpenAPI 3.1). Devolve
dicionários JSON simples (o mesmo corpo que a API manda), não os objetos `attrs` do cliente gerado —
quem precisa do objeto tipado usa `plat_gerado` direto (também instalado por este pacote). Paginação
por cursor e retentativa de rede ficam aqui; a API continua sem saber que o SDK existe."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import httpx
from plat_gerado import AuthenticatedClient, Client
from plat_gerado.api.catalogo import apagar_api_itens_id_delete as _rt_item_apagar
from plat_gerado.api.catalogo import criar_api_itens_post as _rt_item_criar
from plat_gerado.api.catalogo import editar_parcial_api_itens_id_patch as _rt_item_editar
from plat_gerado.api.catalogo import facetas_api_itens_facetas_get as _rt_item_facetas
from plat_gerado.api.catalogo import listar_api_itens_get as _rt_item_listar
from plat_gerado.api.catalogo import mover_api_itens_id_mover_post as _rt_item_mover
from plat_gerado.api.catalogo import ver_api_itens_id_get as _rt_item_ver
from plat_gerado.api.compartilhamento import (
    alterar_compartilhamento_api_itens_id_compartilhamento_put as _rt_compart_alterar,
)
from plat_gerado.api.compartilhamento import ver_compartilhamento_api_itens_id_compartilhamento_get as _rt_compart_ver
from plat_gerado.api.eu import eu_api_eu_get as _rt_eu
from plat_gerado.api.jobs import listar_jobs_api_jobs_get as _rt_job_listar
from plat_gerado.api.jobs import obter_job_api_jobs_job_id_get as _rt_job_obter
from plat_gerado.api.jobs import tipos_de_job_api_jobs_tipos_get as _rt_job_tipos
from plat_gerado.api.login import login_api_login_post as _rt_login
from plat_gerado.api.tokens import criar_api_tokens_post as _rt_token_criar
from plat_gerado.api.tokens import listar_api_tokens_get as _rt_token_listar
from plat_gerado.api.tokens import log_do_token_api_tokens_id_log_get as _rt_token_log
from plat_gerado.api.tokens import renovar_api_tokens_id_renovar_post as _rt_token_renovar
from plat_gerado.api.tokens import revogar_api_tokens_id_delete as _rt_token_revogar
from plat_gerado.models.compartilhamento_entrada import CompartilhamentoEntrada
from plat_gerado.models.editar_parcial_api_itens_id_patch_corpo import EditarParcialApiItensIdPatchCorpo
from plat_gerado.models.item_entrada import ItemEntrada
from plat_gerado.models.item_entrada_dados import ItemEntradaDados
from plat_gerado.models.login_entrada import LoginEntrada
from plat_gerado.models.mover_entrada import MoverEntrada
from plat_gerado.models.token_criar import TokenCriar
from plat_gerado.types import UNSET, Response

from .erros import ErroPlataforma, erro_de_corpo

ESTADOS_TERMINAIS_JOB = frozenset({"concluido", "falhou", "cancelado"})
PREFIXO_TIPO_CAMADA = "camada_"
TENTATIVAS_PADRAO = 3
ESPERA_BASE_S = 0.5
# 429/502/503/504: taxa e indisponibilidade transitória (nunca 4xx de validação/permissão, que repetir não conserta)
STATUS_RETENTAVEIS = frozenset({429, 502, 503, 504})


def _bruto(resposta: Response) -> Any:
    """Decodifica o corpo (bytes) da resposta em JSON; None se vazio (204), bytes crus se não for JSON."""
    if not resposta.content:
        return None
    try:
        return json.loads(resposta.content)
    except ValueError:
        return resposta.content


def _extrair(resposta: Response) -> Any:
    """Sucesso (2xx) devolve o corpo decodificado; qualquer outro status levanta `ErroPlataforma`
    (o corpo de erro é sempre decodificado do bruto, nunca do `.parsed` do gerado — o gerado só
    tipa os status documentados no OpenAPI, e a maioria dos erros, 401/403/404/409, não está lá)."""
    status = int(resposta.status_code)
    if 200 <= status < 300:
        return _bruto(resposta)
    raise erro_de_corpo(status, _bruto(resposta))


def _com_retentativa(chamada, tentativas: int = TENTATIVAS_PADRAO):
    """Repete `chamada()` (uma `Response` do cliente gerado) em erro de rede ou status transitório
    (`STATUS_RETENTAVEIS`), com espera exponencial (0,5 s, 1 s, 2 s, ...). Nunca repete erro do próprio
    pedido (validação, permissão, conflito) — repetir isso nunca muda o resultado."""
    ultimo_erro: Exception | None = None
    for tentativa in range(tentativas):
        if tentativa:
            time.sleep(ESPERA_BASE_S * (2 ** (tentativa - 1)))
        try:
            resposta = chamada()
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            ultimo_erro = e
            continue
        if int(resposta.status_code) in STATUS_RETENTAVEIS and tentativa < tentativas - 1:
            continue
        return resposta
    assert ultimo_erro is not None
    raise ErroPlataforma(
        status=0,
        tipo="rede_indisponivel",
        titulo=f"falha de rede após {tentativas} tentativa(s): {ultimo_erro}",
        detalhe=str(ultimo_erro),
    )


class RecursoBase:
    def __init__(self, cliente: AuthenticatedClient):
        self._cliente = cliente


class Itens(RecursoBase):
    """`/api/itens`: o catálogo (mapas, camadas, conexões e todo `tipo_item` cadastrado)."""

    def listar(
        self,
        *,
        tipo: str | list[str] | None = None,
        limite: int | None = None,
        cursor: str | None = None,
        **filtros: Any,
    ) -> dict:
        """Uma página (`{"total","itens","proximo_cursor","aproximado"}`). `filtros` aceita qualquer
        parâmetro de consulta da rota (`q`, `tags`, `pasta_id`, `bbox`, `favoritos`, `meus`, ...)."""
        parametros = {"tipo": tipo, "limite": limite, "cursor": cursor, **filtros}
        parametros = {k: (v if v is not None else UNSET) for k, v in parametros.items()}
        resposta = _com_retentativa(lambda: _rt_item_listar.sync_detailed(client=self._cliente, **parametros))
        return _extrair(resposta)

    def todos(self, *, tipo: str | list[str] | None = None, **filtros: Any) -> Iterator[dict]:
        """Itera TODOS os itens da consulta, virando página sozinho pelo `proximo_cursor` — a
        paginação embutida do SDK: quem chama nunca lê `proximo_cursor` na mão."""
        cursor: str | None = None
        while True:
            pagina = self.listar(tipo=tipo, cursor=cursor, **filtros)
            yield from pagina.get("itens") or []
            cursor = pagina.get("proximo_cursor")
            if not cursor:
                return

    def obter(self, item_id: str) -> dict:
        resposta = _com_retentativa(lambda: _rt_item_ver.sync_detailed(id=item_id, client=self._cliente))
        return _extrair(resposta)

    def criar(
        self,
        tipo: str,
        titulo: str,
        *,
        resumo: str | None = None,
        descricao: str | None = None,
        tags: list[str] | None = None,
        pasta_id: str | None = None,
        extent: list[float] | None = None,
        categorias: list[str] | None = None,
        url: str | None = None,
        origem: str = "hospedado",
        dados: dict | None = None,
    ) -> dict:
        corpo = ItemEntrada(
            tipo=tipo,
            titulo=titulo,
            resumo=resumo,
            descricao=descricao,
            tags=tags if tags is not None else UNSET,
            pasta_id=pasta_id,
            extent=extent,
            categorias=categorias if categorias is not None else UNSET,
            url=url,
            origem=origem,
            dados=ItemEntradaDados.from_dict(dados) if dados is not None else UNSET,
        )
        resposta = _com_retentativa(lambda: _rt_item_criar.sync_detailed(client=self._cliente, body=corpo))
        return _extrair(resposta)

    def atualizar(self, item_id: str, **campos: Any) -> dict:
        """`PATCH /api/itens/{id}`: só os campos passados mudam (edição parcial)."""
        resposta = _rt_item_editar.sync_detailed(
            id=item_id, client=self._cliente, body=EditarParcialApiItensIdPatchCorpo.from_dict(campos)
        )
        return _extrair(resposta)

    def apagar(self, item_id: str, *, cascata: bool = False) -> None:
        resposta = _rt_item_apagar.sync_detailed(id=item_id, client=self._cliente, cascata=cascata)
        _extrair(resposta)

    def mover(self, item_id: str, pasta_id: str | None) -> dict:
        resposta = _rt_item_mover.sync_detailed(id=item_id, client=self._cliente, body=MoverEntrada(pasta_id=pasta_id))
        return _extrair(resposta)

    def facetas(self) -> dict:
        """`GET /api/itens/facetas`: contagem por tipo/tag/categoria do que o dono do token pode ler
        (sem parâmetro — a rota não filtra, é sempre a visão inteira do inquilino)."""
        resposta = _com_retentativa(lambda: _rt_item_facetas.sync_detailed(client=self._cliente))
        return _extrair(resposta)

    def compartilhamento(self, item_id: str) -> dict:
        resposta = _com_retentativa(lambda: _rt_compart_ver.sync_detailed(id=item_id, client=self._cliente))
        return _extrair(resposta)

    def compartilhar(self, item_id: str, *, acesso: str, grupos: list[str] | None = None) -> dict:
        corpo = CompartilhamentoEntrada(acesso=acesso, grupos=grupos if grupos is not None else UNSET)
        resposta = _rt_compart_alterar.sync_detailed(id=item_id, client=self._cliente, body=corpo)
        return _extrair(resposta)


class Camadas(Itens):
    """Visão de `/api/itens` filtrada em `tipo_item` que começa com `camada_` — não é rota própria
    da API (não existe `/api/camadas`; ver `docs/PARIDADE.md`, seção rede/OGC, para o que falta para
    uma camada virar FeatureServer de verdade — item `L2-04-servicos-esri-ogc`, dependência aberta)."""

    TIPO_PADRAO = "camada_vetorial"

    def listar(self, *, tipo: str | list[str] | None = None, **filtros: Any) -> dict:
        return super().listar(tipo=tipo or self.TIPO_PADRAO, **filtros)

    def todos(self, *, tipo: str | list[str] | None = None, **filtros: Any) -> Iterator[dict]:
        yield from super().todos(tipo=tipo or self.TIPO_PADRAO, **filtros)

    def criar(self, titulo: str, *, tipo: str = TIPO_PADRAO, **campos: Any) -> dict:
        return super().criar(tipo, titulo, **campos)


class Mapas(Itens):
    """Visão de `/api/itens` filtrada em `tipo_item = "mapa"` — mesma ressalva de `Camadas`."""

    TIPO_PADRAO = "mapa"

    def listar(self, *, tipo: str | list[str] | None = None, **filtros: Any) -> dict:
        return super().listar(tipo=tipo or self.TIPO_PADRAO, **filtros)

    def todos(self, *, tipo: str | list[str] | None = None, **filtros: Any) -> Iterator[dict]:
        yield from super().todos(tipo=tipo or self.TIPO_PADRAO, **filtros)

    def criar(self, titulo: str, *, tipo: str = TIPO_PADRAO, **campos: Any) -> dict:
        return super().criar(tipo, titulo, **campos)


class Jobs(RecursoBase):
    """`/api/jobs`: fila assíncrona (ingestão, exportação pesada, agenda). `esperar()` faz o
    polling que a hipótese do item pede — a API não tem webhook nem SSE para job ainda."""

    def listar(self, **filtros: Any) -> dict:
        parametros = {k: (v if v is not None else UNSET) for k, v in filtros.items()}
        resposta = _com_retentativa(lambda: _rt_job_listar.sync_detailed(client=self._cliente, **parametros))
        return _extrair(resposta)

    def obter(self, job_id: str) -> dict:
        resposta = _com_retentativa(lambda: _rt_job_obter.sync_detailed(job_id=job_id, client=self._cliente))
        return _extrair(resposta)

    def tipos(self) -> list[dict]:
        resposta = _com_retentativa(lambda: _rt_job_tipos.sync_detailed(client=self._cliente))
        return _extrair(resposta)

    def esperar(self, job_id: str, *, tempo_limite_s: float = 60.0, intervalo_s: float = 1.0) -> dict:
        """Espera o job chegar a um estado terminal (`concluido`, `falhou`, `cancelado`) ou levanta
        `TimeoutError` em `tempo_limite_s`. Nunca espera para sempre."""
        inicio = time.monotonic()
        while True:
            job = self.obter(job_id)
            if job.get("estado") in ESTADOS_TERMINAIS_JOB:
                return job
            if time.monotonic() - inicio >= tempo_limite_s:
                raise TimeoutError(
                    f"job {job_id} não chegou a estado terminal em {tempo_limite_s}s "
                    f"(estado atual: {job.get('estado')!r})"
                )
            time.sleep(intervalo_s)


class Tokens(RecursoBase):
    """`/api/tokens`: tokens de serviço. TODA rota deste recurso exige SESSÃO de cookie na API
    (`so_sessao=True` em `listar`, `criar`, `ver`, `revogar`, `renovar`, `log` — ADR 0002 seção 8:
    "um token não se perpetua", nem por `admin:inquilino`); é por isso que `Plataforma.entrar()`
    guarda o cliente de sessão do login e o passa para cá (`cliente_sessao`). Sem sessão viva
    (`Plataforma(url, token=...)` direto, sem `entrar()`), todo método aqui bate no mesmo 403
    `so_sessao` que a API devolveria a qualquer token — não é um limite do SDK, é o modelo de
    autorização real (ver `docs/PARIDADE.md`)."""

    def __init__(self, cliente: AuthenticatedClient, *, cliente_sessao: Client | None = None):
        super().__init__(cliente)
        self._cliente_sessao = cliente_sessao

    def _cliente_de_sessao_ou_erro(self) -> AuthenticatedClient | Client:
        return self._cliente_sessao or self._cliente

    def listar(self) -> list[dict]:
        cliente = self._cliente_de_sessao_ou_erro()
        resposta = _com_retentativa(lambda: _rt_token_listar.sync_detailed(client=cliente))
        return _extrair(resposta)

    def criar(
        self, nome: str, escopos: list[str], *, validade_dias: int | None = None, restricao: dict | None = None
    ) -> dict:
        corpo = TokenCriar(
            nome=nome,
            escopos=escopos,
            validade_dias=validade_dias,
            restricao=restricao if restricao is not None else UNSET,
        )
        cliente = self._cliente_de_sessao_ou_erro()
        resposta = _rt_token_criar.sync_detailed(client=cliente, body=corpo)
        return _extrair(resposta)

    def revogar(self, token_id: int) -> None:
        cliente = self._cliente_de_sessao_ou_erro()
        resposta = _rt_token_revogar.sync_detailed(id=token_id, client=cliente)
        _extrair(resposta)

    def renovar(self, token_id: int) -> dict:
        cliente = self._cliente_de_sessao_ou_erro()
        resposta = _rt_token_renovar.sync_detailed(id=token_id, client=cliente)
        return _extrair(resposta)

    def log(self, token_id: int) -> list[dict]:
        cliente = self._cliente_de_sessao_ou_erro()
        resposta = _com_retentativa(lambda: _rt_token_log.sync_detailed(id=token_id, client=cliente))
        return _extrair(resposta)


class Plataforma:
    """Ponto de entrada do SDK: `Plataforma(url, token="plat_...")`.

    `url` é a URL pública do inquilino (com ou sem barra final); `token` é um token de serviço
    (`plat_...`, criado em Minha conta -> Tokens, ou por `Plataforma.entrar(...)`)."""

    def __init__(
        self,
        url: str,
        token: str,
        *,
        tempo_limite_s: float = 30.0,
        verificar_tls: bool = True,
        _cliente_sessao: Client | None = None,
        _token_id: int | None = None,
    ):
        if not token:
            raise ValueError("token vazio: crie um token de serviço em Minha conta -> Tokens")
        self.url = url.rstrip("/")
        self.token = token
        # só presente quando este objeto veio de `entrar()`: id do próprio token, para quem quiser
        # `p.tokens.revogar(p.token_id)` ao terminar (o limite de tokens ativos por usuário é real —
        # 20, ver app/limites.py — e um SDK que nunca revoga o que cria esgota a conta de exemplo).
        self.token_id = _token_id
        self._cliente = AuthenticatedClient(
            base_url=self.url,
            token=token,
            prefix="Bearer",
            timeout=httpx.Timeout(tempo_limite_s),
            verify_ssl=verificar_tls,
        )
        # só presente quando este objeto veio de `entrar()`: guarda o cookie de sessão do login
        # para que `.tokens.criar()`/`.renovar()` (so_sessao=True na API) continuem funcionando.
        self._cliente_sessao = _cliente_sessao
        self.itens = Itens(self._cliente)
        self.camadas = Camadas(self._cliente)
        self.mapas = Mapas(self._cliente)
        self.jobs = Jobs(self._cliente)
        self.tokens = Tokens(self._cliente, cliente_sessao=_cliente_sessao)

    def __repr__(self) -> str:  # pragma: no cover — nunca imprime o token
        return f"Plataforma(url={self.url!r})"

    def eu(self) -> dict:
        """`GET /api/eu`: identidade e privilégios de quem o token representa."""
        resposta = _com_retentativa(lambda: _rt_eu.sync_detailed(client=self._cliente))
        return _extrair(resposta)

    def fechar(self) -> None:
        if self._cliente_sessao is not None:
            self._cliente_sessao.get_httpx_client().close()
        self._cliente.get_httpx_client().close()

    def __enter__(self) -> "Plataforma":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.fechar()

    @classmethod
    def entrar(
        cls,
        url: str,
        inquilino: str,
        login: str,
        senha: str,
        *,
        nome_token: str = "sdk-python",
        escopos: list[str] | None = None,
        validade_dias: int | None = None,
        verificar_tls: bool = True,
    ) -> "Plataforma":
        """Login por usuário e senha (`POST /api/login`), depois cria um token de serviço com a
        sessão resultante (`POST /api/tokens`, que só aceita sessão de cookie) e devolve um
        `Plataforma` já autenticado por esse token — o padrão de uso é o token, o login é só a
        porta de entrada para tirar o primeiro token. Levanta `ErroPlataforma` em 2FA obrigatório
        (a API devolve `exige_2fa=true`; este SDK não implementa TOTP — use um token já existente)."""
        url_normalizada = url.rstrip("/")
        # o MESMO objeto `Client` em login e criação do token: seu httpx.Client interno é cacheado
        # (get_httpx_client) e guarda o cookie de sessão que /api/login emite — é o que faz o 2º
        # pedido (POST /api/tokens, so_sessao=True) andar autenticado.
        cliente_sessao = Client(base_url=url_normalizada, verify_ssl=verificar_tls)
        resposta = _rt_login.sync_detailed(
            client=cliente_sessao, body=LoginEntrada(inquilino=inquilino, login=login, senha=senha)
        )
        corpo = _bruto(resposta)
        if resposta.status_code != 200 or not (isinstance(corpo, dict) and corpo.get("ok")):
            if isinstance(corpo, dict) and corpo.get("exige_2fa"):
                raise ErroPlataforma(
                    status=int(resposta.status_code),
                    tipo="exige_2fa",
                    titulo="conta com 2FA obrigatório (este SDK não implementa TOTP; use um token já existente)",
                    detalhe=corpo,
                )
            raise erro_de_corpo(int(resposta.status_code), corpo)
        resposta_token = _rt_token_criar.sync_detailed(
            client=cliente_sessao,
            body=TokenCriar(
                nome=nome_token,
                escopos=escopos or ["admin:inquilino"],
                validade_dias=validade_dias if validade_dias is not None else UNSET,
            ),
        )
        corpo_token = _extrair(resposta_token)
        # a sessão fica viva dentro do Plataforma resultante (`.tokens.criar/renovar` a reusam);
        # `Plataforma.fechar()`/`with Plataforma.entrar(...) as p:` fecha as duas conexões juntas.
        return cls(
            url_normalizada,
            token=corpo_token["token"],
            verificar_tls=verificar_tls,
            _cliente_sessao=cliente_sessao,
            _token_id=corpo_token["id"],
        )
