"""ADVERSÁRIO INDEPENDENTE do item L1-01-d-garage-por-inquilino (turno 3).

Quem escreve aqui não participou da construção. Cada afirmação do construtor é reproduzida com um
cliente S3 de terceiro (boto3) ou com HTTP cru, nunca pelo adaptador da casa, e o que expõe defeito
fica `xfail(strict=True)`: falha de propósito hoje e vira alarme no dia em que o defeito for corrigido.

Ataques:
 1. a chave só-leitura é MESMO só leitura — treze verbos de escrita da API S3 mais a Admin API;
 2. cruzado de verdade — a chave de A contra o balde de B por travessia, codificação dupla, nome
    parecido (`...-demo` × `...-demo2`), endereço virtual e caminho, com controle positivo (B lê B);
 3. a cota é do Garage ou é conferência prévia — multipart somando acima do limite, cota de OBJETOS
    estourada de um em um, e dez gravações CONCORRENTES contra o mesmo balde;
 4. nunca sobrescrever — mesma chave por multipart, CopyObject sobre si mesma, e a versão 1 conferida
    byte a byte no fim;
 5. faixa de bytes — inválida, aberta, além do fim, múltiplas faixas, e o token no caminho (não pode
    ser adivinhado nem servir a outro inquilino);
 6. a ressalva do próprio construtor: ListBuckets responde 200 com a chave só-leitura.

Baldes: os do ambiente de teste em uso (prefixo `PLAT_GARAGE_BUCKET_PREFIXO`), inquilinos `demo` e
`demo2` já semeados. Nenhum balde novo é criado; todo objeto criado começa por `zadv/` e é apagado no
fim do módulo (o disco desta máquina é apertado e o Garage é compartilhado).
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import secrets
import socket
import subprocess
import threading
import time
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente

RAIZ = Path(__file__).resolve().parents[2]
MEDIDAS: dict = {"item": "L1-01-d-garage-por-inquilino", "papel": "adversario", "ataques": {}}
PREFIXO = "zadv"


# ---------------------------------------------------------------- apoio
def _schema() -> str:
    from app.settings import settings

    return settings.PLAT_SCHEMA


def _contexto(con, tenant_id: int) -> None:
    with con.cursor() as cur:
        cur.execute(f"SET search_path = {_schema()}, public")
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
            "set_config('plat.login', %s, true)",
            (str(tenant_id), "0", "adversario"),
        )


def _ids(con) -> dict[str, int]:
    """Os ids de demo/demo2 pela função SECURITY DEFINER, como no test_rls: a role da aplicação não
    enxerga a tabela `tenant` sem contexto."""
    saida = {}
    with con.cursor() as cur:
        cur.execute(f"SET search_path = {_schema()}, public")
        for slug in ("demo", "demo2"):
            cur.execute("SELECT tenant_id FROM plat.auth_login(%s, 'admin')", (slug,))
            linha = cur.fetchone()
            if linha is None:
                pytest.skip(f"admin de {slug} não semeado neste ambiente")
            saida[slug] = linha["tenant_id"]
    con.rollback()
    return saida


def _boto3(bucket: dict, *, ro: bool, estilo: str = "path"):
    import boto3
    from botocore.config import Config

    from app.settings import settings

    return boto3.client(
        "s3",
        endpoint_url=settings.PLAT_GARAGE_URL,
        aws_access_key_id=bucket["chave_ro_id"] if ro else bucket["chave_rw_id"],
        aws_secret_access_key=bucket["chave_ro_segredo"] if ro else bucket["chave_rw_segredo"],
        region_name=settings.PLAT_GARAGE_REGIAO,
        config=Config(signature_version="s3v4", s3={"addressing_style": estilo}, retries={"max_attempts": 1}),
    )


def _status(excecao) -> int:
    r = getattr(excecao, "response", {}) or {}
    return int(r.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0)


def _codigo(excecao) -> str:
    r = getattr(excecao, "response", {}) or {}
    return str(r.get("Error", {}).get("Code") or _status(excecao) or excecao)


def _porta_viva(porta: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, porta)) == 0


def _limpar(bucket: dict) -> None:
    cli = _boto3(bucket, ro=False)
    alias = bucket["bucket_alias"]
    for u in (cli.list_multipart_uploads(Bucket=alias).get("Uploads") or []):
        if u["Key"].startswith(PREFIXO):
            cli.abort_multipart_upload(Bucket=alias, Key=u["Key"], UploadId=u["UploadId"])
    token = None
    while True:
        kw = {"Bucket": alias, "Prefix": PREFIXO}
        if token:
            kw["ContinuationToken"] = token
        r = cli.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            cli.delete_object(Bucket=alias, Key=o["Key"])
        token = r.get("NextContinuationToken")
        if not token:
            break


@pytest.fixture(scope="module")
def ambiente(env):
    """Baldes de A (`demo`) e B (`demo2`) com um objeto-alvo em cada, e a cota original de A guardada
    para ser devolvida no fim. Conexão própria: o módulo inteiro compartilha o estado."""
    from app import objetos

    # cursor da PRÓPRIA aplicação (reescreve `plat.` para o schema do ambiente): sem ele o teste só rodaria
    # contra o schema de produção, e o adversário precisa rodar no ambiente isolado da trilha.
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    baldes: dict[str, dict] = {}
    cotas_originais: dict[str, tuple[int, int]] = {}
    try:
        ids = _ids(con)
        for slug, tid in ids.items():
            _contexto(con, tid)
            with con.cursor() as cur:
                cur.execute("SELECT cota_bytes, cota_objetos FROM plat.tenant WHERE id = %s", (tid,))
                c = cur.fetchone()
                cotas_originais[slug] = (int(c["cota_bytes"]), int(c["cota_objetos"]))
                baldes[slug] = dict(objetos.garantir_bucket(cur, tid, slug, web=True))
            con.commit()
        alvos = {}
        for slug in ("demo", "demo2"):
            cli = _boto3(baldes[slug], ro=False)
            corpo = (f"objeto de {slug} para a refutacao. ".encode()) * 64
            chave = f"{PREFIXO}/alvo_{hashlib.sha256(corpo).hexdigest()[:8]}.bin"
            cli.put_object(Bucket=baldes[slug]["bucket_alias"], Key=chave, Body=corpo)
            alvos[slug] = {"chave": chave, "corpo": corpo, "sha": hashlib.sha256(corpo).hexdigest()}
        yield {"ids": ids, "baldes": baldes, "alvos": alvos, "con": con, "cotas": cotas_originais}
    finally:
        for slug, b in baldes.items():
            try:
                _limpar(b)
            except Exception as e:
                print(f"AVISO: limpeza do balde de {slug} falhou: {e}")
        # devolve as cotas do banco e do Garage ao que eram antes
        for slug, (cb, co) in cotas_originais.items():
            try:
                tid = ids[slug]
                _contexto(con, tid)
                with con.cursor() as cur:
                    cur.execute(
                        "UPDATE plat.tenant SET cota_bytes = %s, cota_objetos = %s WHERE id = %s",
                        (cb, co, tid),
                    )
                    objetos.garantir_bucket(cur, tid, slug, forcar=True)
                con.commit()
            except Exception as e:
                print(f"AVISO: cota de {slug} não foi restaurada: {e}")
        con.close()


# ================================================================ ataque 1: a chave RO escreve?
ESCRITAS = [
    "PutObject", "DeleteObject", "DeleteObjects", "CopyObject_mesmo_balde", "CopyObject_entre_baldes",
    "CreateMultipartUpload", "PutObjectAcl", "PutBucketPolicy", "PutBucketCors", "PutObjectTagging",
    "RestoreObject", "CreateBucket", "DeleteBucket",
]


def _tentar_escrita(nome: str, cli, alias: str, alias_b: str, chave: str) -> tuple[bool, str]:
    """(escreveu?, código devolvido). `escreveu=True` é a refutação do item."""
    try:
        if nome == "PutObject":
            cli.put_object(Bucket=alias, Key=f"{PREFIXO}/invasao.bin", Body=b"invasao")
        elif nome == "DeleteObject":
            cli.delete_object(Bucket=alias, Key=chave)
        elif nome == "DeleteObjects":
            r = cli.delete_objects(Bucket=alias, Delete={"Objects": [{"Key": chave}], "Quiet": False})
            if r.get("Errors"):
                return False, str(r["Errors"][0].get("Code"))
        elif nome == "CopyObject_mesmo_balde":
            cli.copy_object(Bucket=alias, Key=f"{PREFIXO}/copia.bin", CopySource=f"{alias}/{chave}")
        elif nome == "CopyObject_entre_baldes":
            cli.copy_object(Bucket=alias_b, Key=f"{PREFIXO}/copia.bin", CopySource=f"{alias}/{chave}")
        elif nome == "CreateMultipartUpload":
            cli.create_multipart_upload(Bucket=alias, Key=f"{PREFIXO}/mp.bin")
        elif nome == "PutObjectAcl":
            cli.put_object_acl(Bucket=alias, Key=chave, ACL="public-read")
        elif nome == "PutBucketPolicy":
            cli.put_bucket_policy(Bucket=alias, Policy=json.dumps(
                {"Version": "2012-10-17",
                 "Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:*",
                                "Resource": f"arn:aws:s3:::{alias}/*"}]}))
        elif nome == "PutBucketCors":
            cli.put_bucket_cors(Bucket=alias, CORSConfiguration={
                "CORSRules": [{"AllowedMethods": ["GET"], "AllowedOrigins": ["*"]}]})
        elif nome == "PutObjectTagging":
            cli.put_object_tagging(Bucket=alias, Key=chave,
                                   Tagging={"TagSet": [{"Key": "invadido", "Value": "sim"}]})
        elif nome == "RestoreObject":
            cli.restore_object(Bucket=alias, Key=chave, RestoreRequest={"Days": 1})
        elif nome == "CreateBucket":
            cli.create_bucket(Bucket=f"{PREFIXO}-balde-invasor")
        elif nome == "DeleteBucket":
            cli.delete_bucket(Bucket=alias)
        else:
            raise AssertionError(nome)
        return True, "200"
    except Exception as e:
        return False, _codigo(e)


def test_1_chave_so_leitura_nao_escreve_por_nenhum_verbo(ambiente):
    """Treze verbos de escrita da API S3 com a chave SÓ-LEITURA de A. Qualquer sucesso refuta o item.
    O objeto-alvo é conferido byte a byte depois de todas as tentativas."""
    a, b = ambiente["baldes"]["demo"], ambiente["baldes"]["demo2"]
    alvo = ambiente["alvos"]["demo"]
    ro = _boto3(a, ro=True)
    resultado = {}
    for nome in ESCRITAS:
        escreveu, codigo = _tentar_escrita(nome, ro, a["bucket_alias"], b["bucket_alias"], alvo["chave"])
        resultado[nome] = {"escreveu": escreveu, "codigo": codigo}
    passaram = [n for n, r in resultado.items() if r["escreveu"]]
    corpo = _boto3(a, ro=True).get_object(Bucket=a["bucket_alias"], Key=alvo["chave"])["Body"].read()
    MEDIDAS["ataques"]["1_escrita_com_chave_ro"] = {
        "verbos": resultado, "escritas_bem_sucedidas": passaram,
        "alvo_intacto": hashlib.sha256(corpo).hexdigest() == alvo["sha"],
    }
    assert not passaram, f"a chave só-leitura ESCREVEU: {passaram} — REFUTADO"
    assert hashlib.sha256(corpo).hexdigest() == alvo["sha"], "o objeto-alvo mudou durante as tentativas"


def test_1b_credencial_s3_nao_abre_a_admin_api(ambiente):
    """A Admin API do Garage (:3903) é Bearer com token próprio. A credencial S3 só-leitura — e a de
    escrita — não pode servir como token de administração (criar balde, mudar cota, dar permissão)."""
    import requests

    from app.settings import settings

    a = ambiente["baldes"]["demo"]
    tentativas = {}
    for rotulo, segredo in (
        ("chave_ro_id", a["chave_ro_id"]),
        ("chave_ro_segredo", a["chave_ro_segredo"]),
        ("chave_rw_segredo", a["chave_rw_segredo"]),
    ):
        r = requests.get(
            f"{settings.PLAT_GARAGE_ADMIN_URL}/v2/ListBuckets",
            headers={"Authorization": f"Bearer {segredo}"}, timeout=10,
        )
        tentativas[rotulo] = r.status_code
    MEDIDAS["ataques"]["1b_admin_api_com_credencial_s3"] = tentativas
    assert all(s in (401, 403) for s in tentativas.values()), f"a Admin API aceitou credencial S3: {tentativas}"


# ================================================================ ataque 2: cruzado de verdade
def test_2_controle_positivo_b_le_b(ambiente):
    """Controle positivo: sem isto o ataque 2 passaria por engano (uma chave que não lê NADA daria 403
    em tudo). A chave só-leitura de B lê o objeto de B e o sha256 bate."""
    b = ambiente["baldes"]["demo2"]
    alvo = ambiente["alvos"]["demo2"]
    corpo = _boto3(b, ro=True).get_object(Bucket=b["bucket_alias"], Key=alvo["chave"])["Body"].read()
    MEDIDAS["ataques"]["2_controle_positivo"] = {
        "balde": b["bucket_alias"], "bytes": len(corpo), "sha_bate": hashlib.sha256(corpo).hexdigest() == alvo["sha"],
    }
    assert hashlib.sha256(corpo).hexdigest() == alvo["sha"]


def test_2b_chave_de_a_nao_alcanca_b_por_nenhuma_forma(ambiente):
    """A chave só-leitura de A contra o balde de B: caminho direto, nome parecido (o alias de B é o de A
    com sufixo `2`), travessia com `..`, codificação de URL simples e dupla, e endereçamento virtual.
    Qualquer leitura bem-sucedida do conteúdo de B refuta o isolamento."""
    import requests

    from app.settings import settings

    a, b = ambiente["baldes"]["demo"], ambiente["baldes"]["demo2"]
    alvo_b = ambiente["alvos"]["demo2"]
    ro_a_path = _boto3(a, ro=True)
    ro_a_virtual = _boto3(a, ro=True, estilo="virtual")
    tentativas: dict[str, str] = {}

    def registrar(nome, fn):
        try:
            r = fn()
            corpo = r["Body"].read() if isinstance(r, dict) and "Body" in r else b""
            if corpo == alvo_b["corpo"]:
                tentativas[nome] = "LEU O CONTEUDO DE B"
            else:
                tentativas[nome] = "200 sem conteudo de B"
        except Exception as e:
            tentativas[nome] = _codigo(e)

    registrar("GetObject_balde_de_B", lambda: ro_a_path.get_object(Bucket=b["bucket_alias"], Key=alvo_b["chave"]))
    registrar("HeadObject_balde_de_B", lambda: ro_a_path.head_object(Bucket=b["bucket_alias"], Key=alvo_b["chave"]))
    registrar("ListObjects_balde_de_B", lambda: ro_a_path.list_objects_v2(Bucket=b["bucket_alias"]))
    registrar("HeadBucket_balde_de_B", lambda: ro_a_path.head_bucket(Bucket=b["bucket_alias"]))
    registrar("GetBucketLocation_de_B", lambda: ro_a_path.get_bucket_location(Bucket=b["bucket_alias"]))
    registrar("GetObject_virtualhost_de_B",
              lambda: ro_a_virtual.get_object(Bucket=b["bucket_alias"], Key=alvo_b["chave"]))
    registrar("GetObject_prefixo_do_alias_de_A",
              lambda: ro_a_path.get_object(Bucket=a["bucket_alias"], Key=alvo_b["chave"]))

    # travessia e codificação: requests cru, porque boto3 normaliza o caminho antes de assinar
    from app.garage import ClienteS3

    cli = ClienteS3(settings.PLAT_GARAGE_URL, a["chave_ro_id"], a["chave_ro_segredo"], settings.PLAT_GARAGE_REGIAO)
    sufixo = b["bucket_alias"].removeprefix(a["bucket_alias"])  # "2" quando os aliases são demo/demo2
    cruas = {
        "travessia_ponto_ponto": f"../{b['bucket_alias']}/{alvo_b['chave']}",
        "travessia_codificada": f"..%2F{b['bucket_alias']}%2F{alvo_b['chave']}",
        "travessia_codificada_dupla": f"..%252F{b['bucket_alias']}%252F{alvo_b['chave']}",
        "sufixo_no_nome_do_balde": f"{sufixo}/{alvo_b['chave']}" if sufixo else "n/a",
    }
    for nome, chave in cruas.items():
        if chave == "n/a":
            tentativas[nome] = "n/a"
            continue
        try:
            corpo = cli.get(a["bucket_alias"], chave)
            tentativas[nome] = "LEU O CONTEUDO DE B" if corpo == alvo_b["corpo"] else "200 sem conteudo de B"
        except FileNotFoundError:
            tentativas[nome] = "404"
        except Exception as e:
            tentativas[nome] = str(e)[:80]

    # o caminho cru montado à mão, sem passar pela assinatura do cliente da casa
    url = f"{settings.PLAT_GARAGE_URL}/{a['bucket_alias']}/../{b['bucket_alias']}/{alvo_b['chave']}"
    r = requests.get(url, timeout=10)
    tentativas["caminho_cru_sem_assinatura"] = f"{r.status_code}"
    if r.content == alvo_b["corpo"]:
        tentativas["caminho_cru_sem_assinatura"] = "LEU O CONTEUDO DE B"

    MEDIDAS["ataques"]["2b_cruzado"] = tentativas
    vazou = [n for n, v in tentativas.items() if v == "LEU O CONTEUDO DE B"]
    assert not vazou, f"a chave de A alcançou o conteúdo de B por: {vazou} — REFUTADO"


def test_2c_endpoint_web_do_garage_e_leitura_anonima_de_qualquer_balde(ambiente):
    """O bloco do nginx entrega o COG pelo endpoint WEB do Garage (:3902), que serve leitura ANÔNIMA e
    escolhe o balde pelo cabeçalho `Host`. Quem alcança essa porta lê QUALQUER balde de QUALQUER
    inquilino sem token e sem assinatura. Mede-se o alcance: a porta escuta só em 127.0.0.1, então o
    ataque é local (outro processo/usuário da máquina), não da internet. É fronteira do desenho, não
    defeito do código — por isso este teste AFIRMA o fato em vez de exigir 403."""
    import requests

    if not _porta_viva(3902):
        pytest.skip("endpoint web do Garage não está ouvindo")
    b = ambiente["baldes"]["demo2"]
    alvo = ambiente["alvos"]["demo2"]
    r = requests.get(
        f"http://127.0.0.1:3902/{alvo['chave']}",
        headers={"Host": f"{b['bucket_alias']}.web.garage.localhost"}, timeout=10,
    )
    escutas = subprocess.run(["ss", "-ltn"], capture_output=True, text=True).stdout
    so_local = "0.0.0.0:3902" not in escutas and ":::3902" not in escutas
    MEDIDAS["ataques"]["2c_web_anonimo"] = {
        "status": r.status_code, "leu_o_conteudo": r.content == alvo["corpo"],
        "porta_3902_so_em_127_0_0_1": so_local, "web_ativo_no_balde": bool(b["web_ativo"]),
    }
    assert so_local, "o endpoint web do Garage escuta fora de 127.0.0.1: o token do nginx deixa de ser barreira"
    if b["web_ativo"]:
        assert r.status_code == 200 and r.content == alvo["corpo"], (
            "com web_ativo o endpoint anônimo devia servir o objeto; se não serve, o bloco do nginx não funciona"
        )


# ================================================================ ataque 3: a cota é real?
def _definir_cota(con, tenant_id: int, slug: str, cota_bytes: int, cota_objetos: int) -> dict:
    from app import objetos

    _contexto(con, tenant_id)
    with con.cursor() as cur:
        cur.execute(
            "UPDATE plat.tenant SET cota_bytes = %s, cota_objetos = %s WHERE id = %s",
            (cota_bytes, cota_objetos, tenant_id),
        )
        linha = dict(objetos.garantir_bucket(cur, tenant_id, slug, forcar=True))
    con.commit()
    return linha


def test_3_cota_de_bytes_e_do_garage_nao_da_conferencia_previa(ambiente):
    """Multipart em partes que somam ACIMA da cota, mandado pela chave RW direto no Garage (a checagem
    prévia da casa nem é chamada). Se o `CompleteMultipartUpload` passar, a cota é conferência prévia."""
    from app import objetos

    con, tid = ambiente["con"], ambiente["ids"]["demo"]
    a = ambiente["baldes"]["demo"]
    alias = a["bucket_alias"]
    usado = int(objetos._admin().info_bucket(a["bucket_id"]).get("bytes", 0))
    parte = b"P" * (5 * 1024 * 1024)  # o mínimo de parte não-final do S3
    cota = usado + len(parte) + 1024  # cabe UMA parte, nunca duas
    linha = _definir_cota(con, tid, "demo", cota, ambiente["cotas"]["demo"][1])
    cli = _boto3(linha, ro=False)
    chave = f"{PREFIXO}/multipart_acima_da_cota.bin"
    resultado = {"cota_bytes": cota, "usado_antes": usado, "partes": 2, "bytes_enviados": 2 * len(parte)}
    upload = cli.create_multipart_upload(Bucket=alias, Key=chave)["UploadId"]
    try:
        etags = []
        for n in (1, 2):
            try:
                etags.append({"PartNumber": n, "ETag": cli.upload_part(
                    Bucket=alias, Key=chave, UploadId=upload, PartNumber=n, Body=parte)["ETag"]})
                resultado[f"parte_{n}"] = "aceita"
            except Exception as e:
                resultado[f"parte_{n}"] = _codigo(e)
        try:
            cli.complete_multipart_upload(
                Bucket=alias, Key=chave, UploadId=upload, MultipartUpload={"Parts": etags})
            resultado["concluir"] = "aceito"
        except Exception as e:
            resultado["concluir"] = _codigo(e)
        info = objetos._admin().info_bucket(a["bucket_id"])
        resultado["bytes_no_garage_depois"] = int(info.get("bytes", 0))
        resultado["ultrapassou_a_cota"] = resultado["bytes_no_garage_depois"] > cota
    finally:
        try:
            cli.abort_multipart_upload(Bucket=alias, Key=chave, UploadId=upload)
        except Exception:
            pass
        try:
            cli.delete_object(Bucket=alias, Key=chave)
        except Exception:
            pass
        _definir_cota(con, tid, "demo", *ambiente["cotas"]["demo"])
    MEDIDAS["ataques"]["3_multipart_acima_da_cota"] = resultado
    assert not resultado["ultrapassou_a_cota"], (
        f"o balde ficou com {resultado['bytes_no_garage_depois']} bytes sobre cota de {cota} — REFUTADO"
    )


def test_3b_cota_de_objetos_para_de_um_em_um(ambiente):
    """Objetos pequenos, um a um, até a cota de OBJETOS: o Garage tem de recusar exatamente no limite."""
    from app import objetos

    con, tid = ambiente["con"], ambiente["ids"]["demo"]
    a = ambiente["baldes"]["demo"]
    alias = a["bucket_alias"]
    info = objetos._admin().info_bucket(a["bucket_id"])
    objetos_agora = int(info.get("objects", 0))
    folga = 3
    cota_obj = objetos_agora + folga
    linha = _definir_cota(con, tid, "demo", ambiente["cotas"]["demo"][0], cota_obj)
    cli = _boto3(linha, ro=False)
    aceitos, recusados, criados = 0, [], []
    try:
        for n in range(folga + 3):
            chave = f"{PREFIXO}/pequeno_{n}.bin"
            try:
                cli.put_object(Bucket=alias, Key=chave, Body=b"x" * 16)
                aceitos += 1
                criados.append(chave)
            except Exception as e:
                recusados.append(_codigo(e))
        depois = int(objetos._admin().info_bucket(a["bucket_id"]).get("objects", 0))
    finally:
        for c in criados:
            try:
                cli.delete_object(Bucket=alias, Key=c)
            except Exception:
                pass
        _definir_cota(con, tid, "demo", *ambiente["cotas"]["demo"])
    MEDIDAS["ataques"]["3b_cota_de_objetos"] = {
        "objetos_antes": objetos_agora, "cota_objetos": cota_obj, "tentativas": folga + 3,
        "aceitos": aceitos, "recusados": len(recusados), "codigos": sorted(set(recusados)),
        "objetos_no_garage_depois": depois,
    }
    assert aceitos <= folga, f"o Garage aceitou {aceitos} objetos com folga de {folga} — REFUTADO"
    assert depois <= cota_obj, f"o balde ficou com {depois} objetos sobre cota de {cota_obj} — REFUTADO"


@pytest.mark.xfail(
    strict=True,
    reason="MEDIDO pelo adversário: a cota de bytes do Garage é conferida contra um contador que só converge "
           "DEPOIS da gravação. Trinta e duas gravações disparadas no mesmo instante num balde com folga para "
           "UMA entram quase todas e o balde termina muitas vezes acima do limite. O enforcement é sequencial, "
           "não concorrente — a cota segura um cliente de cada vez, não um worker paralelo.",
)
def test_3c_gravacoes_concorrentes_nao_furam_a_cota(ambiente):
    """Trinta e duas gravações de 16 KiB disparadas ao mesmo tempo (`threading.Barrier`) num balde com folga
    para UMA. Se a cota fosse limite duro, trinta e uma seriam recusadas. Objeto pequeno de propósito: o que
    abre a corrida não é a duração do envio, é o atraso do contador — com objetos de 4 MiB o envio demora mais
    que a convergência e a cota segura. Três rodadas independentes; vale a PIOR. Mede-se o que o Garage
    contabiliza depois (GetBucketInfo), nunca o que a checagem prévia da casa achou antes."""
    from app import objetos

    con, tid = ambiente["con"], ambiente["ids"]["demo"]
    a = ambiente["baldes"]["demo"]
    alias = a["bucket_alias"]
    tamanho = 16 * 1024
    corpo = b"C" * tamanho
    paralelas = 32
    rodadas = []
    try:
        for rodada in range(3):
            usado = int(objetos._admin().info_bucket(a["bucket_id"]).get("bytes", 0))
            cota = usado + tamanho + 1024  # cabe UMA
            linha = _definir_cota(con, tid, "demo", cota, ambiente["cotas"]["demo"][1])
            chaves = [f"{PREFIXO}/concorrente_{rodada}_{n}.bin" for n in range(paralelas)]
            portao = threading.Barrier(paralelas)

            def enviar(chave, bucket=linha, barreira=portao):
                cli = _boto3(bucket, ro=False)
                barreira.wait(timeout=60)  # as trinta e duas partem no mesmo instante
                try:
                    cli.put_object(Bucket=alias, Key=chave, Body=corpo)
                    return "aceito"
                except Exception as e:
                    return _codigo(e)

            with concurrent.futures.ThreadPoolExecutor(max_workers=paralelas) as ex:
                saidas = list(ex.map(enviar, chaves))
            depois = int(objetos._admin().info_bucket(a["bucket_id"]).get("bytes", 0))
            rodadas.append({
                "gravacoes_simultaneas": paralelas, "tamanho_cada": tamanho, "cabem_pela_cota": 1,
                "cota_bytes": cota, "aceitos": saidas.count("aceito"),
                "codigos_de_recusa": sorted(set(x for x in saidas if x != "aceito")),
                "bytes_no_garage_depois": depois, "sobra_sobre_a_cota": depois - cota,
                "razao": round(depois / cota, 2),
            })
            cli = _boto3(linha, ro=False)
            for c in chaves:
                try:
                    cli.delete_object(Bucket=alias, Key=c)
                except Exception:
                    pass
    finally:
        _definir_cota(con, tid, "demo", *ambiente["cotas"]["demo"])
    pior = max(rodadas, key=lambda r: r["razao"])
    MEDIDAS["ataques"]["3c_concorrencia"] = {"rodadas": rodadas, "pior": pior}
    assert pior["bytes_no_garage_depois"] <= pior["cota_bytes"], (
        f"{paralelas} gravações simultâneas deixaram {pior['bytes_no_garage_depois']} bytes numa cota de "
        f"{pior['cota_bytes']} ({pior['razao']}x o limite) — a cota do Garage tem corrida"
    )


# ================================================================ ataque 4: nunca sobrescrever
@pytest.mark.xfail(
    strict=True,
    reason="MEDIDO pelo adversário: 'nunca sobrescrever' é regra do ADAPTADOR (HEAD antes do PUT), não do "
           "armazenamento. Com a chave RW o Garage sobrescreve a mesma chave por PutObject, por multipart "
           "e por CopyObject sobre si mesma.",
)
def test_4_a_mesma_chave_e_sobrescrita_no_garage_apesar_do_adaptador(ambiente):
    """A regra "nunca sobrescrever" é do ADAPTADOR (`HEAD` antes de gravar), não do Garage. Qualquer
    processo com a chave RW — o worker, um script, um erro de código — sobrescreve a mesma chave por
    PutObject, por multipart e por CopyObject sobre si mesma. Este teste mede a fronteira: o alvo é
    sobrescrito de verdade, e o que protege o objeto é convenção da aplicação, não o armazenamento."""
    a = ambiente["baldes"]["demo"]
    alias = a["bucket_alias"]
    cli = _boto3(a, ro=False)
    chave = f"{PREFIXO}/sobrescrita.bin"
    v1 = b"versao 1 " * 100
    cli.put_object(Bucket=alias, Key=chave, Body=v1)
    medida = {"sha_v1": hashlib.sha256(v1).hexdigest()}
    try:
        v2 = b"versao 2 " * 100
        cli.put_object(Bucket=alias, Key=chave, Body=v2)
        lido = cli.get_object(Bucket=alias, Key=chave)["Body"].read()
        medida["put_sobrescreveu"] = lido == v2
        # multipart na MESMA chave
        v3 = b"V" * (5 * 1024 * 1024 + 7)
        up = cli.create_multipart_upload(Bucket=alias, Key=chave)["UploadId"]
        etag = cli.upload_part(Bucket=alias, Key=chave, UploadId=up, PartNumber=1, Body=v3)["ETag"]
        cli.complete_multipart_upload(
            Bucket=alias, Key=chave, UploadId=up, MultipartUpload={"Parts": [{"PartNumber": 1, "ETag": etag}]})
        medida["multipart_sobrescreveu"] = cli.head_object(Bucket=alias, Key=chave)["ContentLength"] == len(v3)
        # CopyObject sobre si mesma
        try:
            cli.copy_object(Bucket=alias, Key=chave, CopySource=f"{alias}/{chave}")
            medida["copy_sobre_si_mesma"] = "aceito"
        except Exception as e:
            medida["copy_sobre_si_mesma"] = _codigo(e)
    finally:
        try:
            cli.delete_object(Bucket=alias, Key=chave)
        except Exception:
            pass
    MEDIDAS["ataques"]["4_sobrescrita_no_garage"] = medida
    assert not medida["put_sobrescreveu"], "o Garage sobrescreveu a mesma chave por PutObject"


def test_4b_adaptador_recusa_a_mesma_chave_e_a_versao_1_fica_intacta(ambiente):
    """O que o adaptador promete: `guardar_bytes` na mesma chave levanta `ObjetoJaExiste`, e conteúdo
    diferente ganha chave diferente (o sha8 muda). Depois de tudo, a versão 1 é conferida byte a byte."""
    from app import objetos_raster

    con, tid = ambiente["con"], ambiente["ids"]["demo"]
    item = f"{PREFIXO}item"
    v1 = b"conteudo original do adversario " * 40
    _contexto(con, tid)
    with con.cursor() as cur:
        g1 = objetos_raster.guardar_bytes(cur, item, "cog", v1)
    con.commit()
    medida = {"chave_v1": g1["chave"], "sha8_v1": g1["sha8"]}
    try:
        _contexto(con, tid)
        with con.cursor() as cur:
            with pytest.raises(objetos_raster.ObjetoJaExiste):
                objetos_raster.guardar_bytes(cur, item, "cog", v1)
        con.rollback()
        v2 = b"conteudo DIFERENTE do adversario " * 40
        _contexto(con, tid)
        with con.cursor() as cur:
            g2 = objetos_raster.guardar_bytes(cur, item, "cog", v2)
        con.commit()
        medida["chave_v2"] = g2["chave"]
        medida["chaves_diferentes"] = g1["chave"] != g2["chave"]
        lido = objetos_raster.ler_intervalo(g1["chave"], 0, len(v1) - 1)
        medida["v1_intacta_byte_a_byte"] = lido == v1
    finally:
        _contexto(con, tid)
        with con.cursor() as cur:
            objetos_raster.apagar_item(cur, item)
        con.commit()
    MEDIDAS["ataques"]["4b_adaptador_nao_sobrescreve"] = medida
    assert medida["chaves_diferentes"] and medida["v1_intacta_byte_a_byte"]


# ================================================================ ataque 5: faixa de bytes
@pytest.fixture(scope="module")
def nginx_cog(ambiente, tmp_path_factory):
    """nginx PRÓPRIO na 8173 com o bloco de deploy/nginx.conf (o mesmo recorte que o construtor usa), um
    objeto de ~3 MiB no balde de A e um token de serviço de A. Devolve tudo o que o ataque 5 precisa."""
    import ssl

    from app import objetos_raster
    from app.settings import settings

    porta_api = int(os.environ.get("PLAT_TESTE_API_PORTA", "8171"))
    if not _porta_viva(porta_api):
        pytest.skip(f"API não está ouvindo em 127.0.0.1:{porta_api}")
    if not _porta_viva(3902):
        pytest.skip("endpoint web do Garage não está ouvindo")

    con, tid = ambiente["con"], ambiente["ids"]["demo"]
    dados = os.urandom(3 * 1024 * 1024 + 777)
    _contexto(con, tid)
    with con.cursor() as cur:
        gravado = objetos_raster.guardar_bytes(cur, f"{PREFIXO}range", "cog", dados)
    con.commit()

    from tests.api.conftest import credenciais, entrar, novo_cliente

    cliente_a = novo_cliente()
    login, senha = credenciais()["demo"]
    assert entrar(cliente_a, "demo", login, senha).status_code == 200
    tok_a = cliente_a.post(
        "/api/tokens", json={"nome": f"{PREFIXO}-cog-{secrets.token_hex(3)}", "escopos": ["admin:inquilino"]}
    )
    assert tok_a.status_code == 201, tok_a.text
    token_a = tok_a.json()
    cliente_b = novo_cliente()
    login_b, senha_b = credenciais()["demo2"]
    assert entrar(cliente_b, "demo2", login_b, senha_b).status_code == 200
    tok_b = cliente_b.post(
        "/api/tokens", json={"nome": f"{PREFIXO}-cog-{secrets.token_hex(3)}", "escopos": ["admin:inquilino"]}
    )
    assert tok_b.status_code == 201, tok_b.text
    token_b = tok_b.json()

    prefixo = tmp_path_factory.mktemp("nginx_adv")
    (prefixo / "logs").mkdir()
    (prefixo / "cache").mkdir()
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=localhost",
         "-keyout", str(prefixo / "k.pem"), "-out", str(prefixo / "c.pem")], check=True, capture_output=True)
    modelo = (RAIZ / "deploy" / "nginx.conf").read_text(encoding="utf-8")
    bloco = modelo[modelo.index("    # ── COG por inquilino"):modelo.index("    location / {")]
    bloco = bloco.replace("PORTA", str(porta_api)).replace(
        "PREFIXO_BALDE", settings.PLAT_GARAGE_BUCKET_PREFIXO).replace(
        "proxy_cache plat_cog;", "proxy_cache plat_cog_adv;")
    conf = prefixo / "nginx.conf"
    conf.write_text(
        f"""worker_processes 1;
