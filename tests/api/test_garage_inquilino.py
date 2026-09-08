"""Balde por inquilino no Garage: cota em bytes E em objetos, chave só-leitura própria, objeto nomeado por
conteúdo e nunca sobrescrito, entrega por Range atrás do nginx e apagamento que devolve a cota (item
L1-01-d-garage-por-inquilino; ADR 20260908T1255, sobre o ADR 0006).

Portão, cláusula por cláusula:
 (a) a semeadura de instalação cria o balde do inquilino de teste com a cota DECLARADA e é idempotente;
 (b) escrita acima da cota é recusada pelo PRÓPRIO Garage e a recusa dele chega à API em português;
 (c) a chave só-leitura do inquilino A não lista nem lê o balde do B (medido com boto3, o mesmo cliente que o
     ArcGIS Pro e o GDAL do TiTiler usam por baixo);
 (d) PUT com a mesma chave de objeto é recusado pelo adaptador (nunca sobrescreve);
 (e) GET por HTTPS com cabeçalho Range responde 206 no endpoint web do Garage atrás do nginx com `slice 1m`;
 (f) apagar o item remove os objetos e o balde reflete a cota na hora.

Refutação (escrita neste arquivo ANTES de o adaptador ser considerado pronto): com a chave só-leitura, tentar
PUT, DELETE, ListBuckets, CopyObject entre baldes; chave de objeto com `..`. Qualquer escrita bem-sucedida
refuta o item.

Todos os baldes criados aqui são apagados no fim (`objetos.apagar_bucket_do_inquilino`): o disco desta máquina
é apertado e balde órfão no Garage é sujeira que a próxima rodada herda."""

import hashlib
import json
import os
import secrets
import socket
import subprocess
import time
from pathlib import Path

import pytest

from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L1-01-d-garage-por-inquilino"
RAIZ = Path(__file__).resolve().parents[2]
MEDIDAS: dict = {"item": ITEM, "clausulas": {}}


# ---------------------------------------------------------------- apoio
def _bucket(con, tenant_id, slug, **kw):
    from app import objetos

    contexto(con, tenant_id, usuario_id=0, login="teste")
    with con.cursor() as cur:
        linha = objetos.garantir_bucket(cur, tenant_id, slug, **kw)
    con.commit()
    return linha


def _cliente_boto3(bucket: dict, *, ro: bool):
    """Cliente S3 de verdade (boto3), do jeito que a conexão S3 do ArcGIS Pro e o /vsis3 do GDAL falam com o
    Garage: endereçamento por caminho, assinatura v4, região do PLAT_GARAGE_REGIAO."""
    import boto3
    from botocore.config import Config

    from app.settings import settings

    return boto3.client(
        "s3",
        endpoint_url=settings.PLAT_GARAGE_URL,
        aws_access_key_id=bucket["chave_ro_id"] if ro else bucket["chave_rw_id"],
        aws_secret_access_key=bucket["chave_ro_segredo"] if ro else bucket["chave_rw_segredo"],
        region_name=settings.PLAT_GARAGE_REGIAO,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 1}),
    )


def _guardar(con, tenant_id, slug, item_id, asset, dados, content_type="image/tiff"):
    from app import objetos_raster

    contexto(con, tenant_id, usuario_id=0, login="teste")
    with con.cursor() as cur:
        r = objetos_raster.guardar_bytes(cur, item_id, asset, dados, content_type)
    con.commit()
    return r


@pytest.fixture(scope="module")
def inquilino_de_teste(sessao_plat, env):
    """Inquilino zt-inq-* novo (nunca teve balde) + o balde apagado no fim, no Garage e no banco. A conexão de
    limpeza é PRÓPRIA (psycopg2 direto): `conexao_plat_app` é por função e este inquilino vive o módulo inteiro."""
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.conftest import InquilinoTemporario

    inq = InquilinoTemporario(sessao_plat)
    yield inq
    from app import objetos

    # CursorSchemaAmbiente, não RealDictCursor: esta conexão é própria (a `conexao_plat_app` é por função e este
    # inquilino vive o módulo inteiro) e faz SQL cru com `plat.` literal. Sem a reescrita ela ignora PLAT_SCHEMA e
    # vai bater no schema de produção — em base de trilha isso é "permission denied for schema plat" na limpeza,
    # e em produção seria pior que um erro. É a mesma escolha da fixture `conexao_plat_app` de tests/conftest.py.
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        contexto(con, inq.id, usuario_id=0, login="teste")
        with con.cursor() as cur:
            objetos.apagar_bucket_do_inquilino(cur, inq.id)
        con.commit()
    finally:
        con.close()
    inq.apagar()


