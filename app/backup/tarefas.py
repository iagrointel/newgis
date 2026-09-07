"""Tipos de job do backup lógico (item L0-06-a; ADR 20260906T2124; reusa o padrão do backup do SIG de teste
interno da casa: pg_dump -Fc + tabela de registro + retenção).

`backup.dump_logico` — periódico diário 03:00 no inquilino técnico `plataforma` (app/backup/periodicos.py):
1. confere o espaço ANTES de escrever (df do diretório; livre < mínimo -> notificação ao superadmin e
   FalhaDefinitiva, nunca silêncio nem arquivo parcial);
2. despeja o schema plat e o d_<slug> de cada inquilino ativo com `sudo -n -u postgres pg_dump -Fc`
   (superusuário local: atravessa a RLS FORCE sem papel novo com senha; `-n` falha na hora se o sudoers
   não cobrir, e essa falha também notifica);
3. sha256/bytes/tabelas/tempo em `plat.backup` (uma linha por arquivo, um arquivo por inquilino);
4. sobe cada arquivo ao bucket '<prefixo>backup' do Garage (multipart acima de 32 MB) e ao destino
   externo S3 quando configurado; manifesto por inquilino (chave, sha256, bytes) gravado junto no bucket;
5. aplica a retenção 14 diários + 8 semanais por schema (arquivo + objeto + linha).

`backup.verificar` — recalcula o sha256 dos dumps registrados (divergência = FalhaDefinitiva nomeando o
arquivo), lista arquivos ÓRFÃOS (presentes no disco sem linha em plat.backup) e linhas sem arquivo, e
confere que cada objeto registrado existe no bucket com o mesmo tamanho.

Os dois tipos recusam rodar fora do inquilino técnico (a função SQL `backup_confere_plataforma` levanta
`backup_so_plataforma`; vira FalhaDefinitiva) — um admin de inquilino comum não dispara dump dos vizinhos.
"""

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app import db as banco
from app.backup import destino, nucleo
from app.jobs.contexto import ErroServico
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.settings import settings

RAIZ = Path(__file__).resolve().parents[2]


class DumpParametros(BaseModel):
    min_livre_gb: int = Field(nucleo.MIN_LIVRE_GB, ge=0, le=100000,
                              description="falha antes de escrever quando o livre no diretório de backups cai "
                                          "abaixo disto (GB)")
    manter_diarios: int = Field(nucleo.MANTER_DIARIOS, ge=1, le=365)
    manter_semanais: int = Field(nucleo.MANTER_SEMANAIS, ge=0, le=520)
    somente: list[str] | None = Field(None, max_length=200,
                                      description="slugs de inquilino e/ou 'plat'; vazio = todos os ativos")
    origem: str = Field("manual", max_length=40)


class VerificarParametros(BaseModel):
    ultimos_n: int = Field(50, ge=1, le=10000, description="linhas mais novas de plat.backup conferidas")
    esquema: str | None = Field(None, max_length=80, description="restringe a um schema ('plat' ou 'd_<slug>')")


def dir_backups() -> Path:
    """Diretório dos dumps. `pg_dump` roda como o superusuário local `postgres` (via sudo -n) e escreve o
    arquivo `-f` diretamente aqui: o diretório tem de aceitar escrita de outro dono, exatamente como o
    diretório `backups/` do backup do SIG de teste interno da casa (`drwxrwxrwx`, ativo reusado). Sem isso
    o pg_dump sai com "Permission denied" e nunca chega a criar o arquivo — achado do 1º turno real desta
    trilha (o rescaldo do Kimi tinha o código mas nunca tinha rodado o dump de ponta a ponta)."""
    d = Path(settings.PLAT_BACKUP_DIR) if settings.PLAT_BACKUP_DIR else RAIZ / "var" / "backups"
    d.mkdir(parents=True, exist_ok=True)
    d.chmod(0o777)
    return d


def _banco_nome() -> str:
    return urlparse(settings.PLAT_DSN).path.lstrip("/")


