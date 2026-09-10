"""Cliente do Garage (item L0-11-arquivos-objetos; ADR 0006): S3 assinado AWS SigV4 (sem boto3/botocore — a venv
tem só `requests`, ~2 KB de dependência nova de zero versus dezenas de MB de botocore num disco a 98 %; a
assinatura é ~80 linhas e foi MEDIDA contra o Garage real desta máquina antes de entrar aqui, ver ADR seção 3) e
cliente da Admin API v2 (:3903, Bearer, `PLAT_GARAGE_ADMIN_TOKEN`) para criar bucket/chave/cota. Path-style sempre
(`AWS_VIRTUAL_HOSTING=FALSE`, igual ao `.env.pipeline`/`.env.titiler` já em produção nesta máquina)."""

from __future__ import annotations

import datetime
import hashlib
import hmac
import logging
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger("plat.garage")
TIMEOUT_S = 30.0
SERVICO = "s3"


class ErroGarage(RuntimeError):
    """Garage (S3 ou Admin API) devolveu erro; a mensagem traz o corpo devolvido, cortado."""


class CotaGarage(ErroGarage):
    """O PRÓPRIO Garage recusou a escrita por cota do balde (bytes ou objetos) — item L1-01-d: a mensagem já
    vem em português (`traduzir_erro_s3`) para chegar assim à API e à tela; `limite` é o número que o Garage
    citou, quando citou."""

    def __init__(self, mensagem: str, *, tipo: str, limite: int | None):
        super().__init__(mensagem)
        self.tipo = tipo  # "bytes" | "objetos"
        self.limite = limite


_RE_XML_CODE = re.compile(r"<Code>([^<]*)</Code>")
_RE_XML_MSG = re.compile(r"<Message>([^<]*)</Message>")
_RE_NUMERO = re.compile(r"(\d+)\s*$")


def traduzir_erro_s3(status: int, corpo: str) -> tuple[str, str, CotaGarage | None]:
    """(código S3, mensagem em português, CotaGarage ou None) a partir da resposta de erro do Garage. As frases
    do Garage foram MEDIDAS nesta instância (v2.3.0, 06/09/2026): "Bucket size quota is reached, maximum size
    for this bucket: N" e "Object quota is reached, maximum objects for this bucket: N" (ambas 403 AccessDenied);
    "Operation is not allowed for this key" (chave sem permissão; também 403)."""
    codigo = (_RE_XML_CODE.search(corpo or "") or [None, ""])[1] or f"HTTP{status}"
    msg = (_RE_XML_MSG.search(corpo or "") or [None, ""])[1] or (corpo or "")[:200]
    baixo = msg.lower()
    numero = _RE_NUMERO.search(msg)
    limite = int(numero.group(1)) if numero else None
    if "size quota" in baixo:
        pt = "o Garage recusou a gravação: a cota de armazenamento do inquilino foi atingida"
        if limite is not None:
            pt += f" (limite do balde: {limite} bytes)"
        return codigo, pt, CotaGarage(pt, tipo="bytes", limite=limite)
    if "object quota" in baixo:
        pt = "o Garage recusou a gravação: a cota de objetos do inquilino foi atingida"
        if limite is not None:
            pt += f" (limite do balde: {limite} objetos)"
        return codigo, pt, CotaGarage(pt, tipo="objetos", limite=limite)
    if "not allowed for this key" in baixo:
        return codigo, "a chave de acesso não tem permissão para esta operação neste balde", None
    if codigo == "NoSuchBucket":
        return codigo, "o balde não existe no Garage", None
    if codigo == "NoSuchKey":
        return codigo, "o objeto não existe no balde", None
    return codigo, f"o Garage respondeu {status} {codigo}: {msg}", None


def _erro_escrita(operacao: str, status: int, corpo: str) -> ErroGarage:
    """Exceção certa para uma resposta de erro de ESCRITA: CotaGarage quando foi cota, ErroGarage nos demais."""
    codigo, pt, cota = traduzir_erro_s3(status, corpo)
    if cota is not None:
        return cota
    return ErroGarage(f"{operacao}: {status} {codigo} — {pt}")