error_log {prefixo}/logs/erro.log warn;
pid {prefixo}/logs/nginx.pid;
events {{ worker_connections 64; }}
http {{
  access_log off;
  proxy_temp_path {prefixo}/proxy_temp;
  client_body_temp_path {prefixo}/client_temp;
  fastcgi_temp_path {prefixo}/fastcgi_temp;
  uwsgi_temp_path {prefixo}/uwsgi_temp;
  scgi_temp_path {prefixo}/scgi_temp;
  proxy_cache_path {prefixo}/cache levels=1:2 keys_zone=plat_cog_adv:4m max_size=64m inactive=10m use_temp_path=off;
  server {{
    listen 8173 ssl;
    server_name localhost;
    ssl_certificate {prefixo}/c.pem;
    ssl_certificate_key {prefixo}/k.pem;
{bloco}  }}
}}
""", encoding="utf-8")
    teste = subprocess.run(["/usr/sbin/nginx", "-p", str(prefixo), "-c", str(conf), "-t"],
                           capture_output=True, text=True)
    assert teste.returncode == 0, teste.stderr
    proc = subprocess.Popen(["/usr/sbin/nginx", "-p", str(prefixo), "-c", str(conf), "-g", "daemon off;"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        for _ in range(60):
            if _porta_viva(8173):
                break
            time.sleep(0.1)
        assert _porta_viva(8173), "o nginx do adversário não subiu na 8173"
        yield {"dados": dados, "chave": gravado["chave"], "token_a": token_a, "token_b": token_b, "ssl": ctx}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        cliente_a.delete(f"/api/tokens/{token_a['id']}")
        cliente_b.delete(f"/api/tokens/{token_b['id']}")
        _contexto(con, tid)
        with con.cursor() as cur:
            objetos_raster.apagar_item(cur, f"{PREFIXO}range")
        con.commit()


def _pedir(nginx, caminho, faixa=None):
    import urllib.error
    import urllib.request

    cabecalhos = {"Range": faixa} if faixa else {}
    pedido = urllib.request.Request(f"https://127.0.0.1:8173{caminho}", headers=cabecalhos)
    try:
        with urllib.request.urlopen(pedido, context=nginx["ssl"], timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_5_faixas_de_bytes_atras_do_nginx(nginx_cog):
    """Faixa normal, aberta (`bytes=100-`), além do fim, inválida e múltipla. O que se cobra: 206 com
    `Content-Range` correto e bytes iguais ao gravado quando a faixa é válida."""
    n = nginx_cog
    dados = n["dados"]
    total = len(dados)
    caminho = f"/svc/{n['token_a']['token']}/cog/{n['chave']}"
    medida = {}

    st, h, corpo = _pedir(n, caminho, "bytes=1048576-1048591")
    medida["faixa_normal"] = {"status": st, "content_range": h.get("Content-Range"), "bytes": len(corpo)}
    assert st == 206 and corpo == dados[1048576:1048592]
    assert h.get("Content-Range") == f"bytes 1048576-1048591/{total}"

    st, h, corpo = _pedir(n, caminho, "bytes=100-")
    medida["faixa_aberta"] = {"status": st, "content_range": h.get("Content-Range"), "bytes": len(corpo)}
    assert st == 206, f"faixa aberta devolveu {st}"
    assert corpo == dados[100:], "faixa aberta devolveu bytes diferentes do gravado"
    assert h.get("Content-Range") == f"bytes 100-{total - 1}/{total}"

    st, h, corpo = _pedir(n, caminho, f"bytes={total + 1000}-{total + 2000}")
    medida["faixa_alem_do_fim"] = {"status": st, "content_range": h.get("Content-Range")}
    assert st in (416, 206, 200), f"faixa além do fim devolveu {st}"

    st, h, corpo = _pedir(n, caminho, "bytes=abc-xyz")
    medida["faixa_invalida"] = {"status": st, "bytes": len(corpo)}
    assert st in (200, 206, 416), f"faixa inválida devolveu {st}"

    st, h, corpo = _pedir(n, caminho, "bytes=0-15,1048576-1048591")
    medida["multiplas_faixas"] = {
        "status": st, "content_range": h.get("Content-Range"), "content_type": h.get("Content-Type"),
        "bytes": len(corpo),
    }
    st, h, corpo = _pedir(n, caminho)
    medida["sem_faixa"] = {"status": st, "bytes": len(corpo), "accept_ranges": h.get("Accept-Ranges")}
    assert st == 200 and corpo == dados, "o objeto inteiro não bate byte a byte"
    MEDIDAS["ataques"]["5_faixas"] = medida


def test_5b_token_nao_pode_ser_adivinhado_nem_emprestado(nginx_cog, ambiente):
    """O token vai no CAMINHO: mede-se que um token inventado, um truncado, o token de OUTRO inquilino e
    o caminho sem token nenhum não abrem o objeto de A."""
    n = nginx_cog
    tok_a = n["token_a"]["token"]
    casos = {
        "token_inventado": f"/svc/plat_{'z' * 40}/cog/{n['chave']}",
        "token_truncado": f"/svc/{tok_a[:-4]}/cog/{n['chave']}",
        "token_com_um_char_trocado": f"/svc/{tok_a[:-1]}{'a' if tok_a[-1] != 'a' else 'b'}/cog/{n['chave']}",
        "token_de_outro_inquilino": f"/svc/{n['token_b']['token']}/cog/{n['chave']}",
        "sem_token": f"/svc/cog/{n['chave']}",
        "caminho_do_balde_direto": f"/{n['chave']}",
    }
    medida = {}
    for nome, caminho in casos.items():
        st, h, corpo = _pedir(n, caminho, "bytes=0-15")
        medida[nome] = {"status": st, "abriu": corpo == n["dados"][:16]}
    abriram = [k for k, v in medida.items() if v["abriu"]]
    MEDIDAS["ataques"]["5b_token"] = medida
    assert not abriram, f"o objeto abriu sem o token certo: {abriram} — REFUTADO"


@pytest.mark.xfail(strict=True, reason="a chave de cache do nginx não distingue o token: medido pelo adversário")
def test_5c_chave_de_cache_do_nginx_inclui_o_token(nginx_cog):
    """`proxy_cache_key "plat_cog$cog_slug/$cog_obj$slice_range"` não tem o token. Como o auth_request roda
    ANTES de o cache ser consultado, isso é escolha e não furo — mas quem lê o arquivo precisa saber que
    duas requisições com tokens diferentes compartilham a MESMA fatia em disco. Marcado xfail para que a
    frase deixe de ser verdade no dia em que alguém puser o token na chave."""
    conf = (RAIZ / "deploy" / "nginx.conf").read_text(encoding="utf-8")
    linha = [x for x in conf.splitlines() if "proxy_cache_key" in x][0]
    assert "cog_token" in linha, f"a chave de cache não inclui o token: {linha.strip()}"


@pytest.mark.xfail(
    strict=True,
    reason="MEDIDO pelo adversário: com `slice 1m` o nginx não repassa pedido de MÚLTIPLAS faixas; ele "
           "responde 200 com o objeto INTEIRO. Um leitor de COG que peça várias faixas numa requisição "
           "baixa o arquivo todo em vez de dezenas de bytes.",
)
def test_5d_multiplas_faixas_devolvem_206_multipart(nginx_cog):
    """`Range: bytes=0-15,1048576-1048591` deveria voltar 206 `multipart/byteranges`. Atrás do `slice 1m`
    volta 200 com o objeto inteiro — mede-se o custo: quantos bytes vieram para 32 pedidos."""
    n = nginx_cog
    st, h, corpo = _pedir(n, f"/svc/{n['token_a']['token']}/cog/{n['chave']}", "bytes=0-15,1048576-1048591")
    MEDIDAS["ataques"]["5d_multiplas_faixas"] = {
        "status": st, "content_type": h.get("Content-Type"), "bytes_pedidos": 32, "bytes_recebidos": len(corpo),
        "objeto_inteiro": len(corpo) == len(n["dados"]),
    }
    assert st == 206 and "multipart/byteranges" in (h.get("Content-Type") or ""), (
        f"múltiplas faixas devolveram {st} com {len(corpo)} bytes de um objeto de {len(n['dados'])}"
    )


# ================================================================ ataque 6: ListBuckets
def test_6_listbuckets_com_chave_ro_responde_200_e_o_que_ele_revela(ambiente):
    """A ressalva do construtor, conferida: `ListBuckets` com a chave só-leitura de A responde 200. Mede-se
    o que a resposta REVELA — se traz só o balde de A, o nome do balde já é o do próprio inquilino e o
    portador da chave o conhece; se trouxesse o de B, seria vazamento de nome de inquilino."""
    a, b = ambiente["baldes"]["demo"], ambiente["baldes"]["demo2"]
    ro = _boto3(a, ro=True)
    r = ro.list_buckets()
    nomes = [x["Name"] for x in r.get("Buckets", [])]
    medida = {
        "status": r["ResponseMetadata"]["HTTPStatusCode"], "baldes_listados": nomes,
        "traz_o_proprio": a["bucket_alias"] in nomes, "traz_o_do_vizinho": b["bucket_alias"] in nomes,
        "veredito": "ruído" if nomes == [a["bucket_alias"]] else "vazamento de nome de inquilino",
    }
    MEDIDAS["ataques"]["6_listbuckets"] = medida
    assert r["ResponseMetadata"]["HTTPStatusCode"] == 200, "a ressalva do construtor mudou: já não é 200"
    assert b["bucket_alias"] not in nomes, "ListBuckets revelou o balde do vizinho — REFUTADO"


@pytest.mark.xfail(
    strict=True,
    reason="MEDIDO pelo adversário: a cota vive em TRÊS lugares (plat.tenant, plat.arquivo_bucket e o Garage) "
           "e nada os reconcilia sozinho. Se o processo cai entre o UPDATE em plat.tenant e a chamada de "
           "garantir_bucket, o inquilino fica com a cota ANTIGA valendo no Garage — e ninguém avisa. Achado "
           "no ambiente de produção desta máquina em 06/09: plat.tenant.demo2 = 21.474.836.480 bytes, "
           "plat.arquivo_bucket.plat-demo2 = 500 bytes, Garage plat-demo2 maxSize = 500, maxObjects = null.",
)
def test_7_cota_fica_dessincronizada_quando_o_processo_cai_no_meio(ambiente):
    """Encena a queda: baixa a cota do inquilino e sincroniza, depois devolve a cota no banco SEM sincronizar
    (é o que sobra de um teste interrompido, de um OOM ou de um Ctrl-C entre as duas escritas). Cobra-se que a
    cota que VALE seja a declarada em `plat.tenant`. Cura no fim com `garantir_bucket(forcar=True)`."""
    from app import objetos

    con, tid = ambiente["con"], ambiente["ids"]["demo"]
    a = ambiente["baldes"]["demo"]
    declarada, cota_obj = ambiente["cotas"]["demo"]
    chave = f"{PREFIXO}/depois_da_queda.bin"
    medida = {"cota_declarada_no_tenant": declarada}
    try:
        _definir_cota(con, tid, "demo", 500, cota_obj)          # sincroniza banco e Garage em 500
        _contexto(con, tid)
        with con.cursor() as cur:                                # devolve SÓ o banco: a queda é aqui
            cur.execute(
                "UPDATE plat.tenant SET cota_bytes = %s WHERE id = %s", (declarada, tid)
            )
        con.commit()
        info = objetos._admin().info_bucket(a["bucket_id"])
        medida["cota_no_garage_depois_da_queda"] = int((info.get("quotas") or {}).get("maxSize") or 0)
        cli = _boto3(a, ro=False)
        try:
            cli.put_object(Bucket=a["bucket_alias"], Key=chave, Body=b"z" * 4096)
            medida["gravacao_de_4096_bytes"] = "aceita"
        except Exception as e:
            medida["gravacao_de_4096_bytes"] = _codigo(e)
    finally:
        try:
            _boto3(a, ro=False).delete_object(Bucket=a["bucket_alias"], Key=chave)
        except Exception:
            pass
        _definir_cota(con, tid, "demo", declarada, cota_obj)     # cura
        curada = objetos._admin().info_bucket(a["bucket_id"])
        medida["cota_no_garage_depois_da_cura"] = int((curada.get("quotas") or {}).get("maxSize") or 0)
    MEDIDAS["ataques"]["7_cota_dessincronizada"] = medida
    assert medida["cota_no_garage_depois_da_queda"] == declarada, (
        f"o Garage ficou com cota de {medida['cota_no_garage_depois_da_queda']} bytes enquanto "
        f"plat.tenant declara {declarada}; gravação de 4.096 bytes: {medida['gravacao_de_4096_bytes']}"
    )


# ============================== cláusulas (a) e (f) do portão, reproduzidas por conta própria
def test_8_semeadura_e_idempotente_e_a_cota_do_garage_e_a_declarada(ambiente):
    """Cláusula (a) do portão, reproduzida sem o teste do construtor: `python -m app.baldes_semear` sobre um
    inquilino que JÁ tem balde não muda nada, e a cota que está no Garage é a declarada em `plat.tenant`."""
    import io

    from app import baldes_semear, objetos

    tid = ambiente["ids"]["demo"]
    a = ambiente["baldes"]["demo"]
    declarada = ambiente["cotas"]["demo"]
    primeira = baldes_semear.semear([(tid, "demo")], saida=io.StringIO())
    segunda = baldes_semear.semear([(tid, "demo")], saida=io.StringIO())
    cotas = (objetos._admin().info_bucket(a["bucket_id"]).get("quotas") or {})
    medida = {
        "primeira_alterados": primeira["criados_ou_alterados"], "segunda_alterados": segunda["criados_ou_alterados"],
        "segunda_sem_mudanca": segunda["sem_mudanca"],
        "cota_declarada": {"bytes": declarada[0], "objetos": declarada[1]},
        "cota_no_garage": {"bytes": int(cotas.get("maxSize") or 0), "objetos": int(cotas.get("maxObjects") or 0)},
    }
    MEDIDAS["ataques"]["8_semeadura_idempotente"] = medida
    assert segunda["criados_ou_alterados"] == 0 and segunda["sem_mudanca"] == 1, "a semeadura não é idempotente"
    assert int(cotas.get("maxSize") or 0) == declarada[0]
    assert int(cotas.get("maxObjects") or 0) == declarada[1]


def test_9_apagar_item_devolve_os_contadores_do_garage(ambiente):
    """Cláusula (f) do portão, reproduzida por conta própria: os contadores do PRÓPRIO Garage (GetBucketInfo)
    voltam ao valor anterior depois de `apagar_item`, e a segunda chamada devolve zeros (idempotente)."""
    from app import objetos, objetos_raster

    con, tid = ambiente["con"], ambiente["ids"]["demo"]
    a = ambiente["baldes"]["demo"]
    item = f"{PREFIXO}apagar"
    antes = objetos._admin().info_bucket(a["bucket_id"])
    par = (int(antes.get("objects", 0)), int(antes.get("bytes", 0)))
    _contexto(con, tid)
    with con.cursor() as cur:
        for n in range(3):
            objetos_raster.guardar_bytes(cur, item, f"asset{n}", b"D" * (1024 * (n + 1)))
    con.commit()
    meio = objetos._admin().info_bucket(a["bucket_id"])
    _contexto(con, tid)
    with con.cursor() as cur:
        liberado = objetos_raster.apagar_item(cur, item)
        segunda = objetos_raster.apagar_item(cur, item)
    con.commit()
    depois = objetos._admin().info_bucket(a["bucket_id"])
    medida = {
        "antes": {"objetos": par[0], "bytes": par[1]},
        "com_os_tres": {"objetos": int(meio.get("objects", 0)), "bytes": int(meio.get("bytes", 0))},
        "depois": {"objetos": int(depois.get("objects", 0)), "bytes": int(depois.get("bytes", 0))},
        "liberado": liberado, "segunda_chamada": segunda,
    }
    MEDIDAS["ataques"]["9_apagar_devolve_contadores"] = medida
    assert (int(depois.get("objects", 0)), int(depois.get("bytes", 0))) == par, "os contadores não voltaram"
    assert segunda == {"objetos": 0, "bytes": 0}, "apagar_item não é idempotente"


def test_zz_grava_medidas():
    destino = RAIZ / "tests" / "medidas" / "L1-01-d-adversario.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(MEDIDAS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert len(MEDIDAS["ataques"]) >= 17, MEDIDAS["ataques"].keys()
