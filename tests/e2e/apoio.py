"""Apoio dos e2e do L0-02 (ADR 0002 seções 15 e 16.5): coletor de console/respostas, login pela tela, capturas,
TOTP de 6 linhas (RFC 6238; T=59 -> 287082 conferido), credenciais de tests/credenciais.txt e chamadas à API pelo
contexto do navegador (mesmo cookie). Nenhum número digitado: o que se mede vai para tests/medidas pelo fixture."""

import base64
import hashlib
import hmac
import os
import re
import secrets
import struct
import time
from pathlib import Path

ITEM = "L0-02-tenant-auth"
RAIZ = Path(__file__).resolve().parents[2]
CAPTURAS = Path(__file__).resolve().parent / "capturas"
RECURSO_FALHOU = re.compile(r"Failed to load resource: the server responded with a status of (\d{3})")


def totp(segredo_b32: str, t: float | None = None) -> str:
    """TOTP RFC 6238 (SHA-1, 30 s, 6 dígitos) em biblioteca padrão; a mesma função do backend."""
    chave = base64.b32decode(segredo_b32 + "=" * (-len(segredo_b32) % 8), casefold=True)
    h = hmac.new(chave, struct.pack(">Q", int((time.time() if t is None else t) // 30)), hashlib.sha1).digest()
    o = h[-1] & 15
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000).zfill(6)


def passo_atual() -> int:
    return int(time.time() // 30)


def esperar_proximo_passo(passo_usado: int) -> None:
    """anti-replay: um código já aceito no passo N não vale de novo; espera o passo N+1 começar."""
    while passo_atual() <= passo_usado:
        time.sleep(0.5)


def credenciais() -> dict[str, tuple[str, str]]:
    """{slug: (login, senha)} lido de tests/credenciais.txt (escrito pelo install.sh; fora do git). Item
    L7-31: PLAT_CREDENCIAIS_ARQUIVO aponta para tests/credenciais_homolog.txt (db/homolog_bootstrap.sh
    semeia os admins do schema plat_homolog lá — nunca os mesmos usuário/senha de produção)."""
    out = {}
    caminho = Path(os.environ.get("PLAT_CREDENCIAIS_ARQUIVO") or (RAIZ / "tests" / "credenciais.txt"))
    if not caminho.exists():
        return out
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if len(partes) == 3:
            out[partes[0]] = (partes[1], partes[2])
    return out


def sufixo() -> str:
    return secrets.token_hex(3)


class Tela:
    """Uma página do playwright com coleta de erros de console, erros de página e respostas >= 400.

    Chromium grava "Failed to load resource: ... status of 4xx" como console.error mesmo quando o 4xx é a resposta
    esperada de um fluxo (senha errada = 401). Esses, e só esses, são aceitos quando o status foi declarado com
    esperar_status(); qualquer outro erro de console reprova (cláusula P1: 0 erro de console)."""

    def __init__(self, page, base_url: str, item: str | None = None):
        # `item` nomeia a captura (tests/e2e/capturas/<item>_<nome>.png). Sem argumento, cai no ITEM deste
        # módulo (L0-02) por compatibilidade — era o único valor possível antes (achado no item
        # L2-02-e-simbolos-sprites-glifos: toda captura de todo item saía como "L0-02-tenant-auth_*", porque
        # `capturar()` usava a constante do módulo em vez do item do teste que a chamou).
        self.item = item or ITEM
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.console: list[str] = []
        self.respostas: list[tuple[str, int]] = []
        self.esperados: set[int] = set()
        self.medidas: dict[str, float] = {}
        page.on("console", lambda m: self.console.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: self.console.append(f"pageerror: {e}"))
        page.on("response", lambda r: self.respostas.append((r.url, r.status)))

    def esperar_status(self, *codigos: int) -> None:
        self.esperados.update(codigos)

    def ir(self, caminho: str, nome_medida: str | None = None) -> float:
        t0 = time.perf_counter()
        self.page.goto(caminho, wait_until="domcontentloaded")
        self.page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        if nome_medida:
            self.medidas[nome_medida] = ms
        return ms

    def entrar(self, slug: str, login: str, senha: str, proximo: str = "/") -> None:
        self.page.goto(f"/entrar?inquilino={slug}&proximo={proximo}", wait_until="domcontentloaded")
        self.page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        self.page.fill("#login", login)
        self.page.fill("#senha", senha)
        self.page.click("#entrar")
        self.page.wait_for_url(lambda u: not u.rstrip("/").endswith("/entrar") and "/entrar?" not in u, timeout=20000)
        self.page.wait_for_selector("body[data-pronto='1']", timeout=20000)

    def sair(self) -> None:
        self.page.click("#sair")
        self.page.wait_for_url(lambda u: "/entrar" in u, timeout=20000)
        self.page.wait_for_selector("body[data-pronto='1']", timeout=20000)

    def capturar(self, nome: str) -> Path:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{self.item}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho

    def api(self, metodo: str, caminho: str, corpo=None, cabecalhos: dict | None = None):
        """chamada à API pelo contexto do navegador (mesmo cookie de sessão)."""
        kw = {"method": metodo, "headers": {"Content-Type": "application/json", **(cabecalhos or {})}}
        if corpo is not None:
            kw["data"] = corpo
        elif metodo in ("POST", "PUT"):
            kw["data"] = {}
        return self.page.request.fetch(f"{self.base_url}{caminho}", **kw)

    def verificar(self) -> None:
        graves = []
        for linha in self.console:
            m = RECURSO_FALHOU.search(linha)
            if m and int(m.group(1)) in self.esperados:
                continue
            graves.append(linha)
        assert graves == [], graves
        ruins = [(u, s) for u, s in self.respostas if s >= 400 and s not in self.esperados]
        assert ruins == [], ruins


def texto_aviso(page, seletor: str = "#aviso") -> str:
    return (page.text_content(seletor) or "").strip()


def gravar_medidas(medida, tela: Tela) -> None:
    gravar = medida(tela.item)
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright (tests/e2e/apoio.py Tela.ir)")