def _assinar(chave: bytes, mensagem: str) -> bytes:
    return hmac.new(chave, mensagem.encode("utf-8"), hashlib.sha256).digest()


def _chave_assinatura(segredo: str, datestamp: str, regiao: str, servico: str) -> bytes:
    k_data = _assinar(("AWS4" + segredo).encode("utf-8"), datestamp)
    k_regiao = _assinar(k_data, regiao)
    k_servico = _assinar(k_regiao, servico)
    return _assinar(k_servico, "aws4_request")


@dataclass(frozen=True)
class ObjetoInfo:
    tamanho: int
    etag: str
    content_type: str | None = None


class ClienteS3:
    """S3 path-style contra o Garage, uma chave de acesso por instância (RW ou RO de um inquilino)."""

    def __init__(self, endpoint: str, access_key: str, secret_key: str, regiao: str = "garage"):
        self.endpoint = endpoint.rstrip("/")
        self.host = urllib.parse.urlsplit(self.endpoint).netloc
        self.access_key = access_key
        self.secret_key = secret_key
        self.regiao = regiao

    def _assinar_requisicao(
        self, metodo: str, bucket: str, chave: str, corpo: bytes, query: str, extra: dict[str, str] | None
    ) -> dict[str, str]:
        agora = datetime.datetime.now(datetime.timezone.utc)
        amzdate = agora.strftime("%Y%m%dT%H%M%SZ")
        datestamp = agora.strftime("%Y%m%d")
        uri = urllib.parse.quote(f"/{bucket}/{chave}" if chave else f"/{bucket}", safe="/")
        payload_hash = hashlib.sha256(corpo).hexdigest()
        cabecalhos = {"host": self.host, "x-amz-content-sha256": payload_hash, "x-amz-date": amzdate}
        if extra:
            cabecalhos.update(extra)
        chaves_ordenadas = sorted(cabecalhos.keys())
        canonical_headers = "".join(f"{k}:{cabecalhos[k]}\n" for k in chaves_ordenadas)
        signed_headers = ";".join(chaves_ordenadas)
        canonical_request = "\n".join(
            [metodo, uri, query, canonical_headers, signed_headers, payload_hash]
        )
        escopo = f"{datestamp}/{self.regiao}/{SERVICO}/aws4_request"
        string_to_sign = "\n".join(
            ["AWS4-HMAC-SHA256", amzdate, escopo, hashlib.sha256(canonical_request.encode()).hexdigest()]
        )
        chave_assinatura = _chave_assinatura(self.secret_key, datestamp, self.regiao, SERVICO)
        assinatura = hmac.new(chave_assinatura, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        auth = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{escopo}, "
            f"SignedHeaders={signed_headers}, Signature={assinatura}"
        )
        saida = {k: v for k, v in cabecalhos.items() if k != "host"}
        saida["Authorization"] = auth
        return saida

    def _requisicao(
        self,
        metodo: str,
        bucket: str,
        chave: str = "",
        corpo: bytes = b"",
        query: str = "",
        extra: dict[str, str] | None = None,
        stream: bool = False,
    ) -> requests.Response:
        cabecalhos = self._assinar_requisicao(metodo, bucket, chave, corpo, query, extra)
        url = f"{self.endpoint}/{bucket}/{chave}" if chave else f"{self.endpoint}/{bucket}"
        if query:
            url += "?" + query
        return requests.request(
            metodo, url, headers=cabecalhos, data=corpo, timeout=TIMEOUT_S, stream=stream
        )

    # ---------------------------------------------------------------- objeto único
    def put(self, bucket: str, chave: str, dados: bytes, content_type: str = "application/octet-stream") -> str:
        r = self._requisicao("PUT", bucket, chave, corpo=dados, extra={"content-type": content_type})
        if r.status_code != 200:
            raise _erro_escrita(f"PUT {bucket}/{chave}", r.status_code, r.text)
        return (r.headers.get("etag") or "").strip('"')

    def get(self, bucket: str, chave: str) -> bytes:
        r = self._requisicao("GET", bucket, chave)
        if r.status_code == 404:
            raise FileNotFoundError(f"{bucket}/{chave}")
        if r.status_code != 200:
            raise ErroGarage(f"GET {bucket}/{chave}: {r.status_code} {r.text[:300]}")
        return r.content

    def get_stream(self, bucket: str, chave: str, pedaco_bytes: int = 1024 * 1024):
        """Iterador de bytes (GET com stream=True): usado por parte_concluir para calcular o sha256 do objeto
        completo sem carregá-lo inteiro na memória (ADR 0005: "sha256 do objeto lido de volta em stream")."""
        r = self._requisicao("GET", bucket, chave, stream=True)
        if r.status_code == 404:
            raise FileNotFoundError(f"{bucket}/{chave}")
        if r.status_code != 200:
            raise ErroGarage(f"GET (stream) {bucket}/{chave}: {r.status_code}")
        yield from r.iter_content(chunk_size=pedaco_bytes)

    def get_intervalo(self, bucket: str, chave: str, inicio: int, fim: int) -> bytes:
        """Bytes [inicio, fim] inclusive (cabeçalho Range), para leitura parcial (ex.: cabeçalho central de zip)."""
        r = self._requisicao("GET", bucket, chave, extra={"range": f"bytes={inicio}-{fim}"})
        if r.status_code == 404:
            raise FileNotFoundError(f"{bucket}/{chave}")
        if r.status_code not in (200, 206):
            raise ErroGarage(f"GET (range) {bucket}/{chave}: {r.status_code} {r.text[:300]}")
        return r.content

    def head(self, bucket: str, chave: str) -> ObjetoInfo | None:
        r = self._requisicao("HEAD", bucket, chave)
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise ErroGarage(f"HEAD {bucket}/{chave}: {r.status_code}")
        return ObjetoInfo(
            tamanho=int(r.headers.get("content-length") or 0),
            etag=(r.headers.get("etag") or "").strip('"'),
            content_type=r.headers.get("content-type"),
        )

    def delete(self, bucket: str, chave: str) -> bool:
        r = self._requisicao("DELETE", bucket, chave)
        if r.status_code not in (204, 404):
            raise ErroGarage(f"DELETE {bucket}/{chave}: {r.status_code} {r.text[:300]}")
        return r.status_code == 204

    def copiar(self, bucket: str, origem: str, destino: str, bucket_origem: str | None = None) -> None:
        """CopyObject dentro do balde (`bucket_origem=None`) ou de OUTRO balde (a refutação do L1-01-d tenta isso
        com a chave só-leitura: o Garage recusa, é o que o teste prova)."""
        fonte = f"/{bucket_origem or bucket}/{origem}"
        r = self._requisicao("PUT", bucket, destino, extra={"x-amz-copy-source": fonte})
        if r.status_code != 200:
            raise _erro_escrita(f"COPY {fonte} -> {bucket}/{destino}", r.status_code, r.text)

    def listar_buckets(self) -> list[str]:
        """ListBuckets do S3: os baldes que ESTA chave enxerga (o Garage só lista os que a chave tem permissão)."""
        import xml.etree.ElementTree as ET

        r = self._requisicao("GET", "")
        if r.status_code != 200:
            raise ErroGarage(f"ListBuckets: {r.status_code} {r.text[:300]}")
        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        root = ET.fromstring(r.text)
        return [b.findtext("s3:Name", default="", namespaces=ns) for b in root.iter("{%s}Bucket" % ns["s3"])]

    def listar(self, bucket: str, prefixo: str = "", max_chaves: int = 1000) -> list[dict[str, Any]]:
        import xml.etree.ElementTree as ET

        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        saida: list[dict[str, Any]] = []
        continuation = ""
        while True:
            query = f"list-type=2&max-keys={max_chaves}"
            if prefixo:
                query += f"&prefix={urllib.parse.quote(prefixo, safe='')}"
            if continuation:
                query += f"&continuation-token={urllib.parse.quote(continuation, safe='')}"
            r = self._requisicao("GET", bucket, query=query)
            if r.status_code != 200:
                raise ErroGarage(f"LIST {bucket} (prefixo={prefixo!r}): {r.status_code} {r.text[:300]}")
            root = ET.fromstring(r.text)
            for c in root.findall("s3:Contents", ns):
                saida.append(
                    {
                        "chave": c.findtext("s3:Key", default="", namespaces=ns),
                        "bytes": int(c.findtext("s3:Size", default="0", namespaces=ns)),
                        "etag": (c.findtext("s3:ETag", default="", namespaces=ns) or "").strip('"'),
                    }
                )
            truncado = (root.findtext("s3:IsTruncated", default="false", namespaces=ns) or "false").lower() == "true"
            if not truncado:
                break
            continuation = root.findtext("s3:NextContinuationToken", default="", namespaces=ns) or ""
            if not continuation:
                break
        return saida

    # ---------------------------------------------------------------- multipart (contrato ADR 0005 seção 11.3
    # estendida: parte_iniciar/parte_enviar/parte_concluir/parte_abortar)
    def multipart_iniciar(self, bucket: str, chave: str, content_type: str = "application/octet-stream") -> str:
        r = self._requisicao("POST", bucket, chave, query="uploads=", extra={"content-type": content_type})
        if r.status_code != 200:
            raise ErroGarage(f"CreateMultipartUpload {bucket}/{chave}: {r.status_code} {r.text[:300]}")
        import xml.etree.ElementTree as ET

        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        root = ET.fromstring(r.text)
        upload_id = root.findtext("s3:UploadId", default="", namespaces=ns)
        if not upload_id:
            raise ErroGarage(f"CreateMultipartUpload {bucket}/{chave}: sem UploadId na resposta")
        return upload_id

    def multipart_enviar_parte(self, bucket: str, chave: str, upload_id: str, numero: int, dados: bytes) -> str:
        r = self._requisicao("PUT", bucket, chave, corpo=dados, query=f"partNumber={numero}&uploadId={upload_id}")
        if r.status_code != 200:
            raise _erro_escrita(f"UploadPart {bucket}/{chave} #{numero}", r.status_code, r.text)
        return (r.headers.get("etag") or "").strip('"')

    def multipart_concluir(
        self, bucket: str, chave: str, upload_id: str, partes: list[tuple[int, str]]
    ) -> str:
        corpo_xml = "<CompleteMultipartUpload>" + "".join(
            f"<Part><PartNumber>{n}</PartNumber><ETag>&quot;{etag}&quot;</ETag></Part>" for n, etag in partes
        ) + "</CompleteMultipartUpload>"
        r = self._requisicao("POST", bucket, chave, corpo=corpo_xml.encode("utf-8"), query=f"uploadId={upload_id}")
        if r.status_code != 200:
            raise _erro_escrita(f"CompleteMultipartUpload {bucket}/{chave}", r.status_code, r.text)
        return r.text

    def multipart_abortar(self, bucket: str, chave: str, upload_id: str) -> None:
        r = self._requisicao("DELETE", bucket, chave, query=f"uploadId={upload_id}")
        if r.status_code not in (204, 404):
            raise ErroGarage(f"AbortMultipartUpload {bucket}/{chave}: {r.status_code} {r.text[:300]}")


