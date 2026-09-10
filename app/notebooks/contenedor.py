"""Ciclo de vida do contêiner de notebook por inquilino (L2-16-b), tudo pelo CLI do docker
(nenhum socket docker montado em contêiner algum).

Regras do portão que vivem aqui: partida em <= 20 s (PARTIDA_S, medido), limite de RAM
(--memory e --memory-swap iguais: passar do teto mata o processo, teste com exit 137),
rede interna sem saída, --security-opt no-new-privileges, volume de trabalho próprio por
slug, pids-limit para conter bomba de fork. Único segredo injetado: token de serviço do
usuário (variável PLAT_TOKEN), de leitura, validade curta; ao subir um novo contêiner para
o mesmo inquilino, os tokens de notebook anteriores são revogados no banco.

Estado de uso (ociosidade) mora em plat.notebook_uso; o ceifador lê com a role worker
(PLAT_DSN_WORKER, autocommit e CursorSchemaAmbiente) igual ao app.jobs.worker, porque roda
fora de pedido HTTP.
"""

import secrets
import subprocess
import threading
import time
import urllib.request

import psycopg2

from app import db
from app.auth.sessao import sha256_hex
from app.erros import ErroAPI
from app.notebooks import config, gateway

_TRAVA = threading.Lock()  # um levantar por processo (a fila de ativos é global da trilha)


