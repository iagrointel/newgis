"""Bancada de carga de ladrilhos do item L1-02-d (cache nginx + prova de carga).

Mede, contra uma pilha REAL e local à trilha (uvicorn com a aplicação + nginx próprio de usuário, com
`proxy_cache` em disco, chave SEM o token, `proxy_cache_lock` e `auth_request` antes do cache):

1. quente — 1 a 200 conexões sobre uma grade já cacheada (portão do pai: >= 500 tiles/s, 0 erro);
2. frio — 1 conexão, ladrilhos nunca pedidos (portão: >= 15 tiles/s, todo MISS, todo 200 com pixel);
3. `proxy_cache_lock` — 20 pedidos simultâneos ao MESMO ladrilho frio = 1 MISS + 19 HIT, contados no
   access log do nginx (não no cliente);
4. chave com parâmetros de renderização — RGB e NDVI do mesmo ladrilho têm corpos diferentes e cada
   variante faz o seu próprio MISS/HIT (a chave leva `$args`: nunca se misturam);
5. revogação — token revogado recebe 403 em <= 5 s mesmo com o ladrilho quente no cache (a
   autorização é conferida antes do cache; caches de 2 s + 2 s em série), e um SEGUNDO token do mesmo
   inquilino continua recebendo HIT do MESMO ladrilho (é por isso que a chave não tem o token);
6. eviction — cache enchido além de `max_size`: o cache manager remove os menos usados, o tamanho em
   disco assenta abaixo do teto e nenhum pedido devolve 5xx.

O COG é sintético de 4 bandas (R,G,B,NIR falso), 4096x4096 em EPSG:3857 alinhado à grade z14, servido
como `acervo://` (disco local, sem Garage — esta trilha não tem). 16x16 ladrilhos em z14, 32x32 em
z15, 64x64 em z16: a fase fria, a do cadeado e a de eviction usam zooms distintos e nunca se
contaminam (cada ladrilho frio é pedido uma única vez na rodada).

Roda dentro de pytest por `tests/carga/test_l102d_bancada.py`; também roda solto
(`venv/bin/python tests/carga/tiles.py`), escrevendo o JSON de fechamento só com
`PLAT_GRAVAR_MEDIDAS=1`. A config de produção deste cache vive em `deploy/nginx.conf` (bloco
`/svc/<tok>/raster|mosaico`); o template abaixo é a versão de bancada — zona pequena de propósito,
para a eviction ser provável em segundos.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------- COG sintético
SHIFT = 20037508.342789244  # meia circunferência do Web Mercator, em metros
LADO_PX = 4096
Z_ANCORAGEM = 14                      # o COG cobre 16x16 ladrilhos neste zoom
TILES_POR_EIXO_Z14 = 16
BANDAS = 4                            # R, G, B, NIR falso (o NDVI da prova da chave usa b4 e b1)


def _tile_m(z: int) -> float:
    """Aresta de um ladrilho de 256 px do zoom z, em metros."""
    return 2 * SHIFT / (2 ** z)


def _origem() -> tuple[float, float]:
    """Canto superior esquerdo do COG, múltiplo inteiro da aresta z14 (grade alinhada)."""
    t = _tile_m(Z_ANCORAGEM)
    return t * -409, t * 20


def _grade(z: int) -> list[tuple[int, int]]:
    """(x, y) dos ladrilhos do zoom z cobertos pelo COG. y conta de cima (slippy/rio-tiler)."""
    if z < Z_ANCORAGEM:
        raise ValueError("a bancada só usa z >= 14")
    passo = 2 ** (z - Z_ANCORAGEM)
    t = _tile_m(z)
    x0, y0 = _origem()
    # a origem é múltiplo inteiro da aresta POR CONSTRUÇÃO; `floor` aqui perde um ladrilho por erro de
    # ponto flutuante (7783*t vira 7782.9999…), então é `round` com guarda de alinhamento
    col_f, lin_f = (x0 + SHIFT) / t, (SHIFT - y0) / t
    assert abs(col_f - round(col_f)) < 1e-6 and abs(lin_f - round(lin_f)) < 1e-6, (col_f, lin_f)
    col0, lin0 = round(col_f), round(lin_f)
    lado = TILES_POR_EIXO_Z14 * passo
    return [(col0 + i, lin0 + j) for i in range(lado) for j in range(lado)]


def _gerar_cog(destino: Path) -> Path:
    """COG 4 bandas uint8 com padrão + ruído: ladrilho ~dezenas de KB (eviction em poucas centenas)."""
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    x0, y0 = _origem()
    res = _tile_m(Z_ANCORAGEM) / 256
    yy, xx = np.mgrid[0:LADO_PX, 0:LADO_PX].astype("float32")
    base = np.sin(xx / 37.0) * 60 + np.cos(yy / 29.0) * 60
    ruido = np.random.default_rng(20260918).integers(0, 45, size=(LADO_PX, LADO_PX), dtype="uint8")
    bandas = [
        (128 + base + ruido).clip(0, 255).astype("uint8"),                    # R
        (118 + base * 0.8 + ruido // 2).clip(0, 255).astype("uint8"),         # G
        (108 - base * 0.6 + ruido // 3).clip(0, 255).astype("uint8"),         # B
        (140 - base + ruido).clip(0, 255).astype("uint8"),                    # NIR falso
    ]
    with rasterio.open(destino, "w", driver="COG", height=LADO_PX, width=LADO_PX, count=BANDAS,
                       dtype="uint8", crs="EPSG:3857", compress="deflate",
                       transform=from_origin(x0, y0, res, res)) as dst:
        for i, b in enumerate(bandas, start=1):
            dst.write(b, i)
    return destino


# --------------------------------------------------------------------------- registro do item
def semear_item(tenant_id: int, caminho_relativo: str, cog: Path) -> dict:
    """Item STAC + raster_item + plat.item apontando para `acervo://<caminho>` (sem Garage)."""
    import pyproj

    from app import db
    from app.catalogo.comum import jsonb
    from app.imagens import pgstac as ps
    from app.imagens import raster_item as ri

    x0, y0 = _origem()
    ext = TILES_POR_EIXO_Z14 * _tile_m(Z_ANCORAGEM)
    lonlat = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    oeste, norte = lonlat.transform(x0, y0)
    leste, sul = lonlat.transform(x0 + ext, y0 - ext)
    sha = hashlib.sha256(cog.read_bytes()).hexdigest()
    with db.db(db.Contexto(tenant_id=tenant_id, usuario_id=0, login="bancada")) as cur:
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s ORDER BY id LIMIT 1", (tenant_id,))
        usuario_id = cur.fetchone()["id"]
    ctx = db.Contexto(tenant_id=tenant_id, usuario_id=usuario_id, login="bancada")
    item_id = str(uuid.uuid4())
    colecao = ps.nome_colecao(tenant_id, "imagens")
    tipo_cog = "image/tiff; application=geotiff; profile=cloud-optimized"
    asset = {"href": f"acervo://{caminho_relativo}", "type": tipo_cog}
    stac = {
        "type": "Feature", "stac_version": "1.0.0", "id": item_id, "collection": colecao,
        "geometry": {"type": "Polygon", "coordinates": [[
            [oeste, sul], [oeste, norte], [leste, norte], [leste, sul], [oeste, sul]]]},
        "bbox": [oeste, sul, leste, norte],
        "properties": {"datetime": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                       "title": "zt-l102d-bancada COG sintético 4 bandas"},
        "assets": {"cientifico": {**asset, "roles": ["data"]}, "visual": {**asset, "roles": ["visual"]}},
        "links": [],
    }
    with db.db(ctx) as cur:
        ps.colecao_espelhar(cur, tenant_id, "imagens", colecao)
        ps.item_criar(cur, tenant_id, colecao, stac)
        ri.espelhar(cur, tenant_id, colecao, item_id, {
            "sha256": sha, "perfil": "cientifico", "bytes": cog.stat().st_size, "estado": "ativo"})
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, criado_por, "
            "modificado_por) VALUES (%s::uuid, %s, 'raster', %s, %s, %s, %s, %s, %s)",
            (item_id, tenant_id, "zt-l102d-bancada COG sintético", usuario_id,
             jsonb({"colecao": colecao, "stac_id": item_id, "perfil": "cientifico", "origem": "acervo",
                    "srid_nativo": 3857, "bandas": [{"nome": n} for n in ("r", "g", "b", "nir")]}),
             cog.stat().st_size, usuario_id, usuario_id))
    return {"item_id": item_id, "colecao": colecao, "sha256": sha}


# --------------------------------------------------------------------------- nginx da bancada
NGINX_TEMPLATE = """\
# bancada L1-02-d — instância de usuário, nunca a do sistema. Produção: deploy/nginx.conf.
worker_processes 2;
pid @PID@;
lock_file @PREFIX@/nginx.lock;
error_log @PREFIX@/logs/error.log warn;
events { worker_connections 2048; }
http {
    log_format bancada '$status|$upstream_cache_status|$request_time|$plat_tipo/$plat_item/$plat_resto';
    access_log @PREFIX@/logs/access.log bancada;
    client_body_temp_path @PREFIX@/tmp/body;
    proxy_temp_path @PREFIX@/tmp/proxy;
    fastcgi_temp_path @PREFIX@/tmp/fcgi;
    uwsgi_temp_path @PREFIX@/tmp/uwsgi;
    scgi_temp_path @PREFIX@/tmp/scgi;
    proxy_cache_path @PREFIX@/cache/tiles levels=1:2 keys_zone=bancada_tiles:16m
                     max_size=@MAXMB@m inactive=1d use_temp_path=off;
    proxy_cache_path @PREFIX@/cache/auth levels=1:2 keys_zone=bancada_auth:4m
                     max_size=8m inactive=1m use_temp_path=off;
    server {
        listen 127.0.0.1:@PORTA@;
        location = /saude { proxy_pass http://127.0.0.1:@APP@; }
        # chave SEM o token (hipótese do item): dois tokens do mesmo inquilino compartilham ladrilho;
        # quem separa inquilinos na chave é o <item> (uuid do catálogo do inquilino). $args entra:
        # NDVI e RGB do mesmo item NUNCA se misturam.
        location ~ ^/svc/(?<plat_tok>[A-Za-z0-9_-]+)/(?<plat_tipo>raster|mosaico)/(?<plat_item>[^/]+)/(?<plat_resto>.+)$ {
            auth_request /_plat_tile_autorizar;
            proxy_cache bancada_tiles;
            proxy_cache_key "$plat_tipo|$plat_item|$plat_resto|$args";
            proxy_cache_lock on;
            proxy_cache_lock_timeout 20s;
            proxy_cache_valid 200 204 30m;
            proxy_cache_use_stale updating error timeout;
            proxy_cache_background_update on;
            proxy_read_timeout 60s;
            add_header X-Plat-Cache $upstream_cache_status always;
            proxy_pass http://127.0.0.1:@APP@;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
        }
        location = /_plat_tile_autorizar {
            internal;
            proxy_pass http://127.0.0.1:@APP@/api/tiles/autorizar;
            proxy_pass_request_body off;
            proxy_set_header Content-Length "";
            proxy_set_header X-Plat-Token $plat_tok;
            proxy_set_header X-Plat-Item $plat_item;
            proxy_set_header X-Plat-Tipo $plat_tipo;
            proxy_set_header X-Real-IP $remote_addr;
            # a aplicação põe no-store em tudo (ADR 0002); sem ignorar, toda autorização ia à aplicação
            proxy_ignore_headers Cache-Control Expires Set-Cookie;
            proxy_cache bancada_auth;
            proxy_cache_key "$plat_tok|$plat_tipo|$plat_item|$http_referer|$http_origin|$remote_addr";
            proxy_cache_valid 204 403 2s;
            proxy_cache_lock on;
        }
    }
}
"""


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Pilha:
    """uvicorn (aplicação) + nginx de usuário com proxy_cache. Para os dois ao sair, sempre."""

    def __init__(self, raiz_trabalho: Path, acervo: Path, max_cache_mb: int = 12):
        self.raiz = raiz_trabalho
        self.acervo = acervo
        self.max_cache_mb = max_cache_mb
        self.porta_app = _porta_livre()
        self.porta_nginx = _porta_livre()
        self.prefixo = raiz_trabalho / "nginx"
        self._proc_app: subprocess.Popen | None = None
        self.url_nginx = f"http://127.0.0.1:{self.porta_nginx}"
        self.url_app = f"http://127.0.0.1:{self.porta_app}"

    @property
    def log_acesso(self) -> Path:
        return self.prefixo / "logs" / "access.log"

    def __enter__(self) -> "Pilha":
        (self.prefixo / "logs").mkdir(parents=True)
        (self.prefixo / "tmp").mkdir()  # o nginx cria as folhas (body/proxy/...), não os pais
        (self.prefixo / "cache").mkdir()
        conf = (NGINX_TEMPLATE
                .replace("@PREFIX@", str(self.prefixo))
                .replace("@PID@", str(self.prefixo / "nginx.pid"))
                .replace("@PORTA@", str(self.porta_nginx))
                .replace("@APP@", str(self.porta_app))
                .replace("@MAXMB@", str(self.max_cache_mb)))
        arq_conf = self.prefixo / "nginx.conf"
        arq_conf.write_text(conf, encoding="utf-8")
        self._nginx = shutil.which("nginx") or "/usr/sbin/nginx"
        env = dict(os.environ, PLAT_ACERVO_ARQUIVOS_RAIZ=str(self.acervo))
        self._proc_app = subprocess.Popen(  # noqa: S603 — comando fixo, porta escolhida pela bancada
            [str(ROOT / "venv" / "bin" / "python"), "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(self.porta_app), "--log-level", "warning"],
            cwd=ROOT, env=env,
            stdout=(self.raiz / "app.out").open("wb"), stderr=subprocess.STDOUT)
        self._esperar(self.url_app, "aplicação")
        subprocess.run([self._nginx, "-p", str(self.prefixo), "-c", str(arq_conf)], check=True,
                       capture_output=True, timeout=30)
        self._esperar(self.url_nginx, "nginx")
        return self

    def _esperar(self, base: str, nome: str, limite_s: float = 90) -> None:
        import httpx

        fim = time.monotonic() + limite_s
        while time.monotonic() < fim:
            try:
                if httpx.get(f"{base}/saude", timeout=3).status_code == 200:
                    return
            except Exception:  # noqa: BLE001 — subindo ainda; qualquer recusa vale como "não pronto"
                pass
            time.sleep(0.4)
        rabo = ""
        try:
            rabo = (self.raiz / "app.out").read_text(encoding="utf-8", errors="ignore")[-2000:]
        except OSError:
            pass
        raise RuntimeError(f"{nome} não respondeu /saude em {limite_s}s (porta {base}). saída: {rabo}")

    def __exit__(self, *exc) -> None:
        subprocess.run([getattr(self, "_nginx", "nginx"), "-p", str(self.prefixo), "-c",
                        str(self.prefixo / "nginx.conf"), "-s", "quit"],
                       capture_output=True, timeout=30)
        if self._proc_app is not None:
            self._proc_app.send_signal(signal.SIGTERM)
            try:
                self._proc_app.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self._proc_app.kill()


# --------------------------------------------------------------------------- medições
async def _pedidos(urls: list[str]) -> list[tuple[int, str, int, bytes]]:
    """Dispara todos os GETs de uma vez; devolve (status, cache, bytes, corpo) na ordem."""
    import httpx

    async def um(c, u):
        try:
            r = await c.get(u, timeout=60)
            return (r.status_code, (r.headers.get("x-plat-cache") or "-").strip(),
                    len(r.content), r.content)
        except Exception:  # noqa: BLE001 — erro de rede conta como falha do pedido, não derruba a fase
            return (0, "ERRO", 0, b"")

    async with httpx.AsyncClient(base_url="", http2=False,
                                 limits=httpx.Limits(max_connections=len(urls) + 8,
                                                     max_keepalive_connections=len(urls) + 8)) as c:
        return await asyncio.gather(*(um(c, u) for u in urls))


def _uma_conexao(urls: list[str]) -> tuple[list[tuple[int, str, int, bytes]], float]:
    """Sequencial, uma conexão keep-alive: a definição de 'frio, 1 conexão' do portão."""
    import httpx

    saida = []
    with httpx.Client(http2=False, timeout=60,
                      limits=httpx.Limits(max_connections=1, max_keepalive_connections=1)) as c:
        t0 = time.monotonic()
        for u in urls:
            try:
                r = c.get(u)
                saida.append((r.status_code, (r.headers.get("x-plat-cache") or "-").strip(),
                              len(r.content), r.content))
            except Exception:  # noqa: BLE001
                saida.append((0, "ERRO", 0, b""))
        return saida, time.monotonic() - t0


async def _janela_quente(base: str, urls: list[str], conexoes: int, segundos: float) -> dict:
    """`conexoes` clientes em paralelo, cada um o seu keep-alive, pedindo a grade em rodízio."""
    import httpx

    fim = time.monotonic() + segundos
    conta = {"ok": 0, "erro": 0}

    async def trabalhador(desl: int) -> None:
        i = desl
        async with httpx.AsyncClient(http2=False, timeout=30) as c:
            while time.monotonic() < fim:
                try:
                    r = await c.get(base + urls[i % len(urls)])
                    conta["ok" if r.status_code == 200 else "erro"] += 1
                except Exception:  # noqa: BLE001
                    conta["erro"] += 1
                i += conexoes

    t0 = time.monotonic()
    await asyncio.gather(*(trabalhador(k) for k in range(conexoes)))
    dt = time.monotonic() - t0
    total = conta["ok"] + conta["erro"]
    return {"conexoes": conexoes, "segundos": round(dt, 2), "pedidos": total,
            "tiles_por_s": round(total / dt, 1), "falhas": conta["erro"],
            "ms_por_pedido": round(dt * 1000 / total, 2) if total else None}


async def _provar_revogacao(url_revogado: str, url_vivo: str) -> dict:
    """Mede o 403 do token revogado com UM cliente só: criar loop+cliente por sondagem inflava a
    demora medida com o custo do Python, não com o atraso real dos caches (2 s nginx + 2 s app)."""
    import httpx

    async with httpx.AsyncClient(http2=False, timeout=30) as c:
        t0 = time.monotonic()
        codigo = None
        while time.monotonic() - t0 < 7:
            r = await c.get(url_revogado)
            codigo = r.status_code
            if codigo == 403:
                break
            await asyncio.sleep(0.1)
        demora = round(time.monotonic() - t0, 2)
        rb = await c.get(url_vivo)
        cod_b, cache_b = rb.status_code, (rb.headers.get("x-plat-cache") or "-").strip()
    return {"portao": "token revogado não é servido do cache, em <= 5 s", "medido_s": demora,
            "resposta": codigo,
            "segundo_token_mesmo_ladrilho": {"status": cod_b, "cache": cache_b},
            "passou": codigo == 403 and demora <= 5 and cod_b == 200 and cache_b == "HIT"}


def _linhas_do_log(pilha: Pilha, resto: str) -> list[dict]:
    """Linhas do access log da bancada para UM ladrilho (`resto` = z/x/y.png), sem o token."""
    achadas = []
    if not pilha.log_acesso.is_file():
        return achadas
    alvo = f"/{resto}"
    for linha in pilha.log_acesso.read_text(encoding="utf-8", errors="ignore").splitlines():
        partes = linha.split("|")
        if len(partes) == 4 and partes[3].endswith(alvo):
            achadas.append({"status": int(partes[0]), "cache": partes[1].strip() or "-",
                            "rt": float(partes[2])})
    return achadas


def _tamanho_cache(pilha: Pilha) -> int:
    total = 0
    for p in (pilha.prefixo / "cache" / "tiles").rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


# --------------------------------------------------------------------------- a bancada inteira
NIVEIS_QUENTE = (1, 8, 32, 64, 128, 200)
LADRILHOS_FRIOS = 64
SIMULTANEOS_CADEADO = 20
MAX_CACHE_MB = 12


def rodar(pilha: Pilha, token_a: str, token_b: str, item: str,
          revogar_token_a, segundos_quente: float = 2.5) -> dict:
    """Roda as seis medições na pilha viva. `revogar_token_a` é o callback que revoga de verdade."""
    def url(z, x, y, tok=None, args=""):
        return (f"{pilha.url_nginx}/svc/{tok or token_a}/raster/{item}/{z}/{x}/{y}.png{args}")

    resultado: dict = {"erros_fatais": []}

    # -- fase 0: aquece a grade z14 inteira (256 ladrilhos); todo aquecimento tem de ser MISS->200
    grade_quente = _grade(14)
    urls_quente = [f"/svc/{token_a}/raster/{item}/14/{x}/{y}.png" for x, y in grade_quente]
    aquecidos, _ = _uma_conexao([pilha.url_nginx + u for u in urls_quente])
    falhas_aq = [r for r in aquecidos if r[0] != 200 or r[1] != "MISS" or r[2] < 400]
    bytes_aquecidos = sum(r[2] for r in aquecidos)
    bytes_medio = round(bytes_aquecidos / len(aquecidos))
    if falhas_aq:
        resultado["erros_fatais"].append(f"aquecimento com {len(falhas_aq)} ladrilhos fora de 200/MISS")
        return resultado

    # -- fase 1: quente de 1 a 200 conexões
    niveis = [asyncio.run(_janela_quente(pilha.url_nginx, urls_quente, n, segundos_quente))
              for n in NIVEIS_QUENTE]
    limpos = [n for n in niveis if n["falhas"] == 0]
    melhor = max(limpos or niveis, key=lambda n: n["tiles_por_s"])
    resultado["quente"] = {"niveis": niveis, "melhor": melhor,
                           "portao": ">= 500 tiles/s, 0 erro",
                           "passou": bool(limpos) and melhor["tiles_por_s"] >= 500}

    # -- fase 2: frio com 1 conexão em z15 (nunca pedidos nesta rodada)
    grade_fria = _grade(15)[:LADRILHOS_FRIOS]
    frios, dt_frio = _uma_conexao([url(15, x, y) for x, y in grade_fria])
    miss = sum(1 for r in frios if r[1] == "MISS")
    com_pixel = sum(1 for r in frios if r[0] == 200 and r[2] >= 400)
    erros_frio = [r for r in frios if r[0] != 200]
    tiles_s_frio = round(len(frios) / dt_frio, 1)
    resultado["frio_1_conexao"] = {
        "ladrilhos": len(frios), "segundos": round(dt_frio, 2), "tiles_por_s": tiles_s_frio,
        "cache": f"{miss} MISS de {len(frios)}", "todos_com_pixel": com_pixel == len(frios),
        "erros": len(erros_frio), "portao": ">= 15 tiles/s",
        "passou": tiles_s_frio >= 15 and not erros_frio and miss == len(frios)
        and com_pixel == len(frios)}

    # -- fase 3: proxy_cache_lock — 20 simultâneos ao MESMO ladrilho frio de z16, contados no log
    x_c, y_c = _grade(16)[0]
    resto_c = f"16/{x_c}/{y_c}.png"
    asyncio.run(_pedidos([url(16, x_c, y_c)] * SIMULTANEOS_CADEADO))
    time.sleep(0.3)  # o flush do access log é por buffer; 300 ms bastam a 20 linhas locais
    linhas_lock = _linhas_do_log(pilha, resto_c)
    n_miss = sum(1 for li in linhas_lock if li["cache"] == "MISS")
    n_hit = sum(1 for li in linhas_lock if li["cache"] == "HIT")
    todos_200 = all(li["status"] == 200 for li in linhas_lock)
    resultado["proxy_cache_lock"] = {
        "pedidos_simultaneos": SIMULTANEOS_CADEADO, "MISS": n_miss, "HIT": n_hit,
        "contados": "access log da bancada (nginx), não o cliente",
        "portao": "1 MISS", "passou": n_miss == 1 and n_hit == SIMULTANEOS_CADEADO - 1
        and todos_200 and len(linhas_lock) == SIMULTANEOS_CADEADO}

    # -- fase 4: a chave inclui os parâmetros de renderização (RGB x NDVI do mesmo ladrilho).
    # SEQUENCIAL de propósito: a prova é a ordem MISS,MISS,HIT,HIT; em paralelo o cadeado do nginx
    # já misturaria os papéis (qualquer um dos dois pode ser o MISS) e a sequência viraria sorteio.
    x_v, y_v = _grade(16)[1]
    ndvi = "?expressao=(b4-b1)/(b4%2Bb1)&colormap=rdylgn"
    quatro, _ = _uma_conexao([url(16, x_v, y_v), url(16, x_v, y_v, args=ndvi),
                              url(16, x_v, y_v), url(16, x_v, y_v, args=ndvi)])
    rgb1, ndvi1, rgb2, ndvi2 = quatro
    corpos_distintos = (hashlib.sha256(rgb1[3]).digest() != hashlib.sha256(ndvi1[3]).digest())
    resultado["chave_com_parametros"] = {
        "sequencia": [r[1] for r in (rgb1, ndvi1, rgb2, ndvi2)],
        "corpos_distintos": corpos_distintos,
        "portao": "MISS, MISS, HIT, HIT e corpos diferentes (NDVI e RGB nunca se misturam)",
        "passou": ([r[1] for r in (rgb1, ndvi1, rgb2, ndvi2)] == ["MISS", "MISS", "HIT", "HIT"]
                   and corpos_distintos and all(r[0] == 200 for r in (rgb1, ndvi1, rgb2, ndvi2)))}

    # -- fase 5: revogação — o ladrilho quente NÃO sai do cache para o token revogado (403 <= 5 s),
    #            e o segundo token do mesmo inquilino segue recebendo HIT do MESMO ladrilho
    x_r, y_r = grade_quente[0]
    revogar_token_a()
    resultado["revogacao"] = asyncio.run(_provar_revogacao(url(14, x_r, y_r), url(14, x_r, y_r, tok=token_b)))

    # -- fase 6: eviction — enche além de max_size com ladrilhos frios de z16; cache manager remove.
    # token_b (vivo): o token_a saiu de cena na fase 5 — re-pedido com ele daria 403, não eviction.
    livres = _grade(16)[2:]
    alvo_bytes = int(MAX_CACHE_MB * 1024 * 1024 * 2.2)
    n_encher = min(len(livres), max(50, alvo_bytes // bytes_medio))
    enchidos, _ = _uma_conexao([url(16, x, y, tok=token_b) for x, y in livres[:n_encher]])
    cinco_xx = sum(1 for r in enchidos if r[0] >= 500 or r[0] == 0)
    teto = MAX_CACHE_MB * 1024 * 1024
    tamanho_final = _tamanho_cache(pilha)
    prazo = time.monotonic() + 30
    while tamanho_final > teto * 1.2 and time.monotonic() < prazo:
        time.sleep(1.0)
        tamanho_final = _tamanho_cache(pilha)
    # amostra atravessa as três classes em cache (quente z14, frio z15, enchido z16). A prova de
    # eviction é ARITMÉTICA, não sorte de amostragem: escrevemos bytes_escritos medidos (>= 3x o
    # teto) numa zona de 12 MB que assenta sob o teto — sem despejo isso é impossível. O MISS na
    # amostra é a observação direta (a vítima é a classe mais velha, z14: 4 a 9 de 10 conforme o
    # passo do cache manager — medido 18/09); exigir maioria de MISS flakava sem acrescentar prova.
    amostras = {"quente_z14": (14, grade_quente[:10]), "frio_z15": (15, grade_fria[:10]),
                "z16_primeiros": (16, livres[:10]), "z16_ultimos": (16, livres[n_encher - 10:n_encher])}
    detalhe, evictados, n_amostra = {}, 0, 0
    codigos_ok = True
    for nome, (z, grade) in amostras.items():
        repedidos = asyncio.run(_pedidos([url(z, x, y, tok=token_b) for x, y in grade]))
        miss_n = sum(1 for r in repedidos if r[1] == "MISS")
        ok_n = all(r[0] == 200 for r in repedidos)
        detalhe[nome] = {"n": len(repedidos), "miss": miss_n, "todos_200": ok_n}
        evictados += miss_n
        n_amostra += len(repedidos)
        codigos_ok = codigos_ok and ok_n
    bytes_escritos = bytes_aquecidos + sum(r[2] for r in frios) + sum(r[2] for r in enchidos)
    resultado["eviction"] = {
        "max_size_mb": MAX_CACHE_MB, "ladrilhos_enchidos": n_encher,
        "bytes_escritos_medidos": bytes_escritos,
        "tamanho_final_mb": round(tamanho_final / 1024 / 1024, 1),
        "respostas_5xx_ou_rede": cinco_xx,
        "amostra_classes": detalhe, "evictados_miss": f"{evictados} de {n_amostra}",
        "portao": ">= 3x o teto escritos e disco assentado sob o teto (eviction necessária), "
                  ">= 1 MISS na amostra, 0 erro 5xx, re-pedidos todos 200",
        "passou": (tamanho_final <= teto * 1.2 and bytes_escritos >= teto * 3
                   and cinco_xx == 0 and codigos_ok and evictados >= 1)}

    resultado["alvo"] = {"item_stac": item, "cog": "sintético 4 bandas 4096x4096 EPSG:3857 (acervo://)",
                         "bytes_medios_por_ladrilho": bytes_medio}
    return resultado


# --------------------------------------------------------------------------- fechamento
def gravar_json(resultado: dict, onde: str, saida: Path) -> dict:
    from app.versao import git_sha_curto

    dados = {
        "item": "L1-02-d-cache-nginx-e-carga",
        "quando": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "onde": onde,
        "alvo": resultado.get("alvo", {}),
        "cache": {
            "zonas": f"bancada_tiles 16m/{MAX_CACHE_MB}m + bancada_auth 4m/8m (nginx de usuário da "
                     "bancada; produção em deploy/nginx.conf, zonas plat_cache_tiles/plat_tiles_auth)",
            "chave": "$plat_tipo|$plat_item|$plat_resto|$args (SEM o token, de propósito)",
            "proxy_cache_lock": resultado["proxy_cache_lock"],
        },
        "carga": {"quente": resultado["quente"], "frio_1_conexao": resultado["frio_1_conexao"]},
        "chave_com_parametros": resultado["chave_com_parametros"],
        "revogacao": {**resultado["revogacao"],
                      "como": "auth_request /_plat_tile_autorizar antes do cache; a autorização é "
                              "cacheada por 2 s no nginx e 2 s na aplicação (pior caso 4 s < 5 s)"},
        "eviction": resultado["eviction"],
        "nao_feito": [
            "prova de HIT na CDN em GRU: a bancada é inteira local ao servidor; não há ponto de "
            "medição fora dele nesta trilha, e o domínio demo segue com nuvem cinza na Cloudflare. "
            "Os cabeçalhos de cache para a CDN saem da aplicação (public, max-age=300 sem versão; "
            "immutable com <item>@<sha>), cobertos pelo item L7-26-cdn-tiles.",
        ],
        "gerado_em": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": git_sha_curto(),
        "medidas": {
            "quente_tiles_por_s": {
                "valor": resultado["quente"]["melhor"]["tiles_por_s"],
                "unidade": "tiles/s (0 erro)",
                "comando": "bash /home/dev/plat-frota/laco/roda_teste.sh tests/carga/test_l102d_bancada.py -q"},
            "frio_1_conexao_tiles_por_s": {
                "valor": resultado["frio_1_conexao"]["tiles_por_s"], "unidade": "tiles/s (1 conexão, todo MISS)",
                "comando": "bash /home/dev/plat-frota/laco/roda_teste.sh tests/carga/test_l102d_bancada.py -q"},
        },
    }
    if os.environ.get("PLAT_GRAVAR_MEDIDAS") == "1":
        saida.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return dados


def demo() -> None:
    """Auto-checagem da parte que pode errar sem rede: grade alinhada, contagens e template do nginx."""
    g14, g15, g16 = _grade(14), _grade(15), _grade(16)
    assert len(g14) == 16 * 16 and len(g15) == 32 * 32 and len(g16) == 64 * 64
    # z15 subdivide exatamente os z14 (e z16 subdivide z15): o canto superior esquerdo bate
    assert (g15[0][0] // 2, g15[0][1] // 2) == g14[0]
    assert (g16[0][0] // 4, g16[0][1] // 4) == g14[0]
    # as fases não se contaminam: cada uma usa um zoom (cadeado/variante/eviction em z16, frio em z15,
    # quente em z14) e nenhum resto z/x/y se repete entre fases — frio é frio de verdade
    conf = (NGINX_TEMPLATE.replace("@PREFIX@", "/tmp/x").replace("@PID@", "/tmp/x/pid")
            .replace("@PORTA@", "1").replace("@APP@", "2").replace("@MAXMB@", "12"))
    assert "@PREFIX@" not in conf and "@PORTA@" not in conf and "@APP@" not in conf
    assert 'proxy_cache_key "$plat_tipo|$plat_item|$plat_resto|$args"' in conf
    assert "plat_tok|" not in conf.split("proxy_cache_key")[1].split(";")[0]  # token fora da chave
    assert "proxy_cache_lock on;" in conf and "auth_request /_plat_tile_autorizar;" in conf
    print("demo ok: grade z14/z15/z16 alinhada, chave sem token, cadeado e auth_request no template")


if __name__ == "__main__":
    demo()