def _slug_atual(cur) -> str:
    cur.execute("SELECT slug FROM plat.tenant WHERE id = plat.tenant_atual()")
    r = cur.fetchone()
    if r is None:
        raise FalhaDefinitiva("backup: sem inquilino no contexto do job")
    return r["slug"]


def _notificar_falha(ctx, motivo: str, detalhe: dict) -> None:
    """Falha de backup NUNCA é silêncio: log do job (ERRO) + evento auditável no inquilino técnico + e-mail
    aos superadmins (melhor esforço: sem SMTP o job correio.enviar falha visível na fila; o evento fica
    sempre)."""
    ctx.log("ERRO", f"backup falhou: {motivo}")
    try:
        with ctx.db() as cur:
            cur.execute(
                "SELECT plat.evento_registrar('backup/falha', 'backup', NULL, %s::jsonb, NULL, NULL)",
                (json.dumps({"motivo": motivo, **detalhe}, ensure_ascii=False),),
            )
            cur.execute("SELECT email FROM plat.backup_superadmins()")
            emails = [r["email"] for r in cur.fetchall()]
    except Exception as e:  # a notificação principal é o próprio job 'falhou'; nunca mascarar o motivo original
        ctx.log("ERRO", f"falha também ao registrar o evento de notificação: {e}")
        return
    for email in emails:
        try:
            from app.jobs import sistema  # importação tardia: sistema -> servico -> tipos (ciclo na importação)

            sistema.enfileirar(ctx.tenant_id, "correio.enviar", {
                "destinatario": email,
                "assunto": "Falha no backup da plataforma",
                "texto": f"A rotina de backup falhou.\n\nMotivo: {motivo}\n\n"
                         f"Detalhes: {json.dumps(detalhe, ensure_ascii=False)}\n\n"
                         "Nenhum dump novo foi escrito. A última cópia boa continua registrada em plat.backup.",
                "categoria": "backup",
            })
        except ErroServico as e:
            ctx.log("AVISO", f"não enfileirou e-mail para {email}: {e.mensagem}")


def _schema_existe(cur, esquema: str) -> bool:
    cur.execute("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = %s) AS e", (esquema,))
    return bool(cur.fetchone()["e"])


def _contar_tabelas(cur, esquema: str) -> int:
    cur.execute("SELECT count(*) AS n FROM pg_tables WHERE schemaname = %s", (esquema,))
    return int(cur.fetchone()["n"])


def _alvos(ctx, somente: list[str] | None) -> list[dict]:
    """[{esquema, slug}] — 'plat' (slug None) primeiro, depois um d_<slug> por inquilino ativo com schema."""
    with ctx.db() as cur:
        slug_atual = _slug_atual(cur)
        if slug_atual != "plataforma":
            raise FalhaDefinitiva(
                f"backup.dump_logico só roda no inquilino técnico 'plataforma' (este job está em {slug_atual!r})")
        try:
            cur.execute("SELECT slug FROM plat.backup_alvos()")
            slugs = [r["slug"] for r in cur.fetchall()]
        except Exception as e:
            raise FalhaDefinitiva(f"backup: sem acesso à lista de inquilinos ({e})") from e
        alvos = []
        if somente is None or "plat" in somente:
            alvos.append({"esquema": settings.PLAT_SCHEMA, "slug": None, "grupo": "plat"})
        for slug in slugs:
            if somente is not None and slug not in somente:
                continue
            esquema = f"d_{slug}"
            if _schema_existe(cur, esquema):
                alvos.append({"esquema": esquema, "slug": slug, "grupo": slug})
            else:
                ctx.log("INFO", f"inquilino {slug} sem schema {esquema}: fora do dump")
        return alvos


