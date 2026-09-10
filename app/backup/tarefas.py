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

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.backup import destino, drill, nucleo
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
    for i, linha in enumerate(linhas):
        ctx.verificar()
        caminho = Path(linha["arquivo"])
        if not caminho.exists():
            faltando.append({"id": linha["id"], "arquivo": linha["arquivo"]})
            continue
        sha = nucleo.sha256_arquivo(caminho)
        conferidos += 1
        if sha != linha["sha256"]:
            divergencias.append({"id": linha["id"], "arquivo": linha["arquivo"],
                                 "sha256_registrado": linha["sha256"], "sha256_atual": sha})
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
        for linha in linhas:
            if not linha["bucket_chave"]:
                continue
            try:
                info = cliente.head(dest["alias"], linha["bucket_chave"])
            except Exception as e:
                bucket_inconsistentes.append({"chave": linha["bucket_chave"], "erro": str(e)[:200]})
                continue
            if info is None:
                bucket_inconsistentes.append({"chave": linha["bucket_chave"], "erro": "objeto ausente no bucket"})
            elif info.tamanho != int(linha["bytes"]):
                bucket_inconsistentes.append({"chave": linha["bucket_chave"],
                                              "erro": f"tamanho {info.tamanho} != registrado {linha['bytes']}"})

    ctx.progresso(100, f"{conferidos} conferidos, {len(divergencias)} divergências, {len(orfaos)} órfãos")
    resultado = {"conferidos": conferidos, "divergencias": divergencias, "faltando": faltando,
                 "orfaos": orfaos, "bucket_inconsistentes": bucket_inconsistentes}
    if divergencias or faltando:
        raise FalhaDefinitiva(
            f"verificação de backup: {len(divergencias)} dump(s) com sha256 divergente "
            f"({', '.join(d['arquivo'] for d in divergencias[:3])}), "
            f"{len(faltando)} linha(s) sem arquivo")
    return resultado


class DrillParametros(BaseModel):
    somente: list[str] | None = Field(None, max_length=200,
                                      description="slugs de inquilino e/ou 'plat'; vazio = todos os esquemas "
                                                  "com dump registrado")
    objetos_por_inquilino: int = Field(drill.OBJETOS_POR_INQUILINO, ge=0, le=50,
                                       description="objetos do bucket conferidos contra o manifesto, por inquilino")
    origem: str = Field("manual", max_length=40)


def _psql(ctx, banco: str, sql: str) -> list[list[str]]:
    """Consulta como o superusuário local (mesmo caminho do pg_dump): a contagem tem de ser a FÍSICA da
    tabela, e a RLS FORCE mostraria ao papel da aplicação só as linhas do inquilino do job."""
    r = ctx.subprocesso(["sudo", "-n", "-u", "postgres", "psql", "-d", banco, "-At", "-F", "|", "-c", sql])
    if r.returncode != 0:
        raise FalhaDefinitiva(f"psql em {banco} saiu com código {r.returncode}")
    return [linha.split("|") for linha in (r.stdout or "").splitlines() if linha.strip()]


def _tabelas_com_tenant(ctx, banco: str, esquema: str) -> list[str]:
    linhas = _psql(ctx, banco, (
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped "
        f"WHERE c.relkind = 'r' AND n.nspname = '{esquema}' ORDER BY 1"))
    return [linha[0] for linha in linhas]


def _contar(ctx, banco: str, esquema: str, tabelas: list[str]) -> dict[str, int]:
    """Um psql só para o schema inteiro (uma chamada por N tabelas, não N chamadas)."""
    if not tabelas:
        return {}
    sql = " UNION ALL ".join(
        f"SELECT '{t}' AS tabela, count(*) AS n FROM \"{esquema}\".\"{t}\"" for t in tabelas)
    return {linha[0]: int(linha[1]) for linha in _psql(ctx, banco, sql)}