class ClienteAdmin:
    """Admin API v2 do Garage (:3903, Bearer). Idempotente onde o portão exige (instalação repetível, D5)."""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token

    def _chamar(self, metodo: str, caminho: str, corpo: dict | None = None) -> Any:
        r = requests.request(
            metodo,
            f"{self.url}{caminho}",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json=corpo,
            timeout=TIMEOUT_S,
        )
        if r.status_code >= 300:
            raise ErroGarage(f"admin {metodo} {caminho}: {r.status_code} {r.text[:400]}")
        return r.json() if r.content else None

    def listar_buckets(self) -> list[dict]:
        return self._chamar("GET", "/v2/ListBuckets")

    def bucket_por_alias(self, alias: str) -> dict | None:
        for b in self.listar_buckets():
            if alias in (b.get("globalAliases") or []):
                return b
        return None

    def criar_bucket(self, alias: str) -> dict:
        """Idempotente: devolve o bucket existente se o alias já existir."""
        existente = self.bucket_por_alias(alias)
        if existente is not None:
            return existente
        return self._chamar("POST", "/v2/CreateBucket", {"globalAlias": alias})

    def info_bucket(self, bucket_id: str) -> dict:
        return self._chamar("GET", f"/v2/GetBucketInfo?id={bucket_id}")

    def definir_cota(self, bucket_id: str, max_bytes: int, max_objetos: int | None = None) -> dict:
        """Cota do balde em bytes e, quando dada, em objetos (item L1-01-d; `maxObjects: null` = sem limite de
        objetos, que era o comportamento do L0-11). Campo `quotas` do UpdateBucket v2, MEDIDO nesta instância."""
        return self._chamar(
            "POST",
            f"/v2/UpdateBucket?id={bucket_id}",
            {"quotas": {"maxSize": int(max_bytes), "maxObjects": int(max_objetos) if max_objetos else None}},
        )

    def definir_web(self, bucket_id: str, ativo: bool) -> dict:
        """Liga/desliga o endpoint web do balde (:3902, Host `<alias>.web.garage.localhost`): leitura ANÔNIMA
        por HTTP só nesse endpoint, atrás do nginx com auth_request (ADR 20260908T1255). MEDIDO 06/09/2026: com o web
        ligado, GET/LIST anônimos no endpoint S3 (:3900) continuam 403 — o web não abre a API S3."""
        acesso = {"enabled": True, "indexDocument": "index.html", "errorDocument": "error.html"} if ativo \
            else {"enabled": False}
        return self._chamar("POST", f"/v2/UpdateBucket?id={bucket_id}", {"websiteAccess": acesso})

    def listar_chaves(self) -> list[dict]:
        return self._chamar("GET", "/v2/ListKeys")

    def chave_por_nome(self, nome: str) -> dict | None:
        for k in self.listar_chaves():
            if k.get("name") == nome:
                return k
        return None

    def criar_chave(self, nome: str) -> dict:
        """Idempotente por NOME: uma chave já existente com o mesmo nome não gera segredo novo (o segredo antigo
        continua sendo o que está gravado em `plat.arquivo_bucket`; só a criação é idempotente, não a rotação).

        Achado nesta verificação: `ListKeys` (usado por `chave_por_nome`) devolve um RESUMO da chave — campo
        `id`, sem `accessKeyId`/`secretAccessKey` — enquanto `CreateKey` devolve o objeto completo. Devolver o
        resumo direto quebrava `garantir_bucket` (`rw["accessKeyId"]`) sempre que a chave já existisse no Garage
        mas a linha de `plat.arquivo_bucket` não (base recriada sem apagar o bucket external, ex.: trilha
        recriada com o schema dropado — o Garage não é dropado junto). Corrigido: no caminho idempotente, busca
        o objeto completo por `GetKeyInfo?showSecretKey=true` (Garage guarda o segredo e devolve de novo; não é
        rotação, é a MESMA chave)."""
        existente = self.chave_por_nome(nome)
        if existente is not None:
            log.info("garage: chave %s já existe (id=%s), reaproveitada sem novo segredo", nome, existente["id"])
            return self._chamar("GET", f"/v2/GetKeyInfo?id={existente['id']}&showSecretKey=true")
        return self._chamar("POST", "/v2/CreateKey", {"name": nome})

    def permitir(self, bucket_id: str, chave_id: str, *, ler: bool, escrever: bool, dono: bool) -> dict:
        return self._chamar(
            "POST",
            "/v2/AllowBucketKey",
            {
                "bucketId": bucket_id,
                "accessKeyId": chave_id,
                "permissions": {"read": ler, "write": escrever, "owner": dono},
            },
        )

    def apagar_chave(self, chave_id: str) -> None:
        self._chamar("POST", f"/v2/DeleteKey?id={chave_id}")

    def apagar_bucket(self, bucket_id: str) -> None:
        self._chamar("POST", f"/v2/DeleteBucket?id={bucket_id}")
