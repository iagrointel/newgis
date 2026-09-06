"""Defesa contra SSRF do modelo de conexão externa (item L6-02-a-modelo-conexao-e-seguranca; ADR 0012; decisão
B7 de laco/decomposicao/L3L6_CONCEITO.md). Usado por toda rota que recebe URL de terceiro — hoje só
`app/conexao/rotas.py` (POST /api/conexoes e POST /api/conexoes/{id}/testar); qualquer conector futuro (L6-02-b
em diante) importa `buscar_seguro` daqui em vez de chamar `httpx`/`urllib` direto.

Mecanismo (os 8 casos do adversário do item, na ordem do portão):
  1. esquema fora de http/https (inclui `file://`)                        → `esquema_nao_permitido`
  2. host ausente na URL                                                  → `host_ausente`
  3. userinfo na URL (`http://user:pass@host/...`)                       → `userinfo_na_url`
  4. IP literal privado/loopback/link-local/CGNAT/reservado/multicast     → `ip_bloqueado:<categoria>`
     (cobre 127.0.0.1, 169.254.169.254 — metadado de nuvem —, 10.0.0.0/8 e as demais faixas RFC 1918/6598)
  5. host que RESOLVE (DNS) para um IP das mesmas faixas                  → mesmo erro (a resolução roda sempre,
     mesmo para IP literal, então rebinding de DNS entre a validação e o uso não passa: o IP usado na conexão
     real é o mesmo que foi validado — ver `cliente_pinado`, que fixa a conexão TCP nesse IP e deixa a
     verificação de TLS (SNI/hostname) olhar o nome original)
  6. redirecionamento para IP interno                                     → `buscar_seguro` NUNCA segue redirect
     automático (`follow_redirects=False` implícito); cada `Location` é revalidado do zero como uma URL nova,
     inclusive contra DNS rebinding, até `CONEXAO_REDIRECT_MAX` saltos
  7. porta interna (ex.: 8150-8159, reservadas nesta máquina)             → já cai no caso 4/5 quando o host é
     loopback; a faixa de porta em si NUNCA é usada como critério (um serviço público pode escutar em qualquer
     porta) — o que importa é o IP, nunca o número da porta
  8. DNS que muda entre a validação e a conexão (rebinding)               → `cliente_pinado` conecta ao(s) IP(s)
     já validados, nunca resolve de novo no momento da conexão (o backend customizado do httpcore não chama
     `getaddrinfo` outra vez para este host)
  9. credencial reenviada a outro host num redirecionamento               → `_sem_credencial_em_outro_host`
     (acrescentado no item L6-02-h): `Authorization`/`Cookie`/`Proxy-Authorization`/`X-Api-Key` só seguem
     quando o `Location` aponta para o MESMO host, mesma porta e sem cair de https para http. Este era o
     achado do adversário do L6-02-a que deixou aquele item marcado REFUTADO
"""

from __future__ import annotations

import ipaddress
import socket
import ssl
import typing
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturoTimeoutError
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpcore
import httpx

from app import limites

_ESQUEMAS_PERMITIDOS = {"http", "https"}
# faixas que ipaddress.is_private/is_reserved/etc. NÃO cobrem em toda versão do Python — CGNAT (RFC 6598) é o
# gap mais citado (100.64.0.0/10, usado por alguns provedores e por metadado de nuvem alternativo)
_REDES_EXTRAS_BLOQUEADAS = (ipaddress.ip_network("100.64.0.0/10"),)
_RESOLVEDOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="plat-conexao-dns")


class ErroURLInsegura(ValueError):
    def __init__(self, motivo: str, url: str):
        self.motivo = motivo
        self.url = url
        super().__init__(f"{motivo}: {url}")


@dataclass(frozen=True)
class URLValidada:
    url: str
    esquema: str
    host: str
    porta: int
    ips: tuple[str, ...]  # todos os IPs resolvidos e validados (não só o usado na conexão)