def _conferir_objetos(ctx, cliente, bucket: str, grupo: str, registradas: dict[str, str],
                      limite: int) -> tuple[int, list[dict]]:
    """sha256 de até `limite` objetos do manifesto mais novo do inquilino contra o próprio manifesto.
    Objeto que já saiu pela retenção (sem linha em plat.backup) é pulado, não vira divergência."""
    if limite <= 0:
        return 0, []
    chaves = sorted(o["chave"] for o in cliente.listar(bucket, prefixo=f"{grupo}/manifesto-"))
    if not chaves:
        return 0, [{"grupo": grupo, "motivo": "sem manifesto no bucket"}]
    doc = json.loads(cliente.get(bucket, chaves[-1]))
    conferidos, divergencias = 0, []
    for objeto in drill.escolher_objetos(doc.get("objetos") or [], limite):
        chave = objeto["chave"]
        try:
            dados = cliente.get(bucket, chave)
        except Exception as e:
            if chave not in registradas:
                ctx.log("INFO", f"objeto {chave} já saiu pela retenção: fora do ensaio")
                continue
            divergencias.append({"chave": chave, "motivo": f"objeto do manifesto ilegível no bucket: {e}"[:300]})
            continue
        sha = hashlib.sha256(dados).hexdigest()
        conferidos += 1
        if sha != objeto["sha256"]:
            divergencias.append({"chave": chave, "motivo": "sha256 do objeto difere do manifesto",
                                 "sha256_manifesto": objeto["sha256"], "sha256_objeto": sha})
    return conferidos, divergencias


def _ultimos_dumps(ctx, somente: list[str] | None) -> list[dict]:
    """A linha mais nova de plat.backup por esquema (o ensaio restaura o ÚLTIMO dump, que é o que seria
    usado numa restauração de verdade)."""
    with ctx.db() as cur:
        slug_atual = _slug_atual(cur)
        if slug_atual != "plataforma":
            raise FalhaDefinitiva(
                f"backup.restore_drill só roda no inquilino técnico 'plataforma' (este job está em {slug_atual!r})")
        cur.execute("SELECT * FROM plat.backup_listar(NULL, 10000)")
        linhas = [dict(r) for r in cur.fetchall()]
    escolhidas: dict[str, dict] = {}
    for linha in linhas:  # backup_listar já vem das mais novas para as mais velhas
        escolhidas.setdefault(linha["esquema"], linha)
    alvos = []
    for _esquema, linha in sorted(escolhidas.items()):
        grupo = linha["inquilino_slug"] or "plat"
        if somente is not None and grupo not in somente:
            continue
        alvos.append(linha)
    return alvos


@tarefa(nome="backup.restore_drill",
        descricao="Backup: restaura o último dump de cada esquema num banco temporário, compara COUNT(*) de "
                  "todas as tabelas com tenant_id contra a produção, confere o sha256 de objetos do bucket "
                  "contra o manifesto e grava o ensaio em plat.backup_drill",
        parametros=DrillParametros, pesado=True, memoria_mb=512, timeout_s=7200, tentativas=1,
        chave=lambda p: "restore_drill", perfil_minimo="admin")
