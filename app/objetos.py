"""Armazenamento de objetos por inquilino no Garage (item L0-11-arquivos-objetos; ADR 0006). Substitui o
adaptador local em disco (`PLAT_DADOS_DIR`) mantendo a MESMA assinatura de `guardar/ler/existe/apagar/
url_assinada/assinatura_valida` que `app/catalogo/miniatura.py`, `app/catalogo/destruidores.py`,
`app/catalogo/tarefas.py` e `app/catalogo/rotas_compartilhamento.py` já chamavam (ADR 0004 seção 11.3): nenhum
desses quatro arquivos muda de comportamento por fora; só `guardar` ganha `cur` (para gravar o metadado com RLS e
para achar o inquilino atual) e um `item_id` agora opcional (uploads genéricos, sem item dono).

Isolamento: 1 bucket por inquilino no Garage (`plat.arquivo_bucket`, alias `<PLAT_GARAGE_BUCKET_PREFIXO><slug>`),
criado sob demanda (`garantir_bucket`) com 2 chaves de acesso próprias (RW só a API usa; RO reservada ao L1-02
para tiles) e cota espelhada de `tenant.cota_bytes` — o próprio Garage recusa escrita acima da cota (MEDIDO
contra esta instância antes de escrever este módulo, ver ADR 0006 seção 3: PUT acima da cota devolve 403
AccessDenied; chave sem permissão de escrita também 403; chave de outro bucket não lê o bucket errado, também
403 — os três são o mecanismo do Garage, não uma checagem nossa que possa ter bug).

Chave (o que os quatro chamadores gravam e devolvem): `<slug>/<classe>/[<referencia>/]<sha256>.<ext>`. O
prefixo `<slug>` é o que permite a `ler/existe/apagar/url_assinada` resolverem o bucket certo SEM precisar de
contexto de sessão — a entrega por URL assinada (`GET /api/objetos/{chave}`) é uma rota anônima (ADR 0004 seção
11.2) que não passa por `db.db(ctx)`; a chave sozinha basta.

Nome do objeto = sha256 do conteúdo: duas gravações do mesmo conteúdo (mesma classe/referência) caem na mesma
chave (`HEAD` antes de `PUT`: se já existe, não regrava — nunca sobrescreve com conteúdo diferente, porque a
chave SÓ é a mesma quando o conteúdo é o mesmo).

Item L7-03-b-antivirus-anexos (`app/varredura_conteudo.py`): `guardar()` em si NÃO varre conteúdo — ver a nota
no próprio docstring da função sobre por quê (adaptador genérico, chamado também com conteúdo já validado por
Pillow e com conteúdo sintético de teste). Quem recebe byte cru de fora varre na borda, antes de chamar
`guardar()`: `app/rotas_arquivos.py::enviar()` é o único caminho que grava byte de cliente sem passar por
outra validação primeiro."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
import uuid
from typing import Any

from app import db
from app.garage import ClienteAdmin, ClienteS3, CotaGarage, ErroGarage
from app.settings import settings
from app.varredura_conteudo import ConteudoRecusado, escanear_cabecalho  # noqa: F401 — reexportado (item L7-03-b)

log = logging.getLogger("plat.objetos")

EXTENSOES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/tiff": "tif",
    "image/webp": "webp",
    "application/json": "json",
    "application/geo+json": "geojson",
    "text/csv": "csv",
    "application/pdf": "pdf",
    "application/zip": "zip",
    "application/vnd.google-earth.kmz": "kmz",
    "application/octet-stream": "bin",
}
_SLUG = r"[a-z0-9][a-z0-9-]{1,38}"
_CLASSE = r"[a-z0-9_]{1,40}"
_REFERENCIA = r"[0-9a-zA-Z_-]{1,64}"
_SHA256 = r"[0-9a-f]{64}"
_EXT = r"[a-z0-9]{1,8}"
CHAVE = re.compile(rf"^(?P<slug>{_SLUG})/(?P<classe>{_CLASSE})/((?P<referencia>{_REFERENCIA})/)?(?P<sha256>{_SHA256})\.(?P<ext>{_EXT})$")  # noqa: E501
PARTE_TAMANHO_MINIMO = 5 * 1024 * 1024  # regra do S3: toda parte exceto a última tem de ter >= 5 MiB


class ChaveInvalida(ValueError):
    """Chave fora do padrão <slug>/<classe>/[<referencia>/]<sha256>.<ext>: nunca chega ao Garage."""


class ConfiguracaoAusente(RuntimeError):
    """PLAT_GARAGE_ADMIN_URL/PLAT_GARAGE_ADMIN_TOKEN ausentes: sem eles não se cria bucket novo."""


class CotaExcedida(RuntimeError):
    """O objeto levaria o inquilino acima de tenant.cota_bytes (checagem prévia; o Garage também recusa)."""


class UploadInexistente(ValueError):
    """upload_id sem linha em plat.arquivo_upload (concluído, abortado, ou de outro inquilino: RLS o esconde)."""


def _partes(chave: str) -> dict:
    m = CHAVE.match(chave)
    if not m:
        raise ChaveInvalida(chave)
    return m.groupdict()


def _admin() -> ClienteAdmin:
    if not settings.PLAT_GARAGE_ADMIN_URL or not settings.PLAT_GARAGE_ADMIN_TOKEN:
        raise ConfiguracaoAusente("PLAT_GARAGE_ADMIN_URL e PLAT_GARAGE_ADMIN_TOKEN são obrigatórios para L0-11")
    return ClienteAdmin(settings.PLAT_GARAGE_ADMIN_URL, settings.PLAT_GARAGE_ADMIN_TOKEN)


def _cliente(bucket: dict, *, ro: bool = False) -> ClienteS3:
    if not settings.PLAT_GARAGE_URL:
        raise ConfiguracaoAusente("PLAT_GARAGE_URL é obrigatório para L0-11")
    chave_id = bucket["chave_ro_id"] if ro else bucket["chave_rw_id"]
    segredo = bucket["chave_ro_segredo"] if ro else bucket["chave_rw_segredo"]
    return ClienteS3(settings.PLAT_GARAGE_URL, chave_id, segredo, settings.PLAT_GARAGE_REGIAO)


def _tenant_atual(cur) -> tuple[int, str]:
    cur.execute("SELECT id, slug FROM plat.tenant WHERE id = plat.tenant_atual()")
    r = cur.fetchone()
    if r is None:
        raise RuntimeError("objetos: sem inquilino no contexto da conexão (db.db(ctx) exige Contexto)")
    return r["id"], r["slug"]


def _linha_bucket(cur, tenant_id: int) -> dict | None:
    cur.execute("SELECT * FROM plat.arquivo_bucket_por_tenant(%s)", (tenant_id,))
    return cur.fetchone()


COTA_OBJETOS_PADRAO = 200000  # mesmo DEFAULT de plat.tenant.cota_objetos (migração 042)


def _cotas_tenant(cur, tenant_id: int) -> tuple[int, int]:
    """(cota_bytes, cota_objetos) do inquilino — `plat.tenant` é a autoridade; o balde só espelha."""
    cur.execute("SELECT cota_bytes, cota_objetos FROM plat.tenant WHERE id = %s", (tenant_id,))
    r = cur.fetchone()
    if r is None:
        return 21474836480, COTA_OBJETOS_PADRAO
    return int(r["cota_bytes"]), int(r["cota_objetos"] or COTA_OBJETOS_PADRAO)


def garantir_bucket(
    cur, tenant_id: int | None = None, tenant_slug: str | None = None, *, web: bool | None = None, forcar: bool = False
) -> dict:
    """Idempotente: cria bucket + 2 chaves (RW, RO) + cotas (bytes E objetos, item L1-01-d) no Garage na 1ª chamada;
    nas seguintes só confere e resincroniza se `tenant.cota_bytes`/`cota_objetos` mudaram desde a última vez (ou
    sempre, com `forcar=True` — é o que a semeadura do install.sh usa para provar que o Garage está igual ao
    banco). `web=True/False` liga/desliga o endpoint web do balde (:3902; ADR 0016) e grava `web_ativo`; `None`
    mantém o que está. Devolve a linha de `plat.arquivo_bucket`."""
    if tenant_id is None or tenant_slug is None:
        tenant_id, tenant_slug = _tenant_atual(cur)
    linha = _linha_bucket(cur, tenant_id)
    cota_bytes, cota_objetos = _cotas_tenant(cur, tenant_id)
    if linha is not None:
        web_alvo = bool(linha["web_ativo"]) if web is None else bool(web)
        mudou_cota = int(linha["cota_bytes"]) != cota_bytes or int(linha["cota_objetos"]) != cota_objetos
        mudou_web = web_alvo != bool(linha["web_ativo"])
        if mudou_cota or forcar:
            _admin().definir_cota(linha["bucket_id"], cota_bytes, cota_objetos)
        if mudou_web or forcar:
            _admin().definir_web(linha["bucket_id"], web_alvo)
        if mudou_cota or mudou_web:
            cur.execute(
                "SELECT plat.arquivo_bucket_cotas_atualizar(%s, %s, %s, %s)",
                (tenant_id, cota_bytes, cota_objetos, web_alvo),
            )
            linha = _linha_bucket(cur, tenant_id)
        return linha
    admin = _admin()
    alias = f"{settings.PLAT_GARAGE_BUCKET_PREFIXO}{tenant_slug}"
    bucket = admin.criar_bucket(alias)
    rw = admin.criar_chave(f"{alias}-rw")
    ro = admin.criar_chave(f"{alias}-ro")
    ids_permitidos = {k["accessKeyId"] for k in bucket.get("keys", [])}
    if rw["accessKeyId"] not in ids_permitidos:
        admin.permitir(bucket["id"], rw["accessKeyId"], ler=True, escrever=True, dono=True)
    if ro["accessKeyId"] not in ids_permitidos:
        admin.permitir(bucket["id"], ro["accessKeyId"], ler=True, escrever=False, dono=False)
    admin.definir_cota(bucket["id"], cota_bytes, cota_objetos)
    admin.definir_web(bucket["id"], bool(web))
    cota_atual = cota_bytes
    # criar_chave é idempotente por NOME (ClienteAdmin.criar_chave): se a chave já existia, a resposta não traz
    # `secretAccessKey` de volta (o Garage só devolve o segredo na criação) — nesse caso o segredo já gravado em
    # plat.arquivo_bucket é o único que vale; só entra aqui na 1ª vez que este bucket é criado, então sempre é novo
    cur.execute(
        "SELECT plat.arquivo_bucket_registrar(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            tenant_id,
            bucket["id"],
            alias,
            rw["accessKeyId"],
            rw["secretAccessKey"],
            ro["accessKeyId"],
            ro["secretAccessKey"],
            cota_atual,
        ),
    )
    cur.execute(
        "SELECT plat.arquivo_bucket_cotas_atualizar(%s, %s, %s, %s)", (tenant_id, cota_bytes, cota_objetos, bool(web))
    )
    log.info("objetos: bucket %s criado para tenant_id=%s", alias, tenant_id)
    return _linha_bucket(cur, tenant_id)


def semear_bucket(cur, tenant_id: int, tenant_slug: str, *, web: bool = True) -> tuple[dict, list[str]]:
    """Passo de instalação (install.sh seção g3, item L1-01-d): garante balde/chaves/cotas/web do inquilino e
    devolve `(linha, mudanças)` — lista vazia na 2ª execução (é o que prova a idempotência). Depois de sincronizar,
    LÊ o balde de volta pela Admin API e confere que as cotas do Garage são as do banco; divergência é erro alto,
    nunca silêncio."""
    antes = _linha_bucket(cur, tenant_id)
    linha = garantir_bucket(cur, tenant_id, tenant_slug, web=web, forcar=antes is None)
    mudancas: list[str] = []
    if antes is None:
        mudancas.append("balde, chaves RW/RO, cotas e web criados")
    else:
        for campo in ("cota_bytes", "cota_objetos", "web_ativo"):
            if antes[campo] != linha[campo]:
                mudancas.append(f"{campo}: {antes[campo]} -> {linha[campo]}")
    info = _admin().info_bucket(linha["bucket_id"])
    cotas = info.get("quotas") or {}
    if int(cotas.get("maxSize") or 0) != int(linha["cota_bytes"]) or int(cotas.get("maxObjects") or 0) != int(
        linha["cota_objetos"]
    ):
        _admin().definir_cota(linha["bucket_id"], int(linha["cota_bytes"]), int(linha["cota_objetos"]))
        mudancas.append("cota reaplicada no Garage (divergia do banco)")
    if bool(info.get("websiteAccess")) != bool(linha["web_ativo"]):
        _admin().definir_web(linha["bucket_id"], bool(linha["web_ativo"]))
        mudancas.append("web reaplicado no Garage (divergia do banco)")
    return linha, mudancas


def _resolver_bucket_por_slug(tenant_slug: str) -> dict | None:
    """Fora de qualquer contexto de inquilino (rota anônima de entrega): conexão própria, função SECURITY
    DEFINER (mesmo padrão de auth_* — ADR 0001 seção 3.3)."""
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.arquivo_bucket_resolver(%s)", (tenant_slug,))
        return cur.fetchone()


def _chave_e_objeto(chave: str) -> tuple[dict, str]:
    """(linha do bucket, caminho do objeto DENTRO do bucket) a partir da chave completa; ChaveInvalida se malformada
    ou FileNotFoundError se o inquilino da chave não tem bucket (nunca existiu ou foi apagado)."""
    p = _partes(chave)
    bucket = _resolver_bucket_por_slug(p["slug"])
    if bucket is None:
        raise FileNotFoundError(chave)
    meio = f"{p['referencia']}/" if p["referencia"] else ""
    obj_key = f"{p['classe']}/{meio}{p['sha256']}.{p['ext']}"
    return bucket, obj_key


def _registrar_metadado(
    cur, tenant_id: int, classe: str, referencia: str | None, sha256: str, tamanho: int, content_type: str,
    chave: str, usuario_id: int | None = None,
) -> None:
    """INSERT se não houver linha; UPDATE (revive) se a única linha existente estiver apagada; nada se já houver
    linha viva — nunca colide com `ix_arquivo_dedupe` (índice único parcial só entre linhas vivas)."""
    cur.execute(
        "SELECT id, apagado_em FROM plat.arquivo WHERE tenant_id=%s AND classe=%s "
        "AND coalesce(referencia,'')=coalesce(%s,'') AND sha256=%s ORDER BY apagado_em NULLS FIRST LIMIT 1",
        (tenant_id, classe, referencia, sha256),
    )
    r = cur.fetchone()
    if r is None:
        cur.execute(
            "INSERT INTO plat.arquivo (tenant_id, classe, referencia, sha256, bytes, content_type, chave, criado_por) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (tenant_id, classe, referencia, sha256, tamanho, content_type, chave, usuario_id),
        )
    elif r["apagado_em"] is not None:
        cur.execute(
            "UPDATE plat.arquivo SET apagado_em = NULL, bytes=%s, content_type=%s, chave=%s, criado_em=now(), "
            "criado_por=%s WHERE id = %s",
            (tamanho, content_type, chave, usuario_id, r["id"]),
        )


# ---------------------------------------------------------------- contrato principal (ADR 0004 seção 11.3)
def guardar(
    cur, classe: str, dados: bytes, content_type: str, item_id: Any = None, usuario_id: int | None = None
) -> dict:
    """`{chave, sha256, bytes, content_type}`. `item_id=None` = objeto genérico (chave sem segmento de referência,
    dedup só por sha256 dentro da classe — é o caminho de `POST /api/arquivos`). NÃO varre conteúdo aqui de
    propósito (item L7-03-b): este adaptador também é chamado com conteúdo já validado por outro meio (Pillow
    reencoda miniatura para PNG limpo antes de chegar aqui) e com conteúdo sintético de teste da própria
    suíte (`tests/api/catalogo/test_miniatura.py::test_adaptador_de_objetos_e_url_assinada` grava `b"abc"` sob
    `image/png` de propósito, para testar só o contrato de armazenamento) — variar o comportamento do
    adaptador conforme quem chama seria mais frágil que varrer na BORDA onde bytes não confiáveis de verdade
    entram: `app/rotas_arquivos.py::enviar()` chama `escanear_cabecalho()` antes de qualquer PUT/multipart."""
    tenant_id, tenant_slug = _tenant_atual(cur)
    bucket = garantir_bucket(cur, tenant_id, tenant_slug)
    sha = hashlib.sha256(dados).hexdigest()
    ext = EXTENSOES.get(content_type, "bin")
    referencia = str(item_id) if item_id is not None else None
    meio = f"{referencia}/" if referencia else ""
    obj_key = f"{classe}/{meio}{sha}.{ext}"
    chave = f"{tenant_slug}/{obj_key}"
    cli = _cliente(bucket)
    if cli.head(bucket["bucket_alias"], obj_key) is None:
        conferir_cotas(bucket, len(dados))
        try:
            cli.put(bucket["bucket_alias"], obj_key, dados, content_type)
        except CotaGarage as e:
            raise CotaExcedida(str(e)) from e
    _registrar_metadado(cur, tenant_id, classe, referencia, sha, len(dados), content_type, chave, usuario_id)
    return {"chave": chave, "sha256": sha, "bytes": len(dados), "content_type": content_type}


def existe(chave: str) -> bool:
    try:
        bucket, obj_key = _chave_e_objeto(chave)
    except (ChaveInvalida, FileNotFoundError):
        return False
    return _cliente(bucket).head(bucket["bucket_alias"], obj_key) is not None


def ler(chave: str) -> bytes:
    bucket, obj_key = _chave_e_objeto(chave)
    return _cliente(bucket).get(bucket["bucket_alias"], obj_key)


def ler_intervalo(chave: str, inicio: int, fim: int) -> bytes:
    """Bytes [inicio, fim] inclusive (contrato ADR 0005: cabeçalho central de zip sem baixar o arquivo inteiro)."""
    bucket, obj_key = _chave_e_objeto(chave)
    return _cliente(bucket).get_intervalo(bucket["bucket_alias"], obj_key, inicio, fim)


def apagar(chave: str) -> bool:
    """`True` só quando havia objeto (idempotente: a segunda chamada devolve `False`). O DELETE do S3/Garage é
    idempotente no sentido dele (sempre 204, exista ou não o objeto) — por isso o HEAD prévio decide o retorno,
    não o status da resposta do DELETE."""
    try:
        bucket, obj_key = _chave_e_objeto(chave)
    except FileNotFoundError:
        return False  # inquilino da chave nunca teve bucket (nada a apagar); ChaveInvalida continua subindo
    cli = _cliente(bucket)
    existia = cli.head(bucket["bucket_alias"], obj_key) is not None
    if existia:
        cli.delete(bucket["bucket_alias"], obj_key)
        with db.db() as cur:
            cur.execute(
                "UPDATE plat.arquivo SET apagado_em = now() WHERE tenant_id = %s AND chave = %s AND apagado_em IS NULL",
                (bucket["tenant_id"], chave),
            )
    return existia


def conferir_cotas(bucket: dict, bytes_novos: int, objetos_novos: int = 1) -> dict:
    """Checagem PRÉVIA (mensagem legível antes de o Garage recusar): uso atual + o que vai entrar contra as duas
    cotas do balde. Devolve `{bytes, objetos}` usados. O Garage recusa de qualquer forma se esta checagem tiver
    bug (ADR 0006 seção 2; a recusa dele chega traduzida por `CotaGarage`)."""
    info = _admin().info_bucket(bucket["bucket_id"])
    usado = int(info.get("bytes", 0))
    objetos = int(info.get("objects", 0))
    if usado + bytes_novos > int(bucket["cota_bytes"]):
        raise CotaExcedida(
            f"cota de {bucket['cota_bytes']} bytes excedida: uso atual {usado}, objeto de {bytes_novos} bytes"
        )
    if objetos + objetos_novos > int(bucket["cota_objetos"]):
        raise CotaExcedida(
            f"cota de {bucket['cota_objetos']} objetos excedida: uso atual {objetos}, mais {objetos_novos} objeto(s)"
        )
    return {"bytes": usado, "objetos": objetos}


def uso(tenant_slug: str) -> int:
    """bytes_usados do bucket do inquilino (0 se o inquilino ainda não tem bucket — nada foi gravado ainda)."""
    return uso_detalhado(tenant_slug)["bytes_usados"]


def uso_detalhado(tenant_slug: str) -> dict:
    """`{bytes_usados, objetos_usados, cota_bytes, cota_objetos, web_ativo}` lidos do PRÓPRIO Garage
    (GetBucketInfo: contagem exata dele, não uma soma nossa) e do registro do balde; zeros e `None` quando o
    inquilino ainda não tem balde."""
    bucket = _resolver_bucket_por_slug(tenant_slug)
    if bucket is None:
        return {"bytes_usados": 0, "objetos_usados": 0, "cota_bytes": None, "cota_objetos": None, "web_ativo": False}
    info = _admin().info_bucket(bucket["bucket_id"])
    return {
        "bytes_usados": int(info.get("bytes", 0)),
        "objetos_usados": int(info.get("objects", 0)),
        "cota_bytes": int(bucket["cota_bytes"]),
        "cota_objetos": int(bucket["cota_objetos"]),
        "web_ativo": bool(bucket["web_ativo"]),
    }


# ---------------------------------------------------------------- assinatura HMAC (inalterado; ADR 0004 11.2)
def _assinar(chave: str, ate: int, segredo: str) -> str:
    return hmac.new(segredo.encode(), f"{chave}|{ate}".encode(), hashlib.sha256).hexdigest()


def url_assinada(chave: str, segundos: int, segredo: str | None = None) -> str:
    _partes(chave)  # valida o formato antes de assinar
    ate = int(time.time()) + max(1, int(segundos))
    return f"/api/objetos/{chave}?ate={ate}&assinatura={_assinar(chave, ate, segredo or settings.PLAT_SECRET)}"


def assinatura_valida(chave: str, ate: int, assinatura: str, segredo: str | None = None) -> bool:
    if not CHAVE.match(chave) or ate < int(time.time()):
        return False
    esperada = _assinar(chave, ate, segredo or settings.PLAT_SECRET)
    return hmac.compare_digest(esperada, assinatura or "")


# ---------------------------------------------------------------- multipart (contrato ADR 0005 seção 11.3-estendida)
def parte_iniciar(cur, classe: str, content_type: str, item_id: Any = None) -> dict:
    """Abre upload multipart S3 num objeto temporário (`_tmp/<uuid>`); devolve `{upload_id, chave_temp}`."""
    tenant_id, tenant_slug = _tenant_atual(cur)
    bucket = garantir_bucket(cur, tenant_id, tenant_slug)
    chave_temp = f"_tmp/{uuid.uuid4()}"
    cli = _cliente(bucket)
    upload_id = cli.multipart_iniciar(bucket["bucket_alias"], chave_temp, content_type)
    cur.execute(
        "INSERT INTO plat.arquivo_upload (upload_id, tenant_id, classe, referencia, content_type, chave_temp) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        (upload_id, tenant_id, classe, str(item_id) if item_id is not None else None, content_type, chave_temp),
    )
    return {"upload_id": upload_id, "chave_temp": chave_temp}


def _upload_linha(cur, upload_id: str) -> dict:
    cur.execute("SELECT * FROM plat.arquivo_upload WHERE upload_id = %s", (upload_id,))
    r = cur.fetchone()
    if r is None:
        raise UploadInexistente(upload_id)
    return r


def parte_enviar(cur, upload_id: str, numero: int, dados: bytes) -> str:
    """Envia a parte `numero` (>=1); devolve o ETag que `parte_concluir` exige de volta."""
    linha = _upload_linha(cur, upload_id)
    bucket = garantir_bucket(cur, linha["tenant_id"])
    cli = _cliente(bucket)
    return cli.multipart_enviar_parte(bucket["bucket_alias"], linha["chave_temp"], upload_id, numero, dados)


def parte_concluir(cur, upload_id: str, partes: list[tuple[int, str]]) -> dict:
    """Fecha o multipart, lê o objeto de volta EM STREAM para calcular o sha256 real (o ETag multipart do
    S3 não é um sha256 do conteúdo), copia para a chave definitiva por conteúdo e apaga o temporário.
    `{chave, sha256, bytes}`."""
    linha = _upload_linha(cur, upload_id)
    bucket = garantir_bucket(cur, linha["tenant_id"])
    tenant_slug = bucket["bucket_alias"][len(settings.PLAT_GARAGE_BUCKET_PREFIXO):]
    cli = _cliente(bucket)
    cli.multipart_concluir(bucket["bucket_alias"], linha["chave_temp"], upload_id, partes)
    h = hashlib.sha256()
    tamanho = 0
    for pedaco in cli.get_stream(bucket["bucket_alias"], linha["chave_temp"]):
        h.update(pedaco)
        tamanho += len(pedaco)
    sha = h.hexdigest()
    ext = EXTENSOES.get(linha["content_type"], "bin")
    referencia = linha["referencia"]
    meio = f"{referencia}/" if referencia else ""
    obj_key = f"{linha['classe']}/{meio}{sha}.{ext}"
    if cli.head(bucket["bucket_alias"], obj_key) is None:
        cli.copiar(bucket["bucket_alias"], linha["chave_temp"], obj_key)
    cli.delete(bucket["bucket_alias"], linha["chave_temp"])
    cur.execute("DELETE FROM plat.arquivo_upload WHERE upload_id = %s", (upload_id,))
    chave = f"{tenant_slug}/{obj_key}"
    _registrar_metadado(
        cur, linha["tenant_id"], linha["classe"], referencia, sha, tamanho, linha["content_type"], chave
    )
    return {"chave": chave, "sha256": sha, "bytes": tamanho, "content_type": linha["content_type"]}


def parte_abortar(cur, upload_id: str) -> None:
    linha = _upload_linha(cur, upload_id)
    bucket = garantir_bucket(cur, linha["tenant_id"])
    cli = _cliente(bucket)
    try:
        cli.multipart_abortar(bucket["bucket_alias"], linha["chave_temp"], upload_id)
    except ErroGarage:
        log.warning("objetos: abortar multipart %s já não existia no Garage", upload_id)
    cur.execute("DELETE FROM plat.arquivo_upload WHERE upload_id = %s", (upload_id,))


# ---------------------------------------------------------------- varredura de órfãos (portão L0-11)
def varrer_orfaos(cur, tenant_slug: str) -> dict:
    """Compara o bucket real do inquilino com `plat.arquivo`: `sem_linha` = objeto no Garage sem metadado (upload
    que falhou depois do PUT); `sem_objeto` = metadado sem objeto no Garage (apagado por fora, ou bucket recriado).
    `cur` precisa estar no contexto do MESMO inquilino (RLS de `plat.arquivo`)."""
    tenant_id, slug_atual = _tenant_atual(cur)
    if slug_atual != tenant_slug:
        raise ValueError(f"varrer_orfaos: cur está no inquilino {slug_atual!r}, pedido {tenant_slug!r}")
    bucket = _linha_bucket(cur, tenant_id)
    if bucket is None:
        return {"sem_linha": [], "sem_objeto": [], "objetos_no_garage": 0, "linhas_no_banco": 0}
    cli = _cliente(bucket)
    no_garage = {o["chave"] for o in cli.listar(bucket["bucket_alias"]) if not o["chave"].startswith("_tmp/")}
    cur.execute(
        "SELECT classe, referencia, sha256, chave FROM plat.arquivo WHERE tenant_id = %s AND apagado_em IS NULL",
        (tenant_id,),
    )
    linhas = cur.fetchall()
    no_banco: dict[str, dict] = {}
    for linha in linhas:
        # a chave gravada é sempre `<slug>/<caminho no balde>` — tanto no formato do L0-11
        # (`<classe>/[ref/]<sha256>.<ext>`) quanto no de imagens do L1-01-d (`<item_id>/<asset>_<sha8>.<ext>`,
        # app/objetos_raster.py); o caminho no balde é o que vem depois da 1ª barra
        _slug, _, obj_key = linha["chave"].partition("/")
        no_banco[obj_key] = linha
    sem_linha = sorted(no_garage - set(no_banco.keys()))
    sem_objeto = [dict(no_banco[k]) for k in sorted(set(no_banco.keys()) - no_garage)]
    return {
        "sem_linha": sem_linha,
        "sem_objeto": sem_objeto,
        "objetos_no_garage": len(no_garage),
        "linhas_no_banco": len(no_banco),
    }


# ---------------------------------------------------------------- ciclo de vida do balde (item L1-01-d)
def apagar_bucket_do_inquilino(cur, tenant_id: int) -> dict:
    """Desfaz o que `garantir_bucket` fez: esvazia o balde, apaga as duas chaves de acesso, apaga o balde no
    Garage e a linha de `plat.arquivo_bucket`. Existe porque apagar o inquilino (`plat.inquilino_apagar`) só
    limpa o banco — sem isto o balde e as chaves ficariam órfãos no Garage. Idempotente: sem linha, devolve zeros.
    Devolve `{objetos, bytes}` liberados."""
    linha = _linha_bucket(cur, tenant_id)
    if linha is None:
        return {"objetos": 0, "bytes": 0}
    admin = _admin()
    cli = _cliente(linha)
    alias = linha["bucket_alias"]
    apagados = 0
    liberados = 0
    for o in cli.listar(alias, max_chaves=1000):
        cli.delete(alias, o["chave"])
        apagados += 1
        liberados += int(o["bytes"])
    for chave_id in (linha["chave_rw_id"], linha["chave_ro_id"]):
        try:
            admin.apagar_chave(chave_id)
        except ErroGarage:
            log.warning("objetos: chave %s já não existia no Garage", chave_id)
    try:
        admin.apagar_bucket(linha["bucket_id"])
    except ErroGarage:
        log.warning("objetos: balde %s já não existia no Garage", linha["bucket_id"])
    cur.execute("DELETE FROM plat.arquivo_bucket WHERE tenant_id = %s", (tenant_id,))
    cur.execute("UPDATE plat.arquivo SET apagado_em = now() WHERE tenant_id = %s AND apagado_em IS NULL", (tenant_id,))
    log.info("objetos: balde %s apagado (%s objeto(s), %s bytes)", alias, apagados, liberados)
    return {"objetos": apagados, "bytes": liberados}
