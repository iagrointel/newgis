"""Destino do backup no Garage (item L0-06-a): bucket próprio '<prefixo>backup' (não é bucket de inquilino),
chave RW única guardada em `plat.backup_destino` (funções SECURITY DEFINER da migração 20260906T2125 — a
tarefa roda no inquilino técnico e a RLS esconde a linha de todo o resto). Provisão idempotente, mesmo
padrão de `app/objetos.py::garantir_bucket`: a chave só nasce uma vez porque o Garage nunca devolve o
segredo de novo. Envio em multipart de 32 MB acima de 32 MB (o dump de produção passa disso e o
`put` inteiro na memória estouraria o RLIMIT do filho). Destino externo S3 opcional por variáveis
PLAT_BACKUP_EXTERNO_* (rclone ausente na máquina; a cópia é pela mesma API S3/SigV4 de app/garage.py)."""

import math
from pathlib import Path

from app.garage import ClienteAdmin, ClienteS3
from app.settings import settings

PARTE_BYTES = 32 * 1024 * 1024
PUT_DIRETO_ATE = 32 * 1024 * 1024


class ConfiguracaoAusente(RuntimeError):
    """Falta configuração obrigatória do destino de backup; a mensagem nomeia a chave."""


def _admin() -> ClienteAdmin:
    if not settings.PLAT_GARAGE_ADMIN_URL or not settings.PLAT_GARAGE_ADMIN_TOKEN:
        raise ConfiguracaoAusente("PLAT_GARAGE_ADMIN_URL e PLAT_GARAGE_ADMIN_TOKEN são obrigatórios para o backup")
    return ClienteAdmin(settings.PLAT_GARAGE_ADMIN_URL, settings.PLAT_GARAGE_ADMIN_TOKEN)


def garantir_bucket(cur) -> dict:
    """Linha {bucket_id, alias, chave_id, chave_segredo} do bucket de backup, criando bucket+chave na 1ª vez."""
    cur.execute("SELECT * FROM plat.backup_destino_ler()")
    linha = cur.fetchone()
    if linha is not None:
        return dict(linha)
    if not settings.PLAT_GARAGE_URL:
        raise ConfiguracaoAusente("PLAT_GARAGE_URL é obrigatório para o backup")
    admin = _admin()
    alias = f"{settings.PLAT_GARAGE_BUCKET_PREFIXO}backup"
    bucket = admin.criar_bucket(alias)
    chave = admin.criar_chave(f"{alias}-rw")
    ids = {k["accessKeyId"] for k in bucket.get("keys", [])}
    if chave["accessKeyId"] not in ids:
        admin.permitir(bucket["id"], chave["accessKeyId"], ler=True, escrever=True, dono=True)
    cur.execute(
        "SELECT plat.backup_destino_registrar(%s, %s, %s, %s)",
        (bucket["id"], alias, chave["accessKeyId"], chave["secretAccessKey"]),
    )
    cur.execute("SELECT * FROM plat.backup_destino_ler()")
    return dict(cur.fetchone())


def cliente_garage(linha: dict) -> ClienteS3:
    return ClienteS3(settings.PLAT_GARAGE_URL, linha["chave_id"], linha["chave_segredo"],
                     settings.PLAT_GARAGE_REGIAO)


def cliente_externo() -> tuple[ClienteS3, str] | None:
    """(cliente, bucket) do destino externo quando as 4 chaves PLAT_BACKUP_EXTERNO_* estão no ambiente."""
    url = settings.PLAT_BACKUP_EXTERNO_URL
    bucket = settings.PLAT_BACKUP_EXTERNO_BUCKET
    chave = settings.PLAT_BACKUP_EXTERNO_CHAVE
    segredo = settings.PLAT_BACKUP_EXTERNO_SEGREDO
    if not any((url, bucket, chave, segredo)):
        return None
    if not all((url, bucket, chave, segredo)):
        faltando = [n for n, v in (("PLAT_BACKUP_EXTERNO_URL", url), ("PLAT_BACKUP_EXTERNO_BUCKET", bucket),
                                   ("PLAT_BACKUP_EXTERNO_CHAVE", chave), ("PLAT_BACKUP_EXTERNO_SEGREDO", segredo))
                    if not v]
        raise ConfiguracaoAusente(f"destino externo de backup incompleto: faltam {', '.join(faltando)}")
    return ClienteS3(url, chave, segredo, settings.PLAT_BACKUP_EXTERNO_REGIAO or "garage"), bucket


def enviar_arquivo(cliente: ClienteS3, bucket: str, chave: str, caminho: Path) -> None:
    """PUT direto até 32 MB; acima disso multipart em partes de 32 MB lidas do disco (nunca o dump inteiro
    na memória — o filho tem RLIMIT_DATA)."""
    tamanho = caminho.stat().st_size
    if tamanho <= PUT_DIRETO_ATE:
        cliente.put(bucket, chave, caminho.read_bytes())
        return
    upload_id = cliente.multipart_iniciar(bucket, chave)
    partes: list[tuple[int, str]] = []
    try:
        with open(caminho, "rb") as f:
            for numero in range(1, math.ceil(tamanho / PARTE_BYTES) + 1):
                dados = f.read(PARTE_BYTES)
                etag = cliente.multipart_enviar_parte(bucket, chave, upload_id, numero, dados)
                partes.append((numero, etag))
        cliente.multipart_concluir(bucket, chave, upload_id, partes)
    except BaseException:
        try:
            cliente.multipart_abortar(bucket, chave, upload_id)
        finally:
            raise