def backup_restore_drill(ctx, somente: list[str] | None = None,
                         objetos_por_inquilino: int = drill.OBJETOS_POR_INQUILINO,
                         origem: str = "manual") -> dict:
    alvos = _ultimos_dumps(ctx, somente)
    if not alvos:
        raise FalhaDefinitiva("ensaio de restauração: nenhum dump registrado em plat.backup para restaurar")
    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.backup_destino_ler()")
        dest = cur.fetchone()
        cur.execute("SELECT arquivo, bucket_chave FROM plat.backup_listar(NULL, 100000)")
        registradas = {r["bucket_chave"]: r["arquivo"] for r in cur.fetchall() if r["bucket_chave"]}
    cliente = destino.cliente_garage(dict(dest)) if dest is not None else None
    banco = _banco_nome()

    ensaios: list[dict] = []
    for i, linha in enumerate(alvos):
        ctx.verificar()
        ensaios.append(_ensaiar(ctx, linha, banco, cliente, dest, registradas, objetos_por_inquilino, origem))
        ctx.progresso(5 + int(90 * (i + 1) / len(alvos)),
                      f"{linha['esquema']}: {ensaios[-1]['tabelas']} tabelas, "
                      f"{len(ensaios[-1]['divergencias'])} divergências")

    ruins = [e for e in ensaios if not e["ok"]]
    resultado = {"ensaios": ensaios, "esquemas": len(ensaios),
                 "divergencias": sum(len(e["divergencias"]) for e in ensaios),
                 "duracao_drill_s": round(sum(e["duracao_drill_s"] for e in ensaios), 2)}
    if ruins:
        motivo = "; ".join(f"{e['esquema']}: {e['mensagem']}" for e in ruins)[:900]
        _notificar_falha(ctx, f"ensaio de restauração acusou divergência — {motivo}",
                         {"esquemas": [e["esquema"] for e in ruins],
                          "divergencias": [d for e in ruins for d in e["divergencias"]][:20]})
        raise FalhaDefinitiva(f"ensaio de restauração: {motivo}")
    ctx.progresso(100, f"{len(ensaios)} esquema(s) restaurado(s) sem divergência")
    return resultado


def _ensaiar(ctx, linha: dict, banco: str, cliente, dest, registradas: dict[str, str],
             objetos_por_inquilino: int, origem: str) -> dict:
    """Um esquema: restaura, compara, confere objetos, grava a linha de plat.backup_drill e devolve o resumo.
    O banco temporário é derrubado sempre (inclusive quando a restauração falha)."""
    inicio = time.monotonic()
    esquema, grupo = linha["esquema"], linha["inquilino_slug"] or "plat"
    arquivo = Path(linha["arquivo"])
    temporario = _banco_ensaio(ctx, banco)
    divergencias: list[dict] = []
    posteriores: list[dict] = []
    contagens: dict[str, int] = {}
    tabelas: list[str] = []
    conferidos = 0
    try:
        if not arquivo.exists():
            divergencias.append({"arquivo": str(arquivo), "motivo": "dump registrado não está no disco"})
        else:
            ctx.log("INFO", f"ensaio de {esquema}: conferindo o sha256 de {arquivo.name}")
            sha = nucleo.sha256_arquivo(arquivo)
            if sha != linha["sha256"]:
                divergencias.append({"arquivo": str(arquivo),
                                     "motivo": "sha256 do dump difere do registrado em plat.backup",
                                     "sha256_registrado": linha["sha256"], "sha256_atual": sha})
            else:
                ctx.log("INFO", f"ensaio de {esquema}: restaurando em {temporario}")
                tabelas, contagens, restauradas = _restaurar_e_contar(ctx, esquema, arquivo, banco, temporario)
                ctx.log("INFO", f"ensaio de {esquema}: {len(tabelas)} tabela(s) contada(s) nos dois lados")
                comparadas = [{"tabela": t, "restaurado": restauradas.get(t), "producao": contagens[t]}
                              for t in tabelas]
                divergencias, posteriores = drill.classificar_contagens(comparadas)
                contagens = restauradas
        if cliente is not None and not divergencias:
            ctx.log("INFO", f"ensaio de {esquema}: conferindo objetos do bucket contra o manifesto")
            conferidos, div_objetos = _conferir_objetos(ctx, cliente, dest["alias"], grupo, registradas,
                                                        objetos_por_inquilino)
            divergencias.extend(div_objetos)
    finally:
        ctx.log("INFO", f"ensaio de {esquema}: derrubando o schema restaurado em {temporario}")
        _largar_schema(ctx, temporario, banco, esquema)
    duracao = round(time.monotonic() - inicio, 2)
    ok = not divergencias
    mensagem = ("sem divergência" if ok else
                "; ".join(f"{d.get('tabela') or d.get('chave') or d.get('arquivo')}: {d['motivo']}"
                          for d in divergencias)[:900])
    with ctx.db() as cur:
        cur.execute(
            "SELECT plat.backup_drill_registrar(%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, "
            "%s, %s) AS id",
            (linha["id"], esquema, linha["inquilino_slug"], str(arquivo), linha["criado_em"], len(tabelas),
             sum(contagens.values()), json.dumps(divergencias, ensure_ascii=False),
             json.dumps(posteriores, ensure_ascii=False), conferidos, ok, mensagem, duracao, origem))
        drill_id = cur.fetchone()["id"]
    return {"id": drill_id, "esquema": esquema, "inquilino_slug": linha["inquilino_slug"],
            "backup_id": linha["id"], "arquivo": str(arquivo), "tabelas": len(tabelas),
            "linhas": sum(contagens.values()), "divergencias": divergencias, "posteriores": posteriores,
            "objetos_conferidos": conferidos, "ok": ok, "mensagem": mensagem, "duracao_drill_s": duracao}


