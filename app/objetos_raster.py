"""Objetos de IMAGEM por inquilino no Garage (item L1-01-d-garage-por-inquilino; ADR 20260908T1255, sobre o ADR 0006).
Constrói EM CIMA de `app/objetos.py` (balde/chaves/cota por inquilino, `plat.arquivo`, `garantir_bucket`) o que a
linha L1 exige e o adaptador genérico não dava:

- nome do objeto por CONTEÚDO no formato da linha de imagens, `<item_id>/<asset>_<sha8>.<ext>` dentro do balde
  (chave completa `<slug>/<item_id>/<asset>_<sha8>.<ext>`), e NUNCA sobrescrito: `guardar_*` faz `HEAD` antes e
  levanta `ObjetoJaExiste` se a chave já está no balde — a regra medida em 29/08 (sobrescrever o mesmo nome deixou
  o TiTiler em 500 pelo cache VSI e a CDN com tile velho) vira recusa explícita do adaptador, não convenção;
- gravação a partir de ARQUIVO em disco (é assim que o worker de conversão para COG chega aqui), em stream:
  sha256 calculado em pedaços, `PUT` único até `limites.ARQUIVO_BUFFER_UNICO_BYTES`, multipart real acima disso,
  nunca mais que uma parte (`limites.ARQUIVO_PARTE_BYTES`) na memória do processo;
- cota em bytes E em objetos conferida antes (`objetos.conferir_cotas`) e, se o Garage recusar mesmo assim, a
  recusa dele chega traduzida (`garage.CotaGarage` → `objetos.CotaExcedida`, mensagem em português);
- leitura sempre com a chave SÓ-LEITURA do inquilino (`ro=True`): é a mesma chave que o TiTiler e a conexão S3
  do ArcGIS Pro recebem (`credenciais_leitura`), então o que este módulo lê é exatamente o que eles conseguem ler;
- `apagar_item` remove todos os objetos do prefixo `<item_id>/` do balde (o destruidor de item `raster` chama
  isto) e marca as linhas de `plat.arquivo`; o balde reflete a cota na hora (GetBucketInfo do próprio Garage).

A chave de ESCRITA (RW) só existe dentro de `objetos._cliente(bucket)` (processo da API/worker); nenhuma rota
devolve o segredo dela. A chave só-leitura sai por `GET /api/arquivos/_chave-leitura` (privilégio
`org.integracoes`, só sessão) porque o Pro precisa dela para a conexão S3 — decisão registrada no ADR 20260908T1255."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Iterator

from app import limites, objetos
from app.garage import CotaGarage, ErroGarage
from app.objetos import ChaveInvalida, CotaExcedida  # noqa: F401 — reexportadas para quem só importa este módulo

log = logging.getLogger("plat.objetos_raster")

CLASSE = "raster"
_ITEM_ID = r"[0-9A-Za-z][0-9A-Za-z_-]{0,63}"  # ULID (26) ou id da casa; sem ponto e sem barra por construção
_ASSET = r"[a-z][a-z0-9_]{0,39}"
_SHA8 = r"[0-9a-f]{8}"
_EXT = r"[a-z0-9]{1,8}"
OBJETO = re.compile(rf"^(?P<item_id>{_ITEM_ID})/(?P<asset>{_ASSET})_(?P<sha8>{_SHA8})\.(?P<ext>{_EXT})$")
CHAVE = re.compile(
    rf"^(?P<slug>{objetos._SLUG})/(?P<item_id>{_ITEM_ID})/(?P<asset>{_ASSET})_(?P<sha8>{_SHA8})\.(?P<ext>{_EXT})$"
)
EXTENSOES = {
    "image/tiff": "tif",
    "image/png": "png",
    "image/jpeg": "jpg",
    "application/json": "json",
    "application/vnd.laszip": "laz",
    "application/octet-stream": "bin",
}


class ObjetoJaExiste(RuntimeError):
    """A chave já existe no balde: um objeto de imagem nunca é sobrescrito (item L1-01-d). Quem quer o objeto
    existente lê por `existe()`/`info()`; quem tem conteúdo novo ganha sha8 novo e, portanto, chave nova."""


def objeto(item_id: str, asset: str, sha256: str, ext: str) -> str:
    """Caminho DENTRO do balde: `<item_id>/<asset>_<sha8>.<ext>`. ChaveInvalida se qualquer parte sair do padrão
    (inclui `..`, `/` e ponto no item_id/asset: a expressão não os admite, então não há travessia possível)."""
    if not re.fullmatch(r"[0-9a-f]{64}", sha256 or ""):
        raise ChaveInvalida(f"sha256 fora do padrão: {sha256!r}")
    caminho = f"{item_id}/{asset}_{sha256[:8]}.{ext}"
    if not OBJETO.match(caminho):
        raise ChaveInvalida(caminho)
    return caminho


def chave(slug: str, caminho_objeto: str) -> str:
    completa = f"{slug}/{caminho_objeto}"
    if not CHAVE.match(completa):
        raise ChaveInvalida(completa)
    return completa


def partes(chave_completa: str) -> dict:
    m = CHAVE.match(chave_completa or "")
    if not m:
        raise ChaveInvalida(chave_completa)
    return m.groupdict()


def sha256_arquivo(caminho: str | Path, pedaco: int = limites.ARQUIVO_PARTE_BYTES) -> tuple[str, int]:
    """(sha256, tamanho) lendo o arquivo em pedaços — nunca o arquivo inteiro na memória."""
    h = hashlib.sha256()
    tamanho = 0
    with open(caminho, "rb") as f:
        while True:
            b = f.read(pedaco)
            if not b:
                break
            h.update(b)
            tamanho += len(b)
    return h.hexdigest(), tamanho


def _pedacos(caminho: str | Path, tamanho_parte: int) -> Iterator[bytes]:
    with open(caminho, "rb") as f:
        while True:
            b = f.read(tamanho_parte)
            if not b:
                break
            yield b


def _bucket_e_objeto(chave_completa: str) -> tuple[dict, str]:
    p = partes(chave_completa)
    bucket = objetos._resolver_bucket_por_slug(p["slug"])
    if bucket is None:
        raise FileNotFoundError(chave_completa)
    return bucket, chave_completa.partition("/")[2]


def _gravar(
    cur, item_id: str, asset: str, ext: str, content_type: str, sha: str, tamanho: int, pedacos: Iterator[bytes]
) -> dict:
    tenant_id, slug = objetos._tenant_atual(cur)
    bucket = objetos.garantir_bucket(cur, tenant_id, slug)
    alias = bucket["bucket_alias"]
    caminho = objeto(item_id, asset, sha, ext)
    completa = chave(slug, caminho)
    cli = objetos._cliente(bucket)
    if cli.head(alias, caminho) is not None:
        raise ObjetoJaExiste(f"{completa}: já existe no balde e um objeto de imagem nunca é sobrescrito")
    objetos.conferir_cotas(bucket, tamanho)
    try:
        if tamanho <= limites.ARQUIVO_BUFFER_UNICO_BYTES:
            cli.put(alias, caminho, b"".join(pedacos), content_type)
        else:
            upload_id = cli.multipart_iniciar(alias, caminho, content_type)
            enviadas: list[tuple[int, str]] = []
            try:
                for numero, dados in enumerate(pedacos, start=1):
                    enviadas.append((numero, cli.multipart_enviar_parte(alias, caminho, upload_id, numero, dados)))
                cli.multipart_concluir(alias, caminho, upload_id, enviadas)
            except Exception:
                try:
                    cli.multipart_abortar(alias, caminho, upload_id)
                except ErroGarage:
                    log.warning("objetos_raster: abortar multipart %s falhou (já não existia?)", upload_id)
                raise
    except CotaGarage as e:
        raise CotaExcedida(str(e)) from e
    info = cli.head(alias, caminho)
    if info is None or info.tamanho != tamanho:
        raise ErroGarage(f"{completa}: gravado com {getattr(info, 'tamanho', None)} bytes, esperado {tamanho}")
    objetos._registrar_metadado(cur, tenant_id, CLASSE, item_id, sha, tamanho, content_type, completa)
    return {
        "chave": completa,
        "objeto": caminho,
        "bucket": alias,
        "sha256": sha,
        "sha8": sha[:8],
        "bytes": tamanho,
        "content_type": content_type,
    }


def guardar_arquivo(
    cur, item_id: str, asset: str, caminho: str | Path, content_type: str = "image/tiff", ext: str | None = None
) -> dict:
    """Grava um arquivo do disco (COG gerado pelo worker) como `<item_id>/<asset>_<sha8>.<ext>`; devolve
    `{chave, objeto, bucket, sha256, sha8, bytes, content_type}`. `ObjetoJaExiste` se a chave já está no balde;
    `CotaExcedida` (bytes ou objetos) antes ou quando o Garage recusa."""
    ext = ext or EXTENSOES.get(content_type, "bin")
    sha, tamanho = sha256_arquivo(caminho)
    if tamanho == 0:
        raise ChaveInvalida(f"{caminho}: arquivo vazio não vira objeto de imagem")
    return _gravar(cur, item_id, asset, ext, content_type, sha, tamanho, _pedacos(caminho, limites.ARQUIVO_PARTE_BYTES))


def guardar_bytes(
    cur, item_id: str, asset: str, dados: bytes, content_type: str = "image/tiff", ext: str | None = None
) -> dict:
    """Mesmo contrato de `guardar_arquivo` para conteúdo já na memória (miniatura, JSON de estatística, teste)."""
    ext = ext or EXTENSOES.get(content_type, "bin")
    if not dados:
        raise ChaveInvalida("conteúdo vazio não vira objeto de imagem")
    sha = hashlib.sha256(dados).hexdigest()
    return _gravar(cur, item_id, asset, ext, content_type, sha, len(dados), iter([dados]))


# ---------------------------------------------------------------- leitura: SEMPRE com a chave só-leitura
def existe(chave_completa: str) -> bool:
    try:
        bucket, caminho = _bucket_e_objeto(chave_completa)
    except (ChaveInvalida, FileNotFoundError):
        return False
    return objetos._cliente(bucket, ro=True).head(bucket["bucket_alias"], caminho) is not None


def info(chave_completa: str):
    bucket, caminho = _bucket_e_objeto(chave_completa)
    return objetos._cliente(bucket, ro=True).head(bucket["bucket_alias"], caminho)


def ler_intervalo(chave_completa: str, inicio: int, fim: int) -> bytes:
    """Bytes [inicio, fim] com a chave só-leitura (o que o TiTiler faz por /vsis3 e o Pro pela conexão S3)."""
    bucket, caminho = _bucket_e_objeto(chave_completa)
    return objetos._cliente(bucket, ro=True).get_intervalo(bucket["bucket_alias"], caminho, inicio, fim)


def listar_item(cur, item_id: str) -> list[dict]:
    """Objetos do item no balde do inquilino do contexto (`[{chave, bytes, etag}]`, caminho dentro do balde)."""
    if not re.fullmatch(_ITEM_ID, item_id or ""):
        raise ChaveInvalida(item_id)
    tenant_id, slug = objetos._tenant_atual(cur)
    bucket = objetos._linha_bucket(cur, tenant_id)
    if bucket is None:
        return []
    return objetos._cliente(bucket, ro=True).listar(bucket["bucket_alias"], prefixo=f"{item_id}/")


def apagar_item(cur, item_id: str) -> dict:
    """Apaga todos os objetos `<item_id>/...` do balde do inquilino do contexto e marca as linhas de
    `plat.arquivo`; devolve `{objetos, bytes}` liberados. Idempotente (segunda chamada = zeros). O balde do
    Garage reflete na hora: GetBucketInfo já sai com bytes/objects menores (é o que o teste (f) prova)."""
    if not re.fullmatch(_ITEM_ID, item_id or ""):
        raise ChaveInvalida(item_id)
    tenant_id, slug = objetos._tenant_atual(cur)
    bucket = objetos._linha_bucket(cur, tenant_id)
    if bucket is None:
        return {"objetos": 0, "bytes": 0}
    cli = objetos._cliente(bucket)
    alias = bucket["bucket_alias"]
    liberados = 0
    apagados = 0
    for o in cli.listar(alias, prefixo=f"{item_id}/"):
        cli.delete(alias, o["chave"])
        apagados += 1
        liberados += int(o["bytes"])
    cur.execute(
        "UPDATE plat.arquivo SET apagado_em = now() WHERE tenant_id = %s AND classe = %s AND referencia = %s "
        "AND apagado_em IS NULL",
        (tenant_id, CLASSE, item_id),
    )
    if apagados:
        log.info(
            "objetos_raster: item %s do inquilino %s: %s objeto(s), %s bytes apagados",
            item_id, slug, apagados, liberados,
        )
    return {"objetos": apagados, "bytes": liberados}


# ---------------------------------------------------------------- credenciais só-leitura e caminho web
def credenciais_leitura(cur) -> dict:
    """A chave SÓ-LEITURA do inquilino do contexto com o que a conexão S3 do ArcGIS Pro (`Create Cloud Storage
    Connection File`, provedor MinIO/S3 compatível, path-style) e o TiTiler (`/vsis3`) precisam: endpoint, região,
    balde, id e segredo. Nunca a chave RW. `endpoint` é o interno (`PLAT_GARAGE_URL`); a exposição pública por
    HTTPS é decisão de infraestrutura registrada no ADR 20260908T1255 (pendência), por isso sai também
    `endpoint_publico` vazio até existir."""
    tenant_id, slug = objetos._tenant_atual(cur)
    bucket = objetos.garantir_bucket(cur, tenant_id, slug)
    return {
        "endpoint": objetos.settings.PLAT_GARAGE_URL,
        "endpoint_publico": None,
        "regiao": objetos.settings.PLAT_GARAGE_REGIAO,
        "bucket": bucket["bucket_alias"],
        "estilo": "path",
        "access_key_id": bucket["chave_ro_id"],
        "secret_access_key": bucket["chave_ro_segredo"],
        "permissoes": {"read": True, "write": False, "owner": False},
        "web_ativo": bool(bucket["web_ativo"]),
    }


def caminho_web(token: str, chave_completa: str) -> str:
    """Caminho público de um objeto de imagem atrás do nginx (deploy/nginx.conf, bloco `/svc/<token>/cog/`):
    o token de serviço do inquilino vai no caminho (conceito C6 do L1), validado por auth_request na aplicação
    (`GET /api/arquivos/_cog/autorizar`) antes de o nginx servir/cachear fatias de 1 MiB do endpoint web do
    Garage. `chave_completa` = `<slug>/<item_id>/<asset>_<sha8>.<ext>`."""
    partes(chave_completa)
    if not re.fullmatch(r"plat_[A-Za-z0-9_\-]{20,128}", token or ""):
        raise ChaveInvalida("token fora do padrão plat_<urlsafe>")
    return f"/svc/{token}/cog/{chave_completa}"