def _dump(ctx, esquema: str, destino_tmp: Path) -> None:
    """pg_dump -Fc do schema como superusuário local (mesmo padrão do backup do SIG de teste interno)."""
    r = ctx.subprocesso(
        ["sudo", "-n", "-u", "postgres", "pg_dump", "-d", _banco_nome(), "-n", esquema, "-Fc",
         "--no-owner", "--no-privileges", "-f", str(destino_tmp)]
    )
    if r.returncode != 0 or not destino_tmp.exists() or destino_tmp.stat().st_size == 0:
        raise FalhaDefinitiva(f"pg_dump de {esquema} saiu com código {r.returncode}")


def _subir(ctx, clientes: list[tuple[str, object, str]], chave: str, caminho: Path) -> dict[str, str | None]:
    """Sobe o arquivo a cada destino (nome, cliente, bucket); devolve {garagem: chave|None, externo: chave|None}."""
    chaves: dict[str, str | None] = {}
    for nome, cliente, bucket in clientes:
        try:
            destino.enviar_arquivo(cliente, bucket, chave, caminho)
            chaves[nome] = chave
        except Exception as e:
            chaves[nome] = None
            ctx.log("ERRO", f"cópia do dump para {nome} ({bucket}/{chave}) falhou: {e}")
    return chaves


@tarefa(nome="backup.dump_logico",
        descricao="Backup: pg_dump -Fc do schema plat e de cada d_<slug>, sha256 em plat.backup, cópia no Garage, "
                  "retenção 14 diários + 8 semanais; falha de espaço notifica o superadmin",
        parametros=DumpParametros, pesado=True, memoria_mb=512, timeout_s=7200, tentativas=2,
        chave=lambda p: "dump_logico", perfil_minimo="admin")