def _banco_ensaio(ctx, banco: str) -> str:
    """Banco de ensaio da instalação (um só, com as extensões que a restauração exige), criado na primeira
    vez. Nunca é o banco da plataforma: o nome vem de `drill.nome_banco_temporario` e é conferido antes de
    qualquer DROP."""
    nome = drill.nome_banco_temporario(settings.PLAT_SCHEMA)
    if nome == banco:
        raise FalhaDefinitiva(f"ensaio de restauração: o banco de ensaio não pode ser o da plataforma ({nome})")
    existe = _psql(ctx, banco, f"SELECT 1 FROM pg_database WHERE datname = '{nome}'")
    if not existe:
        r = ctx.subprocesso(["sudo", "-n", "-u", "postgres", "createdb", nome])
        if r.returncode != 0:
            raise FalhaDefinitiva(f"ensaio de restauração: createdb {nome} saiu com código {r.returncode}")
    for ext in drill.extensoes_do_ensaio():
        ctx.subprocesso(["sudo", "-n", "-u", "postgres", "psql", "-d", nome, "-q", "-c",
                         f"CREATE EXTENSION IF NOT EXISTS {ext}"])
    return nome


def _largar_schema(ctx, banco_ensaio: str, banco: str, esquema: str) -> None:
    """DROP SCHEMA dentro do banco de ensaio. A guarda do nome está aqui e não só em quem chama: é o
    único lugar do produto que derruba schema, e apontar isso para o banco da plataforma apagaria dado
    de verdade."""
    if banco_ensaio == banco or not banco_ensaio.startswith("plat_drill_"):
        raise FalhaDefinitiva(f"ensaio de restauração: recusa derrubar schema fora do banco de ensaio ({banco_ensaio})")
    ctx.subprocesso(["sudo", "-n", "-u", "postgres", "psql", "-d", banco_ensaio, "-q", "-c",
                     f'DROP SCHEMA IF EXISTS "{esquema}" CASCADE'])


def _restaurar_e_contar(ctx, esquema: str, arquivo: Path, banco: str,
                        temporario: str) -> tuple[list[str], dict[str, int], dict[str, int]]:
    """(tabelas da produção com tenant_id, contagem na produção, contagem na cópia restaurada)."""
    _largar_schema(ctx, temporario, banco, esquema)
    rest = ctx.subprocesso(["sudo", "-n", "-u", "postgres", "pg_restore", "-d", temporario,
                            "--no-owner", "--no-privileges", str(arquivo)])
    if rest.returncode != 0:
        ctx.log("AVISO", f"pg_restore de {esquema} devolveu código {rest.returncode} (a prova é por COUNT(*))")
    tabelas = _tabelas_com_tenant(ctx, banco, esquema)
    restauradas_nomes = set(_tabelas_com_tenant(ctx, temporario, esquema))
    producao = _contar(ctx, banco, esquema, tabelas)
    restauradas = _contar(ctx, temporario, esquema, [t for t in tabelas if t in restauradas_nomes])
    return tabelas, producao, restauradas