def _docker(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def _ativos_brutos(cfg: dict) -> list[str]:
    r = _docker("ps", "--filter", f"label=plat.notebook.inst={config.sufixo()}",
                "--format", "{{.Names}}")
    _ = cfg
    return [n for n in r.stdout.splitlines() if n.strip()]


def _ip(nome: str, cfg: dict) -> str:
    r = _docker(
        "inspect", "-f",
        f"{{{{(index .NetworkSettings.Networks \"{cfg['rede']}\" ).IPAddress}}}}", nome,
    )
    return r.stdout.strip()


def _pronto(ip: str, base: str, limite_s: int = 5) -> bool:
    """O Jupyter responde /api/status atrás do base_url (sem sessão: só o 200 do status)."""
    url = f"http://{ip}:8888{base}api/status"
    try:
        with urllib.request.urlopen(url, timeout=limite_s) as resp:
            return resp.status == 200
    except Exception:
        return False


def _subir_token(ctx: db.Contexto, slug: str) -> tuple[int, str]:
    """Cria token de serviço de leitura para o usuário; revoga antes os de notebook do mesmo
    usuário (um vivo por inquilino; quota de tokens nunca vira efeito colateral do notebook)."""
    cfg = config.obter()
    nome = f"notebook {slug}"
    valor = "plat_" + secrets.token_urlsafe(32)
    with db.db(ctx) as cur:
        cur.execute(
            "UPDATE plat.token_servico SET revogado_em = now() "
            "WHERE usuario_id = %s AND nome = %s AND revogado_em IS NULL",
            (ctx.usuario_id, nome),
        )
        cur.execute(
            """
            INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo,
                                           escopos, restricao, expira_em)
            VALUES (%s, %s, %s, %s, %s, %s, '{}'::jsonb, now() + make_interval(days => %s))
            RETURNING id""",
            (ctx.tenant_id, ctx.usuario_id, nome, sha256_hex(valor), valor[:12],
             cfg["escopos_token"], cfg["validade_token_dias"]),
        )
        return cur.fetchone()["id"], valor


def _registrar_uso(tenant_id: int, slug: str, token_id: int | None) -> None:
    with db.db(db.Contexto(tenant_id, 0, "notebooks")) as cur:
        cur.execute(
            """
            INSERT INTO plat.notebook_uso(tenant_id, slug, token_id, levantado_em, ultimo_uso)
            VALUES (%s, %s, %s, now(), now())
            ON CONFLICT (tenant_id) DO UPDATE
              SET slug = EXCLUDED.slug, token_id = EXCLUDED.token_id,
                  levantado_em = now(), ultimo_uso = now()""",
            (tenant_id, slug, token_id),
        )


def levantar(slug: str, ctx: db.Contexto) -> dict:
    """Sobe (ou reutiliza) o contêiner do slug e devolve {base, contenedor, token_id, s}."""
    cfg = config.obter()
    gateway.levantar()  # garante rede + vigia + bomba (idempotente)
    nome = config.nome_contenedor(slug)
    base = config.base_url(slug)
    with _TRAVA:
        r = _docker("inspect", "-f", "{{.State.Running}}", nome)
        if r.returncode == 0 and r.stdout.strip() == "true":
            tok = _docker("inspect", "-f", "{{index .Config.Labels \"plat.notebook.token\"}}", nome)
            token_id = int(tok.stdout.strip()) if tok.stdout.strip().isdigit() else None
            _registrar_uso(ctx.tenant_id, slug, token_id)
            return {"base": base, "contenedor": nome, "token_id": token_id, "s": 0.0,
                    "reusado": True}
        _docker("rm", "-f", nome)

        fila_inicio = time.monotonic()
        while len(_ativos_brutos(cfg)) >= cfg["ativos_max"]:
            if time.monotonic() - fila_inicio > cfg["espera_fila_s"]:
                raise ErroAPI(429, "notebooks_ocupados",
                              "limite de notebooks ativos desta instalação atingido; tente de novo em instantes",
                              {"ativos_max": cfg["ativos_max"], "espera_s": cfg["espera_fila_s"]})
            time.sleep(1.0)

        token_id, valor = _subir_token(ctx, slug)

        _docker("volume", "create", config.volume(slug))
        inicio = time.monotonic()
        r = _docker(
            "run", "-d",
            "--name", nome,
            "--network", cfg["rede"],
            "--label", "plat.notebook.inst=" + config.sufixo(),
            "--label", f"plat.notebook.slug={slug}",
            "--label", f"plat.notebook.tenant={ctx.tenant_id}",
            "--label", f"plat.notebook.token={token_id}",
            "--cpus", cfg["cpus"],
            "--memory", cfg["memoria"],
            "--memory-swap", cfg["memoria"],  # sem troca: estourou RAM, o processo morre
            "--pids-limit", "512",
            "--security-opt", "no-new-privileges",
            "-v", f"{config.volume(slug)}:/home/jovyan/trabalho",
            "-e", f"PLAT_TOKEN={valor}",
            "-e", f"PLAT_URL_API={gateway.levantar()}",
            "-e", f"PLAT_INQUILINO={slug}",
            cfg["imagem"],
            "--ServerApp.base_url=" + base,
            timeout=180,
        )
        if r.returncode != 0:
            raise ErroAPI(503, "notebook_nao_subiu", "contêiner do notebook não iniciou",
                          r.stderr.strip()[-400:])

        fim = inicio + cfg["partida_s"]
        while time.monotonic() < fim:
            if _pronto(_ip(nome, cfg), base):
                _registrar_uso(ctx.tenant_id, slug, token_id)
                return {"base": base, "contenedor": nome, "token_id": token_id,
                        "s": round(time.monotonic() - inicio, 2), "reusado": False}
            time.sleep(0.3)
        saida = _docker("logs", "--tail", "20", nome).stdout
        parar(slug, ctx)
        raise ErroAPI(503, "notebook_lento",
                      f"notebook não ficou pronto em {cfg['partida_s']:.0f} s", saida[-400:])


def _apagar(nome: str) -> None:
    _docker("rm", "-f", nome, timeout=120)


def tocar(ctx: db.Contexto) -> None:
    """Marca uso (o ceifador mede ociosidade pela última passagem pelo proxy)."""
    try:
        with db.db(db.Contexto(ctx.tenant_id, 0, "notebooks")) as cur:
            cur.execute("UPDATE plat.notebook_uso SET ultimo_uso = now() WHERE tenant_id = %s",
                        (ctx.tenant_id,))
    except Exception:
        pass  # tocar é otimização de ociosidade; nunca derruba o pedido


def estado(slug: str) -> dict | None:
    cfg = config.obter()
    nome = config.nome_contenedor(slug)
    r = _docker("inspect", "-f",
                "{{.State.Running}}\t{{.State.StartedAt}}\t{{.State.OOMKilled}}\t{{.State.ExitCode}}", nome)
    if r.returncode != 0:
        return None
    running, inicio, oom, codigo = r.stdout.strip().split("\t")
    return {"slug": slug, "contenedor": nome, "rodando": running == "true",
            "inicio": inicio, "oom_killed": oom == "true", "exit_code": int(codigo),
            "ip": _ip(nome, cfg)}


def parar(slug: str, ctx: db.Contexto) -> None:
    """Encerra o contêiner do slug, revoga o token anotado e apaga a linha de uso."""
    _apagar(config.nome_contenedor(slug))
    try:
        with db.db(db.Contexto(ctx.tenant_id, 0, "notebooks")) as cur:
            cur.execute(
                """
                UPDATE plat.token_servico SET revogado_em = now()
                WHERE id = (SELECT token_id FROM plat.notebook_uso WHERE tenant_id = %s)
                  AND revogado_em IS NULL""",
                (ctx.tenant_id,),
            )
            cur.execute("DELETE FROM plat.notebook_uso WHERE tenant_id = %s", (ctx.tenant_id,))
    except Exception:
        pass
    try:
        _docker("volume", "rm", config.volume(slug))
    except Exception:
        pass


def ativos() -> list[dict]:
    """Notebooks vivos nesta instalação (rótulo por trilha), com slug e inquilino."""
    cfg = config.obter()
    r = _docker("ps", "--filter", f"label=plat.notebook.inst={config.sufixo()}",
                "--format", "{{.Names}}\t{{.Label \"plat.notebook.slug\"}}\t"
                            "{{.Label \"plat.notebook.tenant\"}}")
    saida = []
    for linha in r.stdout.splitlines():
        pedacos = linha.split("\t")
        if not pedacos or not pedacos[0]:
            continue
        nome = pedacos[0]
        slug = pedacos[1] if len(pedacos) > 1 else ""
        tenant = pedacos[2] if len(pedacos) > 2 else ""
        saida.append({"contenedor": nome, "slug": slug,
                      "tenant_id": int(tenant) if tenant.isdigit() else 0,
                      "base": config.base_url(slug or nome.removeprefix("plat-nb-")),
                      "ip": _ip(nome, cfg)})
    return saida


def _con_worker():
    from app.schema_ambiente import CursorSchemaAmbiente
    from app.settings import settings
    if not settings.PLAT_DSN_WORKER:
        raise RuntimeError("PLAT_DSN_WORKER ausente: ceifador do notebook exige a role worker")
    con = psycopg2.connect(settings.PLAT_DSN_WORKER, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = True
    return con


def ceifar() -> list[str]:
    """Encerra contêineres ociosos além de OCIOSIDADE_MIN ou vivos além de TETO_HORAS.
    Lê plat.notebook_uso com a role worker (fora de pedido HTTP, igual ao app.jobs.worker)."""
    cfg = config.obter()
    vivo = _ativos_brutos(cfg)
    ceifados: list[str] = []
    if not vivo:
        return ceifados
    con = _con_worker()
    try:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT tenant_id, slug,
                       EXTRACT(EPOCH FROM (now() - ultimo_uso)) / 60.0 AS ocioso_min,
                       EXTRACT(EPOCH FROM (now() - levantado_em)) / 3600.0 AS idade_h
                FROM plat.notebook_uso"""
            )
            linhas = cur.fetchall()
    finally:
        con.close()
    for linha in linhas:
        slug = linha["slug"]
        nome = config.nome_contenedor(slug)
        if nome not in vivo:
            continue
        ocioso_min = linha["ocioso_min"]
        idade_h = linha["idade_h"]
        if (ocioso_min is not None and ocioso_min >= cfg["ociosidade_min"]) or \
           (idade_h is not None and idade_h >= cfg["teto_horas"]):
            parar(slug, db.Contexto(int(linha["tenant_id"]), 0, "notebooks"))
            ceifados.append(slug)
    # linhas de uso sem contêiner vivo: limpeza (mesma role worker)
    con = _con_worker()
    try:
        with con.cursor() as cur:
            cur.execute(
                "DELETE FROM plat.notebook_uso WHERE slug <> ALL(%s)",
                ([n.removeprefix("plat-nb-") for n in vivo],),
            )
    finally:
        con.close()
    return ceifados