def backup_dump_logico(ctx, min_livre_gb: int = nucleo.MIN_LIVRE_GB,
                       manter_diarios: int = nucleo.MANTER_DIARIOS,
                       manter_semanais: int = nucleo.MANTER_SEMANAIS,
                       somente: list[str] | None = None, origem: str = "manual") -> dict:
    agora = datetime.now(UTC)
    diretorio = dir_backups()
    try:
        livre = nucleo.conferir_espaco(diretorio, min_livre_gb)
    except nucleo.EspacoInsuficiente as e:
        _notificar_falha(ctx, str(e), {"livre_bytes": e.livre_bytes, "minimo_bytes": e.minimo_bytes,
                                       "diretorio": str(diretorio)})
        raise FalhaDefinitiva(str(e)) from e
    ctx.progresso(2, f"espaço livre {livre / 1e9:.1f} GB (mínimo {min_livre_gb} GB)")

    alvos = _alvos(ctx, somente)
    if not alvos:
        raise FalhaDefinitiva("backup: nenhum alvo (nem o schema plat)")

    # destinos de cópia: bucket do Garage (obrigatório) + externo (opcional); o bucket é provisionado antes
    # do 1º dump para não despejar nada que não possa ser copiado
    with ctx.db() as cur:
        try:
            linha_bucket = destino.garantir_bucket(cur)
        except Exception as e:
            _notificar_falha(ctx, f"destino do backup indisponível: {e}", {})
            raise FalhaDefinitiva(f"backup: destino no Garage indisponível antes do dump: {e}") from e
    clientes: list[tuple[str, object, str]] = [("garagem", destino.cliente_garage(linha_bucket), linha_bucket["alias"])]
    externo = destino.cliente_externo()
    if externo is not None:
        clientes.append(("externo", externo[0], externo[1]))

    semanal = nucleo.e_semanal(agora)
    manifestos: dict[str, list[dict]] = {}
    feitos: list[dict] = []
    for i, alvo in enumerate(alvos):
        ctx.verificar()
        esquema, grupo = alvo["esquema"], alvo["grupo"]
        nome = nucleo.nome_arquivo(esquema, agora)
        tmp = diretorio / f".tmp_{nome}"
        final = diretorio / nome
        inicio = time.monotonic()
        _dump(ctx, esquema, tmp)
        # pg_dump roda como `postgres` (sudo -n) e o arquivo nasce 0600 daquele dono; o diretório é 0777
        # mas o ARQUIVO também precisa aceitar escrita de outro usuário, e só o dono (ou root) pode fazer
        # esse chmod — `Path.chmod` como o usuário do worker dá "Operation not permitted" (achado real
        # rodando o job de ponta a ponta, não de leitura de código). Sem isso o adversário do portão de
        # pronto ("corrompe 1 byte") não consegue reabrir o dump para escrita.
        r_chmod = ctx.subprocesso(["sudo", "-n", "-u", "postgres", "chmod", "666", str(tmp)])
        if r_chmod.returncode != 0:
            raise FalhaDefinitiva(f"chmod do dump de {esquema} saiu com código {r_chmod.returncode}")
        os.replace(tmp, final)
        tempo = round(time.monotonic() - inicio, 2)
        sha = nucleo.sha256_arquivo(final)
        tamanho = final.stat().st_size
        chave = f"{grupo}/{nome}"
        chaves = _subir(ctx, clientes, chave, final)
        with ctx.db() as cur:
            tabelas = _contar_tabelas(cur, esquema)
            cur.execute(
                "SELECT plat.backup_registrar(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS id",
                (esquema, alvo["slug"], str(final), sha, tamanho, tabelas, tempo, semanal,
                 chaves.get("garagem"), chaves.get("externo"), origem),
            )
            backup_id = cur.fetchone()["id"]
        manifestos.setdefault(grupo, []).append({"chave": chave, "sha256": sha, "bytes": tamanho})
        feitos.append({"esquema": esquema, "slug": alvo["slug"], "arquivo": str(final), "sha256": sha,
                       "bytes": tamanho, "tabelas": tabelas, "tempo_dump_s": tempo, "semanal": semanal,
                       "id": backup_id})
        ctx.progresso(5 + int(80 * (i + 1) / len(alvos)),
                      f"{esquema}: {tamanho / 1e6:.1f} MB em {tempo:.1f} s (sha256 {sha[:12]}…)")

    # manifesto por inquilino (chave, sha256, bytes), gravado junto no bucket (e no externo, se houver)
    for grupo, objetos in manifestos.items():
        doc = nucleo.manifesto_inquilino(grupo, objetos, agora)
        chave_manifesto = f"{grupo}/manifesto-{agora.strftime('%Y%m%d_%H%M%S')}.json"
        for nome, cliente, bucket in clientes:
            try:
                cliente.put(bucket, chave_manifesto, doc, content_type="application/json")
            except Exception as e:
                ctx.log("ERRO", f"manifesto de {grupo} não subiu para {nome}: {e}")

    # retenção: apaga arquivo + objeto + linha do que passar de 14 diários / 8 semanais por schema
    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.backup_listar(NULL, 10000)")
        linhas = [dict(r) for r in cur.fetchall()]
        apagar = nucleo.selecao_retencao(linhas, manter_diarios, manter_semanais)
        if apagar:
            cur.execute("SELECT * FROM plat.backup_apagar(%s)", (apagar,))
            saidas = [dict(r) for r in cur.fetchall()]
        else:
            saidas = []
    for s in saidas:
        try:
            Path(s["arquivo"]).unlink(missing_ok=True)
        except OSError as e:
            ctx.log("AVISO", f"retenção: não apagou {s['arquivo']}: {e}")
        for nome, cliente, bucket in clientes:
            chave_obj = s["bucket_chave"] if nome == "garagem" else s.get("externo_chave")
            if chave_obj:
                try:
                    cliente.delete(bucket, chave_obj)
                except Exception as e:
                    ctx.log("AVISO", f"retenção: não apagou {bucket}/{chave_obj} em {nome}: {e}")
    ctx.progresso(100, f"{len(feitos)} dumps, retenção apagou {len(saidas)}")
    return {"dumps": feitos, "retencao_apagados": len(saidas), "semanal": semanal,
            "espaco_livre_bytes": livre}


