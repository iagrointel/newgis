"""Pool de páginas do chromium do playwright (item L2-12-a-motor-render-servidor). Uma única instância de
`Motor` por processo (`motor()` abaixo), com N páginas mantidas quentes (context managers do playwright não
fecham entre pedidos), fila com limite (`PLAT_RENDER_FILA_MAX`; acima disso é 429, nunca fila sem fundo) e um
teto de tempo por pedido (`PLAT_RENDER_TIMEOUT_S`). google-chrome do sistema NUNCA é usado (regra da casa: quebra
nesta máquina) — só o chromium instalado pelo playwright (`playwright install chromium`).

Isolamento de rede (cláusula "página headless sem acesso à rede externa"): cada contexto intercepta TODA
requisição e só deixa passar host em `HOSTS_PERMITIDOS` (127.0.0.1/::1/localhost e o host de `PLAT_URL_PUBLICA`
em produção); o resto é abortado antes de sair da máquina — testável sem depender de firewall.

"frio" vs "quente" (cláusula de tempo p95): os primeiros `tamanho_pool` renders de um Motor recém-iniciado são
"frio" (a página está sendo usada pela primeira vez: primeiro `goto` de verdade, cache do processo vazio); os
seguintes são "quente" (mesma página, navegação nova por cima da anterior). É uma definição operacional, não a
única possível — declarada aqui para o adversário poder discordar dela.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app.settings import settings

log = logging.getLogger("plat.render")

HOSTS_PERMITIDOS = frozenset({"127.0.0.1", "::1", "localhost"})


class ErroFilaCheia(RuntimeError):
    pass


class ErroRenderTimeout(RuntimeError):
    pass


@dataclass
class Estatisticas:
    em_execucao: int = 0
    fila_atual: int = 0
    falhas_total: int = 0
    sucesso_total: int = 0
    tempos_ms: list[float] = field(default_factory=list)
    tamanho_pool: int = 0

    def registrar(self, ms: float, ok: bool) -> None:
        if ok:
            self.sucesso_total += 1
            self.tempos_ms.append(ms)
            self.tempos_ms = self.tempos_ms[-500:]  # janela: não cresce sem fim num processo de vida longa
        else:
            self.falhas_total += 1

    def tempo_medio_ms(self) -> float | None:
        if not self.tempos_ms:
            return None
        return round(sum(self.tempos_ms) / len(self.tempos_ms), 1)

    def como_dict(self) -> dict:
        return {
            "em_execucao": self.em_execucao,
            "fila_atual": self.fila_atual,
            "falhas_total": self.falhas_total,
            "sucesso_total": self.sucesso_total,
            "tempo_medio_ms": self.tempo_medio_ms(),
            "tamanho_pool": self.tamanho_pool,
        }


def _host_permitido(host: str | None, extra: frozenset[str]) -> bool:
    return bool(host) and (host in HOSTS_PERMITIDOS or host in extra)


async def _bloquear_rede_externa(route, extra_hosts: frozenset[str]) -> None:
    host = urlsplit(route.request.url).hostname
    if _host_permitido(host, extra_hosts):
        await route.continue_()
    else:
        await route.abort("blockedbyclient")


class Motor:
    """Um motor por processo. `iniciar()`/`parar()` são chamados no ciclo de vida do ASGI (main.py) em
    produção; os testes chamam os dois diretamente, sem subir a app inteira."""

    def __init__(self, tamanho_pool: int | None = None, fila_max: int | None = None, timeout_s: int | None = None):
        self.tamanho_pool = tamanho_pool or settings.PLAT_RENDER_POOL_TAMANHO
        self.fila_max = fila_max or settings.PLAT_RENDER_FILA_MAX
        self.timeout_s = timeout_s or settings.PLAT_RENDER_TIMEOUT_S
        self._pw = None
        self._navegador = None
        self._paginas: asyncio.Queue | None = None
        self._sem: asyncio.Semaphore | None = None
        self._lock_fila = asyncio.Lock()
        self._fila_len = 0
        self._usos_pagina: dict[int, int] = {}
        self.stats = Estatisticas()
        self._extra_hosts: frozenset[str] = frozenset()
        if settings.PLAT_URL_PUBLICA:
            h = urlsplit(settings.PLAT_URL_PUBLICA).hostname
            if h:
                self._extra_hosts = frozenset({h})

    @property
    def ativo(self) -> bool:
        return self._navegador is not None

    async def iniciar(self) -> None:
        if self.ativo:
            return
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._navegador = await self._pw.chromium.launch(headless=True)
        self._paginas = asyncio.Queue()
        self._sem = asyncio.Semaphore(self.tamanho_pool)
        self.stats.tamanho_pool = self.tamanho_pool
        for _ in range(self.tamanho_pool):
            ctx = await self._navegador.new_context()
            await ctx.route("**/*", lambda route: _bloquear_rede_externa(route, self._extra_hosts))
            pagina = await ctx.new_page()
            self._usos_pagina[id(pagina)] = 0
            await self._paginas.put(pagina)
        log.info("motor de render iniciado: pool=%s fila_max=%s timeout_s=%s", self.tamanho_pool, self.fila_max,
                  self.timeout_s)

    async def parar(self) -> None:
        if not self.ativo:
            return
        while self._paginas and not self._paginas.empty():
            pagina = self._paginas.get_nowait()
            try:
                await pagina.context.close()
            except Exception:  # noqa: BLE001 — encerrando; nunca deixa exceção de fechamento subir
                log.exception("motor de render: falha fechando contexto")
        await self._navegador.close()
        await self._pw.stop()
        self._navegador = None
        self._pw = None
        self._paginas = None
        self._sem = None

    async def renderizar(
        self,
        url: str,
        *,
        largura: int,
        altura: int,
        dpi: int = 96,
        formato: str = "png",
        espera_seletor: str = "body[data-pronto='1']",
        espera_timeout_ms: int = 15000,
    ) -> tuple[bytes, str]:
        """Devolve (bytes, media_type). Levanta ErroFilaCheia (fila no limite) ou ErroRenderTimeout (o
        pedido não terminou dentro de `PLAT_RENDER_TIMEOUT_S`, teto único para fila + execução — nunca
        30 s só de execução DEPOIS de esperar a fila o tempo que for)."""
        if not self.ativo:
            raise RuntimeError("motor de render não iniciado")
        async with self._lock_fila:
            if self._fila_len >= self.fila_max:
                raise ErroFilaCheia(f"fila cheia ({self.fila_max})")
            self._fila_len += 1
            self.stats.fila_atual = self._fila_len
        inicio = time.perf_counter()
        try:
            return await asyncio.wait_for(
                self._renderizar_dentro_do_pool(url, largura, altura, dpi, formato, espera_seletor,
                                                 espera_timeout_ms),
                timeout=self.timeout_s,
            )
        except TimeoutError as e:
            self.stats.registrar((time.perf_counter() - inicio) * 1000, ok=False)
            raise ErroRenderTimeout(f"render não terminou em {self.timeout_s}s") from e
        except Exception:
            self.stats.registrar((time.perf_counter() - inicio) * 1000, ok=False)
            raise
        finally:
            async with self._lock_fila:
                self._fila_len -= 1
                self.stats.fila_atual = self._fila_len

    async def _pagina_de_reposicao(self, velha):
        """Fecha uma página que travou no meio de uma navegação e abre uma NOVA no lugar (mesma cláusula da
        refutação do item: "mata o processo do chromium no meio e confere recuperação do pool"). Achado real
        rodando a medida de p95 sob carga: um `goto` que estoura o timeout deixa a MESMA página presa —
        as duas navegações seguintes na mesma página falharam também, até esta troca existir. Sem isso, uma
        única contenção transitória envenena aquele slot do pool para sempre."""
        try:
            await velha.context.close()
        except Exception:  # noqa: BLE001 — a página já está quebrada; fechar também pode falhar, ignora
            log.exception("motor de render: falha fechando página envenenada")
        ctx = await self._navegador.new_context()
        await ctx.route("**/*", lambda route: _bloquear_rede_externa(route, self._extra_hosts))
        nova = await ctx.new_page()
        self._usos_pagina.pop(id(velha), None)
        self._usos_pagina[id(nova)] = 0
        return nova

    async def _renderizar_dentro_do_pool(self, url, largura, altura, dpi, formato, espera_seletor,
                                          espera_timeout_ms) -> tuple[bytes, str]:
        async with self._sem:
            self.stats.em_execucao += 1
            inicio = time.perf_counter()
            pagina = await self._paginas.get()
            pagina_envenenada = False
            try:
                # `largura`/`altura` são o tamanho FINAL em pixels do PNG (a página do render.html não tem
                # chrome nenhum: o viewport É a imagem). `dpi` não reescala o viewport — quem pede 2.480×3.508
                # já pediu o pixel exato de uma A4 a 300 DPI; o DPI entra só como metadado do PNG (Pillow,
                # abaixo) e como `scale` nativo do PDF do chromium, que É físico (pontos, não pixels de CSS).
                await pagina.set_viewport_size({"width": largura, "height": altura})
                try:
                    await pagina.goto(url, wait_until="load", timeout=espera_timeout_ms)
                except Exception:
                    pagina_envenenada = True
                    raise
                try:
                    await pagina.wait_for_selector(espera_seletor, timeout=espera_timeout_ms)
                except Exception as e:  # noqa: BLE001 — vira erro de render, não trava o pool
                    pagina_envenenada = True
                    raise ErroRenderTimeout(f"a página não sinalizou pronto ({espera_seletor})") from e
                self._usos_pagina[id(pagina)] += 1
                frio = self._usos_pagina[id(pagina)] == 1
                if formato == "pdf":
                    dados = await pagina.pdf(width=f"{largura}px", height=f"{altura}px", print_background=True,
                                              scale=min(max(dpi / 96, 0.1), 2))
                    media = "application/pdf"
                else:
                    # `dpi` não é gravado no PNG (evita depender do Pillow em produção — regra da casa,
                    # ADR 0001: só venv + dpkg, nunca `~/.local`; Pillow só existe aqui via
                    # `--system-site-packages` de desenvolvimento). Quem pede DPI já pede o pixel exato
                    # (2.480×3.508 para A4 a 300 DPI); o metadado físico é responsabilidade de quem compuser
                    # o PDF a partir do PNG, não deste motor.
                    dados = await pagina.screenshot(type="png")
                    media = "image/png"
                ms = (time.perf_counter() - inicio) * 1000
                self.stats.registrar(ms, ok=True)
                log.info("render %s: %sms (%s)", formato, round(ms, 1), "frio" if frio else "quente")
                return dados, media
            finally:
                self.stats.em_execucao -= 1
                if pagina_envenenada:
                    try:
                        pagina = await self._pagina_de_reposicao(pagina)
                    except Exception:  # noqa: BLE001 — mesmo a reposição falhando, a página velha já foi
                        # descartada; devolve o que der (o próximo pedido tenta de novo) em vez de sumir com
                        # o slot do pool para sempre
                        log.exception("motor de render: falha abrindo página de reposição")
                await self._paginas.put(pagina)


_motor: Motor | None = None


def motor() -> Motor:
    global _motor
    if _motor is None:
        _motor = Motor()
    return _motor