# ---------------------------------------------------------------- (a) semeadura
def test_a_semeadura_cria_balde_do_inquilino_com_cota_declarada(inquilino_de_teste, conexao_plat_app):
    """A semeadura do install.sh (passo g3, `python -m app.baldes_semear`) cria o balde do inquilino novo com as
    DUAS cotas de `plat.tenant` e liga o endpoint web; a segunda execução não muda nada."""
    import io

    from app import baldes_semear, objetos

    tid = inquilino_de_teste.id
    contexto(conexao_plat_app, tid, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT cota_bytes, cota_objetos FROM plat.tenant WHERE id = %s", (tid,))
        declarada = cur.fetchone()
    conexao_plat_app.commit()
    assert declarada is not None

    primeira = baldes_semear.semear([(tid, inquilino_de_teste.slug)], saida=io.StringIO())
    segunda = baldes_semear.semear([(tid, inquilino_de_teste.slug)], saida=io.StringIO())
    assert primeira["criados_ou_alterados"] == 1, "o inquilino novo não tinha balde: a 1ª semeadura tem de criar"
    assert segunda["criados_ou_alterados"] == 0 and segunda["sem_mudanca"] == 1, "semeadura não é idempotente"

    linha = _bucket(conexao_plat_app, tid, inquilino_de_teste.slug)
    info = objetos._admin().info_bucket(linha["bucket_id"])
    assert info["quotas"]["maxSize"] == declarada["cota_bytes"] == linha["cota_bytes"]
    assert info["quotas"]["maxObjects"] == declarada["cota_objetos"] == linha["cota_objetos"]
    assert linha["bucket_alias"].endswith(inquilino_de_teste.slug)
    MEDIDAS["clausulas"]["a_semeadura"] = {
        "balde": linha["bucket_alias"],
        "cota_bytes_declarada": int(declarada["cota_bytes"]),
        "cota_objetos_declarada": int(declarada["cota_objetos"]),
        "cota_bytes_no_garage": int(info["quotas"]["maxSize"]),
        "cota_objetos_no_garage": int(info["quotas"]["maxObjects"]),
        "primeira_execucao_alterados": primeira["criados_ou_alterados"],
        "segunda_execucao_alterados": segunda["criados_ou_alterados"],
    }


def test_a2_registro_do_balde_nao_expoe_segredo(inquilino_de_teste, conexao_plat_app):
    """`plat.tenant_bucket` é a visão que uma tela de administração pode ler: id do balde, alias, id da chave
    só-leitura e cotas — nenhum dos dois SEGREDOS. E a RLS continua valendo (só o próprio inquilino)."""
    contexto(conexao_plat_app, inquilino_de_teste.id, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT * FROM plat.tenant_bucket")
        linhas = cur.fetchall()
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='plat' AND table_name='tenant_bucket'"
        )
        colunas = {r["column_name"] for r in cur.fetchall()}
    conexao_plat_app.commit()
    assert "segredo" not in " ".join(colunas)
    assert {"bucket_alias", "chave_ro_id", "cota_bytes", "cota_objetos", "web_ativo"} <= colunas
    assert [linha["tenant_id"] for linha in linhas] == [inquilino_de_teste.id], "a RLS da visão deixou vazar outro"


# ---------------------------------------------------------------- (b) cota
def test_b_cota_de_bytes_recusada_pelo_garage_chega_em_portugues(inquilino_de_teste, conexao_plat_app):
    """A recusa medida é a do PRÓPRIO Garage, não a da nossa checagem prévia: o PUT vai direto pelo cliente S3,
    passando por cima de `conferir_cotas`, e mesmo assim é recusado. A mensagem que sobe é em português."""
    from app import objetos
    from app.garage import CotaGarage

    tid = inquilino_de_teste.id
    contexto(conexao_plat_app, tid, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute("UPDATE plat.tenant SET cota_bytes = 1000 WHERE id = %s", (tid,))
    conexao_plat_app.commit()
    try:
        linha = _bucket(conexao_plat_app, tid, inquilino_de_teste.slug)
        assert linha["cota_bytes"] == 1000
        cli = objetos._cliente(linha)
        with pytest.raises(CotaGarage) as e:
            cli.put(linha["bucket_alias"], "item_cota/cog_00000000.tif", os.urandom(4096), "image/tiff")
        assert e.value.tipo == "bytes"
        msg = str(e.value)
        assert "cota de armazenamento" in msg and "atingida" in msg
        assert "quota" not in msg.lower(), f"mensagem em inglês chegou à API: {msg}"
        # e o mesmo erro, pelo caminho do adaptador, sai como CotaExcedida (o que a rota traduz em 413)
        with pytest.raises(objetos.CotaExcedida):
            _guardar(conexao_plat_app, tid, inquilino_de_teste.slug, "item_cota", "cog", os.urandom(4096))
        MEDIDAS["clausulas"]["b_cota_bytes"] = {"cota_bytes": 1000, "bytes_tentados": 4096, "mensagem": msg}
    finally:
        contexto(conexao_plat_app, tid, usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            cur.execute("UPDATE plat.tenant SET cota_bytes = 21474836480 WHERE id = %s", (tid,))
        conexao_plat_app.commit()
        _bucket(conexao_plat_app, tid, inquilino_de_teste.slug)


def test_b2_cota_de_objetos_recusada_pelo_garage_chega_em_portugues(inquilino_de_teste, conexao_plat_app):
    """A cota que o L0-11 não tinha: número de OBJETOS. Um COG de 200 MB e 200 mil miniaturas de 2 KB custam
    coisas diferentes ao cluster, e só a segunda estoura a contagem de partições do Garage."""
    from app import objetos
    from app.garage import CotaGarage

    tid = inquilino_de_teste.id
    linha = _bucket(conexao_plat_app, tid, inquilino_de_teste.slug)
    usados = int(objetos._admin().info_bucket(linha["bucket_id"])["objects"])
    contexto(conexao_plat_app, tid, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute("UPDATE plat.tenant SET cota_objetos = %s WHERE id = %s", (usados + 1, tid))
    conexao_plat_app.commit()
    try:
        linha = _bucket(conexao_plat_app, tid, inquilino_de_teste.slug)
        assert linha["cota_objetos"] == usados + 1
        cli = objetos._cliente(linha)
        alias = linha["bucket_alias"]
        cli.put(alias, "item_obj/a_00000001.tif", b"um", "image/tiff")  # cabe: chega exatamente na cota
        with pytest.raises(CotaGarage) as e:
            cli.put(alias, "item_obj/b_00000002.tif", b"dois", "image/tiff")
        assert e.value.tipo == "objetos"
        msg = str(e.value)
        assert "cota de objetos" in msg and "quota" not in msg.lower()
        cli.delete(alias, "item_obj/a_00000001.tif")
        MEDIDAS["clausulas"]["b_cota_objetos"] = {
            "objetos_usados_antes": usados, "cota_objetos": usados + 1, "mensagem": msg
        }
    finally:
        contexto(conexao_plat_app, tid, usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            cur.execute("UPDATE plat.tenant SET cota_objetos = 200000 WHERE id = %s", (tid,))
        conexao_plat_app.commit()
        _bucket(conexao_plat_app, tid, inquilino_de_teste.slug)


def test_b3_api_devolve_413_com_a_mensagem_em_portugues(token_a, conexao_plat_app):
    """A ponta da cláusula (b): a mensagem chega ao cliente HTTP, não fica só na exceção. `POST /api/arquivos`
    com o inquilino de demonstração abaixo da cota devolve 413 `cota_excedida` e a frase em português."""
    ids = ids_por_slug(conexao_plat_app)
    tid = ids["demo"]
    contexto(conexao_plat_app, tid, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT cota_bytes FROM plat.tenant WHERE id = %s", (tid,))
        original = cur.fetchone()["cota_bytes"]
        cur.execute("UPDATE plat.tenant SET cota_bytes = 500 WHERE id = %s", (tid,))
    conexao_plat_app.commit()
    try:
        _bucket(conexao_plat_app, tid, "demo")
        # cliente sem cookie: `POST /api/arquivos` só aceita token de serviço, e mandar cookie junto daria 400
        # `autenticacao_ambigua` antes de a rota rodar
        from tests.api.conftest import novo_cliente

        r = novo_cliente().post(
            "/api/arquivos?classe=zt_cota_api",
            content=os.urandom(2048),
            headers={"Content-Type": "application/octet-stream", "Authorization": f"Bearer {token_a['token']}"},
        )
        assert r.status_code == 413, r.text
        corpo = r.json()
        assert corpo["erro"] == "cota_excedida"
        assert "cota" in corpo["mensagem"] and "quota" not in corpo["mensagem"].lower()
        MEDIDAS["clausulas"]["b_api"] = {"status": r.status_code, "erro": corpo["erro"], "mensagem": corpo["mensagem"]}
    finally:
        contexto(conexao_plat_app, tid, usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            cur.execute("UPDATE plat.tenant SET cota_bytes = %s WHERE id = %s", (original, tid))
        conexao_plat_app.commit()
        _bucket(conexao_plat_app, tid, "demo")


# ---------------------------------------------------------------- (c) chave só-leitura entre inquilinos
def test_c_chave_so_leitura_de_a_nao_ve_o_balde_de_b(conexao_plat_app):
    """Medido com boto3 (o cliente que o ArcGIS Pro e o GDAL usam por baixo): a chave RO do inquilino A não lê
    nem lista o balde do B, mesmo sabendo o nome exato do balde e da chave do objeto."""
    from botocore.exceptions import ClientError

    ids = ids_por_slug(conexao_plat_app)
    a = _bucket(conexao_plat_app, ids["demo"], "demo")
    b = _bucket(conexao_plat_app, ids["demo2"], "demo2")
    dados = b"conteudo do inquilino B, que o A nunca pode ler"
    sha = hashlib.sha256(dados).hexdigest()
    o = _guardar(conexao_plat_app, ids["demo2"], "demo2", "zt_cruzado", "cog", dados)
    chave_no_balde = o["objeto"]
    try:
        ro_a = _cliente_boto3(a, ro=True)
        ro_b = _cliente_boto3(b, ro=True)
        # a chave RO do B lê o próprio objeto (prova de que a chave funciona e o teste não passa por acidente)
        lido = ro_b.get_object(Bucket=b["bucket_alias"], Key=chave_no_balde)["Body"].read()
        assert hashlib.sha256(lido).hexdigest() == sha
        codigos = {}
        for nome, chamada in {
            "get": lambda: ro_a.get_object(Bucket=b["bucket_alias"], Key=chave_no_balde),
            "head": lambda: ro_a.head_object(Bucket=b["bucket_alias"], Key=chave_no_balde),
            "list": lambda: ro_a.list_objects_v2(Bucket=b["bucket_alias"]),
        }.items():
            with pytest.raises(ClientError) as e:
                chamada()
            codigos[nome] = e.value.response["ResponseMetadata"]["HTTPStatusCode"]
            assert codigos[nome] in (401, 403, 404), f"{nome} devolveu {codigos[nome]} no balde do outro inquilino"
        MEDIDAS["clausulas"]["c_isolamento_ro"] = codigos
    finally:
        from app import objetos_raster

        contexto(conexao_plat_app, ids["demo2"], usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            objetos_raster.apagar_item(cur, "zt_cruzado")
        conexao_plat_app.commit()


def test_c2_refutacao_chave_so_leitura_nao_escreve_de_jeito_nenhum(conexao_plat_app):
    """REFUTAÇÃO. Com a chave só-leitura: PUT, DELETE, ListBuckets e CopyObject (dentro do balde e de um balde
    para o outro). Qualquer uma que passe refuta o item — não há 'quase só-leitura'."""
    from botocore.exceptions import ClientError

    ids = ids_por_slug(conexao_plat_app)
    a = _bucket(conexao_plat_app, ids["demo"], "demo")
    b = _bucket(conexao_plat_app, ids["demo2"], "demo2")
    alvo = _guardar(conexao_plat_app, ids["demo"], "demo", "zt_refuta", "cog", b"objeto alvo da refutacao")
    ro = _cliente_boto3(a, ro=True)
    try:
        tentativas = {
            "put": lambda: ro.put_object(Bucket=a["bucket_alias"], Key="zt_refuta/cog_deadbeef.tif", Body=b"x"),
            "delete": lambda: ro.delete_object(Bucket=a["bucket_alias"], Key=alvo["objeto"]),
            "copy_no_mesmo_balde": lambda: ro.copy_object(
                Bucket=a["bucket_alias"], Key="zt_refuta/copia_deadbeef.tif",
                CopySource={"Bucket": a["bucket_alias"], "Key": alvo["objeto"]},
            ),
            "copy_entre_baldes": lambda: ro.copy_object(
                Bucket=b["bucket_alias"], Key="zt_refuta/copia_deadbeef.tif",
                CopySource={"Bucket": a["bucket_alias"], "Key": alvo["objeto"]},
            ),
            "multipart": lambda: ro.create_multipart_upload(
                Bucket=a["bucket_alias"], Key="zt_refuta/parte_deadbeef.tif"
            ),
        }
        codigos = {}
        for nome, chamada in tentativas.items():
            with pytest.raises(ClientError) as e:
                chamada()
            codigos[nome] = e.value.response["ResponseMetadata"]["HTTPStatusCode"]
            assert codigos[nome] in (401, 403), f"a chave só-leitura conseguiu {nome} ({codigos[nome]}): REFUTADO"
        # ListBuckets: a chave RO não pode enumerar os baldes do cluster (só o seu, se tanto)
        try:
            baldes = [x["Name"] for x in ro.list_buckets().get("Buckets", [])]
            assert b["bucket_alias"] not in baldes, "ListBuckets da chave RO de A mostrou o balde de B: REFUTADO"
            codigos["list_buckets"] = f"200 {baldes}"
        except ClientError as e:
            codigos["list_buckets"] = e.response["ResponseMetadata"]["HTTPStatusCode"]
        # o objeto continua lá e intacto depois de todas as tentativas
        from app import objetos_raster

        assert objetos_raster.existe(alvo["chave"]) is True
        MEDIDAS["clausulas"]["refutacao_ro"] = codigos
    finally:
        from app import objetos_raster

        contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            objetos_raster.apagar_item(cur, "zt_refuta")
        conexao_plat_app.commit()


# ---------------------------------------------------------------- (d) nunca sobrescrever
def test_d_put_na_mesma_chave_e_recusado_pelo_adaptador(conexao_plat_app):
    """Regra medida em 29/08: sobrescrever a mesma chave deixou o TiTiler em 500 (o GDAL guarda o cabeçalho do
    COG em cache) e a CDN com fatia velha. Aqui isso vira recusa explícita, não convenção: o mesmo par
    (item, asset) com conteúdo NOVO tem sha8 novo, logo chave nova; com o MESMO conteúdo, `ObjetoJaExiste`."""
    from app import objetos_raster

    ids = ids_por_slug(conexao_plat_app)
    tid = ids["demo"]
    dados = b"COG versao 1 -- nunca sobrescrito"
    primeiro = _guardar(conexao_plat_app, tid, "demo", "zt_sobrescrita", "cog", dados)
    try:
        with pytest.raises(objetos_raster.ObjetoJaExiste):
            _guardar(conexao_plat_app, tid, "demo", "zt_sobrescrita", "cog", dados)
        novo = _guardar(conexao_plat_app, tid, "demo", "zt_sobrescrita", "cog", b"COG versao 2 -- conteudo novo")
        assert novo["chave"] != primeiro["chave"] and novo["sha8"] != primeiro["sha8"]
        assert objetos_raster.info(primeiro["chave"]).tamanho == len(dados), "a versão 1 foi alterada"
        # REFUTAÇÃO: nem por baixo do adaptador, com a chave de escrita, a chave com `..` chega ao Garage
        with pytest.raises(objetos_raster.ChaveInvalida):
            objetos_raster.objeto("../../etc", "cog", hashlib.sha256(b"x").hexdigest(), "tif")
        MEDIDAS["clausulas"]["d_nunca_sobrescreve"] = {
            "chave_v1": primeiro["chave"], "chave_v2": novo["chave"], "recusa": "ObjetoJaExiste"
        }
    finally:
        contexto(conexao_plat_app, tid, usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            objetos_raster.apagar_item(cur, "zt_sobrescrita")
        conexao_plat_app.commit()


# ---------------------------------------------------------------- (f) apagar item devolve a cota
def test_f_apagar_item_remove_objetos_e_o_balde_reflete_a_cota(conexao_plat_app):
    """Apagar o item apaga TODOS os objetos do prefixo `<item_id>/` e o balde reflete na hora: os contadores do
    próprio Garage (GetBucketInfo) voltam ao que eram. Segunda chamada devolve zeros (idempotente)."""
    from app import objetos, objetos_raster

    ids = ids_por_slug(conexao_plat_app)
    tid = ids["demo"]
    linha = _bucket(conexao_plat_app, tid, "demo")
    admin = objetos._admin()
    antes = admin.info_bucket(linha["bucket_id"])
    corpos = [os.urandom(3000), os.urandom(5000), os.urandom(7000)]
    gravados = [
        _guardar(conexao_plat_app, tid, "demo", "zt_apagar", f"cog{i}", c) for i, c in enumerate(corpos)
    ]
    depois_de_gravar = admin.info_bucket(linha["bucket_id"])
    assert int(depois_de_gravar["objects"]) == int(antes["objects"]) + 3
    assert int(depois_de_gravar["bytes"]) == int(antes["bytes"]) + sum(len(c) for c in corpos)

    contexto(conexao_plat_app, tid, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        r = objetos_raster.apagar_item(cur, "zt_apagar")
        r2 = objetos_raster.apagar_item(cur, "zt_apagar")
    conexao_plat_app.commit()
    assert r == {"objetos": 3, "bytes": sum(len(c) for c in corpos)}
    assert r2 == {"objetos": 0, "bytes": 0}, "apagar item não é idempotente"
    final = admin.info_bucket(linha["bucket_id"])
    assert int(final["objects"]) == int(antes["objects"])
    assert int(final["bytes"]) == int(antes["bytes"])
    for g in gravados:
        assert objetos_raster.existe(g["chave"]) is False
    uso = objetos.uso_detalhado("demo")
    assert uso["bytes_usados"] == int(antes["bytes"]) and uso["cota_objetos"] == int(linha["cota_objetos"])
    MEDIDAS["clausulas"]["f_apagar"] = {
        "objetos_antes": int(antes["objects"]), "bytes_antes": int(antes["bytes"]),
        "objetos_apos_gravar": int(depois_de_gravar["objects"]), "bytes_apos_gravar": int(depois_de_gravar["bytes"]),
        "liberados": r, "objetos_no_fim": int(final["objects"]), "bytes_no_fim": int(final["bytes"]),
    }


# ---------------------------------------------------------------- credencial só-leitura pela API
def test_rota_da_chave_so_leitura_exige_sessao_e_nunca_devolve_a_de_escrita(sessao_a, token_a, conexao_plat_app):
    """A chave RO existe para sair de casa (TiTiler, conexão S3 do ArcGIS Pro). A rota entrega só ela, só sob
    sessão e só com `org.integracoes`; um token de serviço não troca a si mesmo por credencial de armazenamento."""
    ids = ids_por_slug(conexao_plat_app)
    linha = _bucket(conexao_plat_app, ids["demo"], "demo")
    r = sessao_a.get("/api/arquivos/_chave-leitura")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["access_key_id"] == linha["chave_ro_id"]
    assert corpo["secret_access_key"] == linha["chave_ro_segredo"]
    assert corpo["permissoes"] == {"read": True, "write": False, "owner": False}
    inteiro = json.dumps(corpo)
    assert linha["chave_rw_id"] not in inteiro and linha["chave_rw_segredo"] not in inteiro
    # cliente NOVO, sem cookie: só o token de serviço. (Mandar cookie e cabeçalho na mesma requisição dá 400
    # `autenticacao_ambigua` antes de chegar à rota — seria um teste que não prova nada sobre esta rota.)
    from tests.api.conftest import novo_cliente

    so_token = novo_cliente()
    rt = so_token.get("/api/arquivos/_chave-leitura", headers={"Authorization": f"Bearer {token_a['token']}"})
    assert rt.status_code == 403, rt.text
    assert rt.json()["erro"] == "so_sessao"


def test_autorizacao_do_cog_recusa_token_de_outro_inquilino(sessao_a, token_a, conexao_plat_app):
    """A subrequisição `auth_request` do nginx: o token do inquilino A autoriza o caminho de A e NUNCA o de B —
    é o que impede o endpoint web do Garage (leitura anônima) de virar leitura do balde do vizinho."""
    tok = token_a["token"]
    sha8 = hashlib.sha256(b"qualquer").hexdigest()[:8]
    casos = {
        f"/svc/{tok}/cog/demo/item01/cog_{sha8}.tif": 204,
        f"/svc/{tok}/cog/demo2/item01/cog_{sha8}.tif": 403,
        f"/svc/plat_{'z' * 40}/cog/demo/item01/cog_{sha8}.tif": 403,
        f"/svc/{tok}/cog/demo/../demo2/item01/cog_{sha8}.tif": 403,
        f"/svc/{tok}/cog/demo/item01/cog_{sha8}.tif/etc/passwd": 403,
    }
    medido = {}
    for uri, esperado in casos.items():
        r = sessao_a.get("/api/arquivos/_cog/autorizar", headers={"X-Original-URI": uri})
        assert r.status_code == esperado, f"{uri} -> {r.status_code}, esperado {esperado}"
        medido[uri.replace(tok, "<token de A>")] = r.status_code
    MEDIDAS["clausulas"]["cog_autorizacao"] = medido


# ---------------------------------------------------------------- (e) Range 206 atrás do nginx
def _porta_viva(porta: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def _porta_livre() -> int:
    """Porta efêmera pedida ao próprio sistema. A porta é recurso PARTILHADO desta máquina (dezenas de trilhas
    correm ao mesmo tempo): número fixo no teste faz duas rodadas disputarem o mesmo soquete e, pior, faz uma
    delas medir o servidor da outra. O soquete é fechado antes de o nginx subir — a janela de corrida é de
    milissegundos e é a mesma que qualquer alocador de porta tem."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.skipif(not Path("/usr/sbin/nginx").exists(), reason="nginx não instalado nesta máquina")
def test_e_range_responde_206_por_https_atras_do_nginx(conexao_plat_app, tmp_path):
    """Sobe um nginx PRÓPRIO (prefixo temporário, porta livre pedida ao sistema, certificado autoassinado) com o
    MESMO bloco de deploy/nginx.conf — `slice 1m`, cache das fatias, auth_request contra a API — e mede: GET
    com `Range` no endpoint web do Garage responde 206 com `Content-Range`, e sem token válido responde 403.
    Não toca o nginx do sistema (regra do turno: quem aplica o bloco em produção é o gerente).

    A API tem de estar ouvindo (PLAT_TESTE_API_PORTA, padrão 8161: `venv/bin/uvicorn app.main:app --port 8161`),
    porque a autorização do caminho é uma subrequisição HTTP de verdade."""
    import ssl
    import urllib.request

    porta_api = int(os.environ.get("PLAT_TESTE_API_PORTA", "8161"))
    if not _porta_viva(porta_api):
        pytest.skip(f"API não está ouvindo em 127.0.0.1:{porta_api} (suba o uvicorn do worktree antes)")
    if not _porta_viva(3902):
        pytest.skip("endpoint web do Garage (127.0.0.1:3902) não está ouvindo")

    from app import objetos, objetos_raster
    from app.settings import settings

    ids = ids_por_slug(conexao_plat_app)
    tid = ids["demo"]
    _bucket(conexao_plat_app, tid, "demo", web=True)
    # objeto de ~3 MiB: com `slice 1m` o nginx pede 3 fatias ao Garage, então o Range atravessa mesmo
    dados = os.urandom(3 * 1024 * 1024 + 777)
    gravado = _guardar(conexao_plat_app, tid, "demo", "zt_range", "cog", dados)

    # token de serviço do inquilino A, do jeito que o TiTiler/ArcGIS Pro receberiam a URL
    from tests.api.conftest import credenciais, entrar, novo_cliente

    cli = novo_cliente()
    login, senha = credenciais()["demo"]
    assert entrar(cli, "demo", login, senha).status_code == 200
    rt = cli.post("/api/tokens", json={"nome": f"zt-cog-{secrets.token_hex(3)}", "escopos": ["admin:inquilino"]})
    assert rt.status_code == 201, rt.text
    token = rt.json()

    porta_nginx = _porta_livre()
    prefixo = tmp_path / "nginx"
    (prefixo / "logs").mkdir(parents=True)
    (prefixo / "cache").mkdir()
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=localhost",
         "-keyout", str(prefixo / "k.pem"), "-out", str(prefixo / "c.pem")],
        check=True, capture_output=True,
    )
    modelo = (RAIZ / "deploy" / "nginx.conf").read_text(encoding="utf-8")
    inicio = modelo.index("    # ── COG por inquilino")
    fim = modelo.index("    location / {")
    bloco = modelo[inicio:fim].replace("PORTA", str(porta_api)).replace(
        "PREFIXO_BALDE", settings.PLAT_GARAGE_BUCKET_PREFIXO
    ).replace("proxy_cache plat_cog;", "proxy_cache plat_cog_teste;")
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
  proxy_cache_path {prefixo}/cache levels=1:2 keys_zone=plat_cog_teste:4m max_size=64m inactive=10m use_temp_path=off;
  server {{
    listen {porta_nginx} ssl;
    server_name localhost;
    ssl_certificate {prefixo}/c.pem;
    ssl_certificate_key {prefixo}/k.pem;
{bloco}  }}
}}
""",
        encoding="utf-8",
    )
    teste = subprocess.run(
        ["/usr/sbin/nginx", "-p", str(prefixo), "-c", str(conf), "-t"], capture_output=True, text=True
    )
    assert teste.returncode == 0, teste.stderr
    proc = subprocess.Popen(
        ["/usr/sbin/nginx", "-p", str(prefixo), "-c", str(conf), "-g", "daemon off;"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    ctx_ssl = ssl.create_default_context()
    ctx_ssl.check_hostname = False
    ctx_ssl.verify_mode = ssl.CERT_NONE
    try:
        for _ in range(50):
            if _porta_viva(porta_nginx):
                break
            time.sleep(0.1)
        assert _porta_viva(porta_nginx), f"o nginx de teste não subiu na {porta_nginx}"
        caminho = objetos_raster.caminho_web(token["token"], gravado["chave"])
        url = f"https://127.0.0.1:{porta_nginx}{caminho}"

        pedido = urllib.request.Request(url, headers={"Range": "bytes=1048576-1048591"})
        with urllib.request.urlopen(pedido, context=ctx_ssl, timeout=30) as r:
            corpo = r.read()
            status = r.status
            content_range = r.headers.get("Content-Range")
            aceita = r.headers.get("Accept-Ranges")
        assert status == 206, f"Range respondeu {status}, esperado 206"
        assert corpo == dados[1048576:1048592]
        assert content_range and content_range.startswith("bytes 1048576-1048591/")
        assert aceita == "bytes"

        # sem token válido no caminho, o auth_request barra antes de o Garage ver a requisição
        ruim = urllib.request.Request(
            f"https://127.0.0.1:{porta_nginx}/svc/plat_{'z' * 40}/cog/{gravado['chave']}",
            headers={"Range": "bytes=0-15"},
        )
        try:
            with urllib.request.urlopen(ruim, context=ctx_ssl, timeout=30):
                pytest.fail("token inválido conseguiu ler o COG pelo nginx: REFUTADO")
        except urllib.error.HTTPError as e:
            assert e.code in (401, 403), f"token inválido devolveu {e.code}"
            negado = e.code
        MEDIDAS["clausulas"]["e_range_https"] = {
            "url": caminho.replace(token["token"], "<token de A>"),
            "status": status, "content_range": content_range, "bytes_conferidos": len(corpo),
            "objeto_bytes": len(dados), "slice": "1m", "token_invalido": negado,
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        cli.delete(f"/api/tokens/{token['id']}")
        contexto(conexao_plat_app, tid, usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            objetos_raster.apagar_item(cur, "zt_range")
        conexao_plat_app.commit()
        assert objetos.uso_detalhado("demo")["bytes_usados"] >= 0


def test_zz_grava_medidas():
    """Última do arquivo (ordem alfabética do pytest): grava tests/medidas/L1-01-d.json com o que foi MEDIDO."""
    destino = RAIZ / "tests" / "medidas" / "L1-01-d.json"
    anterior = json.loads(destino.read_text(encoding="utf-8")) if destino.exists() else {}
    MEDIDAS["medido_em"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    MEDIDAS["garage"] = "v2.3.0"
    juntas = {**anterior.get("clausulas", {}), **MEDIDAS["clausulas"]}
    MEDIDAS["clausulas"] = juntas
    destino.write_text(json.dumps(MEDIDAS, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    assert destino.exists()