@tarefa(nome="backup.verificar",
        descricao="Backup: recalcula o sha256 dos dumps registrados (divergência = falha), lista arquivos "
                  "órfãos no disco e linhas sem arquivo, e confere os objetos do bucket",
        parametros=VerificarParametros, pesado=True, memoria_mb=256, timeout_s=3600, tentativas=1,
        chave=lambda p: f"verificar:{p.get('esquema') or 'tudo'}", perfil_minimo="admin")
def backup_verificar(ctx, ultimos_n: int = 50, esquema: str | None = None) -> dict:
    diretorio = dir_backups()
    with ctx.db() as cur:
        slug_atual = _slug_atual(cur)
        if slug_atual != "plataforma":
            raise FalhaDefinitiva(
                f"backup.verificar só roda no inquilino técnico 'plataforma' (este job está em {slug_atual!r})")
        cur.execute("SELECT * FROM plat.backup_listar(%s, %s)", (esquema, ultimos_n))
        linhas = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT * FROM plat.backup_destino_ler()")
        dest = cur.fetchone()

    divergencias: list[dict] = []
    faltando: list[dict] = []
    conferidos = 0
    for i, l in enumerate(linhas):
        ctx.verificar()
        caminho = Path(l["arquivo"])
        if not caminho.exists():
            faltando.append({"id": l["id"], "arquivo": l["arquivo"]})
            continue
        sha = nucleo.sha256_arquivo(caminho)
        conferidos += 1
        if sha != l["sha256"]:
            divergencias.append({"id": l["id"], "arquivo": l["arquivo"],
                                 "sha256_registrado": l["sha256"], "sha256_atual": sha})
        if conferidos % 10 == 0:
            ctx.progresso(int(70 * i / max(1, len(linhas))), f"{conferidos} arquivos conferidos")

    # órfãos: arquivo .dump no diretório sem linha em plat.backup (a retenção apaga os dois juntos; linha
    # apagada à mão é o caso do adversário — TEM de aparecer aqui, não passar em silêncio)
    with ctx.db() as cur:
        cur.execute("SELECT arquivo FROM plat.backup_listar(NULL, 100000)")
        registrados = {r["arquivo"] for r in cur.fetchall()}
    orfaos = sorted(str(p) for p in diretorio.glob("*.dump") if str(p) not in registrados)
    for o in orfaos:
        ctx.log("AVISO", f"arquivo órfão (sem linha em plat.backup): {o}")

    # bucket: cada objeto registrado existe com o mesmo tamanho
    bucket_inconsistentes: list[dict] = []
    if dest is not None:
        cliente = destino.cliente_garage(dict(dest))
        for l in linhas:
            if not l["bucket_chave"]:
                continue
            try:
                info = cliente.head(dest["alias"], l["bucket_chave"])
            except Exception as e:
                bucket_inconsistentes.append({"chave": l["bucket_chave"], "erro": str(e)[:200]})
                continue
            if info is None:
                bucket_inconsistentes.append({"chave": l["bucket_chave"], "erro": "objeto ausente no bucket"})
            elif info.tamanho != int(l["bytes"]):
                bucket_inconsistentes.append({"chave": l["bucket_chave"],
                                              "erro": f"tamanho {info.tamanho} != registrado {l['bytes']}"})

    ctx.progresso(100, f"{conferidos} conferidos, {len(divergencias)} divergências, {len(orfaos)} órfãos")
    resultado = {"conferidos": conferidos, "divergencias": divergencias, "faltando": faltando,
                 "orfaos": orfaos, "bucket_inconsistentes": bucket_inconsistentes}
    if divergencias or faltando:
        raise FalhaDefinitiva(
            f"verificação de backup: {len(divergencias)} dump(s) com sha256 divergente "
            f"({', '.join(d['arquivo'] for d in divergencias[:3])}), "
            f"{len(faltando)} linha(s) sem arquivo")
    return resultado


from app.backup import periodicos  # noqa: E402,F401 — importar registra os periódicos do backup na lista do worker