def _categoria_bloqueada(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link_local"  # cobre 169.254.169.254 (metadado de nuvem AWS/GCP/Azure)
    if ip.is_multicast:
        return "multicast"
    if ip.is_unspecified:
        return "nao_especificado"
    if ip.is_reserved:
        return "reservado"
    if ip.is_private:
        return "privado"
    for rede in _REDES_EXTRAS_BLOQUEADAS:
        if ip in rede:
            return "privado"
    return None


def _resolver_host(host: str, porta: int) -> list[str]:
    """`socket.getaddrinfo` sob timeout (roda em thread separada: a função da stdlib não aceita timeout
    direto). DNS que não responde a tempo é tratado como falha de validação, nunca como "sem restrição"."""

    def _consultar():
        return socket.getaddrinfo(host, porta, proto=socket.IPPROTO_TCP)

    futuro = _RESOLVEDOR.submit(_consultar)
    try:
        enderecos = futuro.result(timeout=limites.CONEXAO_DNS_TIMEOUT_S)
    except FuturoTimeoutError as e:
        raise ErroURLInsegura("dns_timeout", host) from e
    except socket.gaierror as e:
        raise ErroURLInsegura("dns_falhou", host) from e
    ips = sorted({info[4][0] for info in enderecos})
    if not ips:
        raise ErroURLInsegura("dns_sem_resposta", host)
    return ips


def validar_url(url: str) -> URLValidada:
    """Recusa o que a docstring do módulo lista; devolve host/porta/IPs já resolvidos e conferidos, prontos
    para `cliente_pinado`. Levanta `ErroURLInsegura` (nunca devolve "meio válido")."""
    if not url or len(url) > limites.CONEXAO_URL_MAX:
        raise ErroURLInsegura("url_vazia_ou_longa_demais", url or "")
    try:
        partes = urlsplit(url)
        porta_declarada = partes.port
    except ValueError as e:
        # porta fora de 0-65535 ou não numérica: urlsplit só levanta ao ACESSAR .port
        raise ErroURLInsegura("url_malformada", url) from e
    if partes.scheme.lower() not in _ESQUEMAS_PERMITIDOS:
        raise ErroURLInsegura("esquema_nao_permitido", url)
    if not partes.hostname:
        raise ErroURLInsegura("host_ausente", url)
    if partes.username is not None or partes.password is not None:
        raise ErroURLInsegura("userinfo_na_url", url)
    host = partes.hostname
    porta = porta_declarada or (443 if partes.scheme.lower() == "https" else 80)

    # IP literal na URL: ipaddress já resolve sem DNS; ainda assim passa pelo mesmo `_resolver_host` embaixo
    # (getaddrinfo aceita IP literal e devolve ele mesmo), então a checagem de categoria é uma só, adiante.
    ips = _resolver_host(host, porta)
    for ip_str in ips:
        ip = ipaddress.ip_address(ip_str)
        categoria = _categoria_bloqueada(ip)
        if categoria is not None:
            raise ErroURLInsegura(f"ip_bloqueado:{categoria}:{ip_str}", url)
    return URLValidada(url=url, esquema=partes.scheme.lower(), host=host, porta=porta, ips=tuple(ips))


class _BackendPinado(httpcore.SyncBackend):
    """Substitui, só para (host, porta) já validados, o alvo do `connect_tcp` pelo IP JÁ RESOLVIDO E
    CONFERIDO — o SNI/verificação de certificado TLS continua olhando o hostname original (httpcore passa
    `server_hostname=origin.host` para `start_tls` independente do IP realmente usado aqui: ver
    `httpcore._sync.connection.HTTPConnection._connect`). Isto é o que fecha o caso 8 (DNS rebinding): entre a
    validação e a conexão não há uma segunda consulta de DNS para este host."""

    def __init__(self, alvo: dict[tuple[str, int], str]):
        super().__init__()
        self._alvo = alvo

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable | None = None,
    ) -> httpcore.NetworkStream:
        ip_pinado = self._alvo.get((host, port), host)
        return super().connect_tcp(
            ip_pinado, port, timeout=timeout, local_address=local_address, socket_options=socket_options
        )


def cliente_pinado(validada: URLValidada, *, timeout_conectar: float, timeout_ler: float) -> httpx.Client:
    """Cliente httpx que só fala com `validada.host:validada.porta` (pinado no primeiro IP validado);
    `follow_redirects` fica False sempre — quem chama revalida o `Location` do zero (`buscar_seguro`)."""
    ssl_context = ssl.create_default_context() if validada.esquema == "https" else None
    # `__new__` (sem __init__): HTTPTransport só usa `self._pool` em handle_request/close (conferido na fonte
    # instalada, httpx 0.138.0) — monta o ConnectionPool direto com o backend pinado, sem abrir um pool default
    # primeiro só para descartar.
    transporte = httpx.HTTPTransport.__new__(httpx.HTTPTransport)
    transporte._pool = httpcore.ConnectionPool(
        ssl_context=ssl_context,
        network_backend=_BackendPinado({(validada.host, validada.porta): validada.ips[0]}),
        max_connections=4,
        retries=0,
    )
    timeout = httpx.Timeout(connect=timeout_conectar, read=timeout_ler, write=timeout_conectar, pool=timeout_conectar)
    return httpx.Client(transport=transporte, timeout=timeout, follow_redirects=False, trust_env=False)


@dataclass(frozen=True)
class ResultadoBusca:
    ok: bool
    status: int | None
    mensagem: str
    url_final: str
    latencia_ms: int
    saltos: int
    corpo: bytes = b""  # só preenchido quando `guardar_corpo=True` (item L6-05): teste de saúde nunca guarda
    # cabeçalhos de resposta do ÚLTIMO salto, em minúsculas (item L6-02-h: ETag/Last-Modified/Content-Type do
    # arquivo baixado). Só leitura; nunca inclui cabeçalho de requisição nem credencial.
    cabecalhos: dict[str, str] = field(default_factory=dict)


# Cabeçalhos que provam quem é o cliente: seguem para o host que o USUÁRIO escolheu, nunca para um terceiro
# que apareça num `Location`. Sem isto, um serviço público que a casa configurou com token consegue redirecionar
# para um servidor do atacante e receber o token de graça (achado do adversário do item L6-02-a, consertado aqui
# no item L6-02-h, que é o primeiro a mandar credencial para URL de terceiro em volume).
CABECALHOS_DE_CREDENCIAL = ("authorization", "cookie", "proxy-authorization", "x-api-key")


def _mesma_origem_de_confianca(anterior: str, novo: str) -> bool:
    """Mesmo host (case-insensitive) E não é uma queda de https para http. Porta diferente já é outro serviço."""
    a, b = urlsplit(anterior), urlsplit(novo)
    if (a.hostname or "").lower() != (b.hostname or "").lower():
        return False
    if a.scheme.lower() == "https" and b.scheme.lower() != "https":
        return False
    porta_a = a.port or (443 if a.scheme.lower() == "https" else 80)
    porta_b = b.port or (443 if b.scheme.lower() == "https" else 80)
    return porta_a == porta_b


def _sem_credencial_em_outro_host(cabecalhos: dict[str, str], anterior: str, novo: str) -> dict[str, str]:
    if _mesma_origem_de_confianca(anterior, novo):
        return cabecalhos
    return {k: v for k, v in cabecalhos.items() if k.lower() not in CABECALHOS_DE_CREDENCIAL}


def buscar_seguro(
    url: str,
    *,
    metodo: str = "GET",
    timeout_conectar: float = limites.CONEXAO_CONECTAR_TIMEOUT_S,
    timeout_ler: float = limites.CONEXAO_LER_TIMEOUT_S,
    max_redirects: int = limites.CONEXAO_REDIRECT_MAX,
    max_bytes: int = limites.CONEXAO_RESPOSTA_MAX_BYTES,
    cabecalhos: dict[str, str] | None = None,
    guardar_corpo: bool = False,
    conteudo: bytes | None = None,
) -> ResultadoBusca:
    """GET/HEAD seguro contra SSRF, com corpo limitado e redirecionamento revalidado hop a hop. Nunca levanta
    `ErroURLInsegura` para fora: qualquer recusa de validação vira `ResultadoBusca(ok=False, status=None, ...)`
    com o motivo em `mensagem` — quem chama (rota de teste de saúde) nunca precisa distinguir os dois.

    `guardar_corpo=True` (item L6-05-proveniencia-camada-externa: ler o que o serviço declara — GetCapabilities,
    `f=json`, catálogo STAC) acumula os bytes lidos (até `max_bytes`, o mesmo teto do teste de saúde) em
    `ResultadoBusca.corpo`; por padrão fica `b""` (o teste de saúde de L6-02-a nunca precisou do corpo, só do
    status).

    `conteudo` (item L6-02-i-google-sheets: POST de troca de token OAuth2) é o corpo da REQUISIÇÃO. Com corpo,
    redirecionamento NUNCA é seguido: reenviar um POST com assertion assinada para um `Location` escolhido pelo
    servidor seria entregar a credencial a outro dono — o 3xx volta para quem chamou decidir (a troca de token
    do Google responde 200 direto; qualquer redirect ali já é anomalia)."""
    import time

    inicio = time.monotonic()
    alvo = url
    cabecalhos_do_salto = dict(cabecalhos or {})
    for salto in range(max_redirects + 1):
        try:
            validada = validar_url(alvo)
        except ErroURLInsegura as e:
            return ResultadoBusca(
                ok=False, status=None, mensagem=f"url_insegura:{e.motivo}", url_final=alvo,
                latencia_ms=int((time.monotonic() - inicio) * 1000), saltos=salto,
            )
        with cliente_pinado(validada, timeout_conectar=timeout_conectar, timeout_ler=timeout_ler) as cliente:
            try:
                with cliente.stream(metodo, alvo, headers=cabecalhos_do_salto, content=conteudo) as r:
                    lido = 0
                    pedacos: list[bytes] = []
                    for pedaco in r.iter_bytes():
                        lido += len(pedaco)
                        if lido > max_bytes:
                            return ResultadoBusca(
                                ok=False, status=r.status_code, mensagem="resposta_excede_limite_de_bytes",
                                url_final=alvo, latencia_ms=int((time.monotonic() - inicio) * 1000), saltos=salto,
                            )
                        if guardar_corpo:
                            pedacos.append(pedaco)
                    status = r.status_code
                    corpo = b"".join(pedacos) if guardar_corpo else b""
            except httpx.TimeoutException:
                return ResultadoBusca(
                    ok=False, status=None, mensagem="tempo_esgotado", url_final=alvo,
                    latencia_ms=int((time.monotonic() - inicio) * 1000), saltos=salto,
                )
            except httpx.HTTPError as e:
                return ResultadoBusca(
                    ok=False, status=None, mensagem=f"erro_de_conexao:{type(e).__name__}", url_final=alvo,
                    latencia_ms=int((time.monotonic() - inicio) * 1000), saltos=salto,
                )
        if status in (301, 302, 303, 307, 308) and conteudo is None:
            local = r.headers.get("location")
            if not local:
                return ResultadoBusca(
                    ok=False, status=status, mensagem="redirecionamento_sem_location", url_final=alvo,
                    latencia_ms=int((time.monotonic() - inicio) * 1000), saltos=salto,
                )
            # Location relativo vira absoluto contra a URL atual, do mesmo jeito que um navegador faria
            anterior = alvo
            alvo = httpx.URL(alvo).join(local).__str__()
            cabecalhos_do_salto = _sem_credencial_em_outro_host(cabecalhos_do_salto, anterior, alvo)
            continue
        return ResultadoBusca(
            ok=200 <= status < 400, status=status, mensagem=f"http_{status}", url_final=alvo,
            latencia_ms=int((time.monotonic() - inicio) * 1000), saltos=salto, corpo=corpo,
            cabecalhos={k.lower(): v for k, v in r.headers.items()},
        )
    return ResultadoBusca(
        ok=False, status=None, mensagem="redirecionamentos_demais", url_final=alvo,
        latencia_ms=int((time.monotonic() - inicio) * 1000), saltos=max_redirects,
    )
