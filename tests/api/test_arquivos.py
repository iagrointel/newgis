"""Arquivos/objetos por inquilino no Garage (item L0-11-arquivos-objetos; ADR 0006). Portão: dois inquilinos não
veem objeto um do outro (cota e leitura), sha256 recalculado bate, cota estourada recusa com mensagem clara,
instalação idempotente, órfão plantado é acusado pela varredura. Refutação: chave só-leitura tentando escrever,
listar bucket de outro inquilino, chave de objeto com '../', sobrescrever objeto existente pela API."""

import hashlib
import os
import time

import pytest

from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L0-11-arquivos-objetos"


def test_bucket_por_inquilino_isolado_e_instalacao_idempotente(conexao_plat_app):
    """garantir_bucket é idempotente (P5): a segunda chamada não recria nada, só confere; cada inquilino tem
    bucket_id e chaves de acesso PRÓPRIAS (nunca compartilhadas)."""
    from app import objetos

    ids = ids_por_slug(conexao_plat_app)
    buckets = {}
    for slug in ("demo", "demo2"):
        contexto(conexao_plat_app, ids[slug], usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            b1 = objetos.garantir_bucket(cur, ids[slug], slug)
            b2 = objetos.garantir_bucket(cur, ids[slug], slug)  # idempotente: mesma linha, 0 mudanças
        conexao_plat_app.commit()
        assert b1["bucket_id"] == b2["bucket_id"] and b1["chave_rw_id"] == b2["chave_rw_id"]
        buckets[slug] = b1
    assert buckets["demo"]["bucket_id"] != buckets["demo2"]["bucket_id"]
    assert buckets["demo"]["bucket_alias"] != buckets["demo2"]["bucket_alias"]
    assert buckets["demo"]["chave_rw_id"] != buckets["demo2"]["chave_rw_id"]
    assert buckets["demo"]["chave_ro_id"] != buckets["demo2"]["chave_ro_id"]


def test_salvar_ler_apagar_e_sha256_recalculado(conexao_plat_app):
    """Contrato salvar/ler/apagar (ADR 0006 seção 2): sha256 devolvido bate com o recalculado sobre o conteúdo
    lido de volta; mesmo conteúdo não regrava (dedup); apagar é idempotente (segunda vez devolve False)."""
    from app import objetos

    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    conteudo = os.urandom(4096)
    with conexao_plat_app.cursor() as cur:
        o = objetos.guardar(cur, "zt_arquivo", conteudo, "application/octet-stream")
    conexao_plat_app.commit()
    assert o["sha256"] == hashlib.sha256(conteudo).hexdigest()
    assert o["bytes"] == len(conteudo)
    assert o["chave"].startswith("demo/zt_arquivo/")
    lido = objetos.ler(o["chave"])
    assert lido == conteudo
    assert hashlib.sha256(lido).hexdigest() == o["sha256"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        o2 = objetos.guardar(cur, "zt_arquivo", conteudo, "application/octet-stream")
    conexao_plat_app.commit()
    assert o2 == o  # mesmo conteúdo = mesma chave = não regrava
    assert objetos.existe(o["chave"]) is True
    assert objetos.apagar(o["chave"]) is True
    assert objetos.existe(o["chave"]) is False
    assert objetos.apagar(o["chave"]) is False  # idempotente


def test_dois_inquilinos_nao_veem_objeto_um_do_outro(conexao_plat_app):
    """Isolamento por bucket + chave (RLS de plat.arquivo): demo2 não lê nem apaga a chave do demo, mesmo sabendo
    o valor exato dela; existe()/ler() resolvem pelo slug DENTRO da própria chave, então não há checagem que
    o inquilino errado possa burlar passando outro contexto — o bucket de demo2 simplesmente não tem o objeto."""
    from app import objetos

    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        o_demo = objetos.guardar(cur, "zt_isolamento", b"segredo do demo", "text/plain")
    conexao_plat_app.commit()

    # a mesma chave, mas dentro do bucket do demo2, nunca existiu (Garage isola por bucket físico)
    b_demo2 = objetos._resolver_bucket_por_slug("demo2")
    assert b_demo2 is not None
    _, obj_key = objetos._chave_e_objeto(o_demo["chave"])
    cli_demo2 = objetos._cliente(b_demo2)
    assert cli_demo2.head(b_demo2["bucket_alias"], obj_key) is None

    objetos.apagar(o_demo["chave"])


def test_chave_so_leitura_nao_escreve_e_nao_le_bucket_alheio(conexao_plat_app):
    """Refutação: a chave de acesso RO de um inquilino recusa escrita (403 do Garage, não checagem nossa); a
    chave RW de um inquilino não lê o bucket de outro (o Garage nunca autoriza — mesmo mecanismo)."""
    from app import garage, objetos

    ids = ids_por_slug(conexao_plat_app)
    for slug in ("demo", "demo2"):
        contexto(conexao_plat_app, ids[slug], usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            objetos.garantir_bucket(cur, ids[slug], slug)
        conexao_plat_app.commit()

    b_demo = objetos._resolver_bucket_por_slug("demo")
    b_demo2 = objetos._resolver_bucket_por_slug("demo2")
    cli_ro_demo = objetos._cliente(b_demo, ro=True)
    with pytest.raises(garage.ErroGarage, match="403|AccessDenied"):
        cli_ro_demo.put(b_demo["bucket_alias"], "zt_tentativa_ro/x.bin", b"nao pode", "text/plain")

    cli_rw_demo2 = objetos._cliente(b_demo2)
    with pytest.raises(garage.ErroGarage, match="403|AccessDenied"):
        cli_rw_demo2.get(b_demo["bucket_alias"], "qualquer-coisa")


def test_chave_com_travessia_e_forma_invalida_nunca_chega_ao_garage(conexao_plat_app):
    """Refutação: chave com '../' (ou qualquer forma fora do padrão) é recusada ANTES de qualquer chamada ao
    Garage — ChaveInvalida, nunca uma travessia real (o caminho nem existe: é uma chave S3, não um caminho de
    disco, mas o formato ainda tem de ser fechado)."""
    from app import objetos

    for chave_ruim in (
        "../../etc/passwd",
        "demo/zt/../../x",
        "sem-barra",
        "demo/zt/" + "g" * 64 + ".bin",  # 'g' não é hexadecimal: sha256 inválido
        "DEMO/zt/" + "a" * 64 + ".bin",  # slug maiúsculo, fora do CHECK de plat.tenant.slug
    ):
        with pytest.raises(objetos.ChaveInvalida):
            objetos.ler(chave_ruim)
        with pytest.raises(objetos.ChaveInvalida):
            objetos._partes(chave_ruim)


def test_upload_nao_sobrescreve_objeto_existente_com_conteudo_diferente(conexao_plat_app):
    """A chave É o sha256: um PUT de conteúdo DIFERENTE nunca pode cair na mesma chave do primeiro (a prova é
    que as duas chaves saem diferentes); tentar reescrever manualmente a MESMA chave com bytes diferentes pela
    API não existe como caminho (guardar sempre deriva a chave do conteúdo recebido) — o teste prova as duas
    metades: chaves diferentes para conteúdo diferente, e a chave do primeiro objeto continua íntegra depois."""
    from app import objetos

    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        o1 = objetos.guardar(cur, "zt_semover", b"conteudo A", "text/plain")
    conexao_plat_app.commit()
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        o2 = objetos.guardar(cur, "zt_semover", b"conteudo B", "text/plain")
    conexao_plat_app.commit()
    assert o1["chave"] != o2["chave"]
    assert objetos.ler(o1["chave"]) == b"conteudo A"  # o primeiro objeto nunca foi tocado
    assert objetos.ler(o2["chave"]) == b"conteudo B"
    objetos.apagar(o1["chave"])
    objetos.apagar(o2["chave"])


def test_cota_estourada_recusa_com_mensagem(conexao_plat_app):
    """Cota do bucket = tenant.cota_bytes (sincronizada em garantir_bucket); acima dela, guardar recusa com
    mensagem legível (nunca silenciosamente trunca ou aceita)."""
    from app import objetos

    ids = ids_por_slug(conexao_plat_app)
    tid = ids["demo2"]
    contexto(conexao_plat_app, tid, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT cota_bytes FROM plat.tenant WHERE id = %s", (tid,))
        cota_original = cur.fetchone()["cota_bytes"]
        cur.execute("UPDATE plat.tenant SET cota_bytes = 500 WHERE id = %s", (tid,))
    conexao_plat_app.commit()
    try:
        contexto(conexao_plat_app, tid, usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            with pytest.raises(objetos.CotaExcedida, match="500"):
                objetos.guardar(cur, "zt_cota", os.urandom(600), "application/octet-stream")
        conexao_plat_app.commit()
    finally:
        contexto(conexao_plat_app, tid, usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            cur.execute("UPDATE plat.tenant SET cota_bytes = %s WHERE id = %s", (cota_original, tid))
        conexao_plat_app.commit()


def test_multipart_real_produz_o_mesmo_sha256_que_um_put_unico(conexao_plat_app):
    """Upload multipart (contrato parte_iniciar/parte_enviar/parte_concluir, ADR 0005): o sha256 do objeto
    concluído é lido de volta em stream e bate com o sha256 calculado sobre os mesmos bytes localmente."""
    from app import objetos

    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    parte1 = os.urandom(5 * 1024 * 1024)
    parte2 = os.urandom(1024)
    esperado = hashlib.sha256(parte1 + parte2).hexdigest()
    with conexao_plat_app.cursor() as cur:
        r = objetos.parte_iniciar(cur, "zt_multipart", "application/octet-stream")
    conexao_plat_app.commit()
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        e1 = objetos.parte_enviar(cur, r["upload_id"], 1, parte1)
    conexao_plat_app.commit()
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        e2 = objetos.parte_enviar(cur, r["upload_id"], 2, parte2)
    conexao_plat_app.commit()
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        concluido = objetos.parte_concluir(cur, r["upload_id"], [(1, e1), (2, e2)])
    conexao_plat_app.commit()
    assert concluido["sha256"] == esperado
    assert concluido["bytes"] == len(parte1) + len(parte2)
    assert objetos.ler(concluido["chave"]) == parte1 + parte2
    objetos.apagar(concluido["chave"])


def test_varredura_acusa_orfao_plantado(conexao_plat_app):
    """Objeto gravado direto no Garage (sem passar por guardar, então sem linha em plat.arquivo) aparece em
    `sem_linha`; a varredura não acusa mais nada além dele.

    08/09: a asserção de entrada era `antes["sem_linha"] == []`, isto é, o BUCKET INTEIRO do inquilino `demo`
    limpo. O bucket é de todo o inquilino, e sob pytest-xdist os arquivos da suíte correm em paralelo: quando
    `tests/api/uploads/test_uploads.py` termina antes deste arquivo, o objeto que a conclusão de multipart deixa
    para trás (medido: 1 objeto `arquivo/<sha>.csv`, sempre o mesmo, produzido por
    `test_duas_sessoes_enviando_partes_diferentes_ao_mesmo_tempo`, que está na linha de base de falhas) já está
    lá e a entrada reprova. Em série o mesmo teste passa só porque `test_arquivos.py` é colhido antes de
    `uploads/` — ordem, não propriedade.

    A propriedade que o item prova continua inteira e é verificada por DIFERENÇA entre as duas varreduras: o
    objeto plantado não era acusado antes, é acusado depois, e nada mais entrou na acusação. Nenhuma asserção
    foi afrouxada: o que saiu foi a dependência de ordem de coleta.
    """
    from app import objetos

    chave = "zt_orfao/plantado.bin"
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        antes = objetos.varrer_orfaos(cur, "demo")
        assert chave not in antes["sem_linha"]
        bucket = objetos.garantir_bucket(cur, ids["demo"], "demo")
    conexao_plat_app.commit()
    cli = objetos._cliente(bucket)
    cli.put(bucket["bucket_alias"], chave, b"ninguem registrou isso", "text/plain")
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        depois = objetos.varrer_orfaos(cur, "demo")
    cli.delete(bucket["bucket_alias"], chave)
    assert chave in depois["sem_linha"]
    assert set(depois["sem_linha"]) - set(antes["sem_linha"]) == {chave}


def test_api_enviar_exige_token_nunca_cookie_de_sessao(sessao_a):
    """CSRF (ADR 0002 5.3): todo verbo de escrita sob cookie de sessão exige corpo application/json; o arquivo
    cru nunca é JSON, então a sessão recebe 415 (ou, se disfarçar o content-type, 403 exige_token) — enviar
    arquivo é sempre por token de serviço, nunca por cookie."""
    r = sessao_a.post("/api/arquivos?classe=zt_api", content=b"bytes crus", headers={"content-type": "text/plain"})
    assert r.status_code == 415 and r.json()["erro"] == "tipo_nao_aceito"


def test_api_enviar_ler_apagar_por_token(cliente, sessao_a, sessao_b):
    """Ponta a ponta pela API (token de serviço, escopo admin:inquilino): enviar, baixar (sha256 igual), apagar;
    token de outro inquilino recebe 404 para a mesma classe+sha256 (nunca vê o objeto do primeiro)."""
    tok_a = sessao_a.post("/api/tokens", json={"nome": "zt-arquivos-a", "escopos": ["admin:inquilino"]}).json()
    tok_b = sessao_b.post("/api/tokens", json={"nome": "zt-arquivos-b", "escopos": ["admin:inquilino"]}).json()
    try:
        h_a = {"Authorization": f"Bearer {tok_a['token']}", "content-type": "text/plain"}
        h_b = {"Authorization": f"Bearer {tok_b['token']}"}
        conteudo = os.urandom(2048)
        r = cliente.post("/api/arquivos?classe=zt_api", content=conteudo, headers=h_a)
        assert r.status_code == 201, r.text
        corpo = r.json()
        assert corpo["sha256"] == hashlib.sha256(conteudo).hexdigest()
        assert corpo["bytes"] == len(conteudo)
        sha = corpo["sha256"]

        r = cliente.get(f"/api/arquivos/{sha}?classe=zt_api", headers=h_a)
        assert r.status_code == 200 and r.content == conteudo

        r = cliente.get(f"/api/arquivos/{sha}?classe=zt_api", headers=h_b)
        assert r.status_code == 404, r.text

        r = cliente.delete(f"/api/arquivos/{sha}?classe=zt_api", headers=h_b)
        assert r.status_code == 404

        r = cliente.delete(f"/api/arquivos/{sha}?classe=zt_api", headers=h_a)
        assert r.status_code == 204
        assert cliente.get(f"/api/arquivos/{sha}?classe=zt_api", headers=h_a).status_code == 404
    finally:
        sessao_a.delete(f"/api/tokens/{tok_a['id']}")
        sessao_b.delete(f"/api/tokens/{tok_b['id']}")


def test_api_recusa_classe_invalida_e_corpo_vazio(cliente, sessao_a):
    tok = sessao_a.post("/api/tokens", json={"nome": "zt-arquivos-c", "escopos": ["admin:inquilino"]}).json()
    try:
        h = {"Authorization": f"Bearer {tok['token']}"}
        assert cliente.post("/api/arquivos?classe=Maiuscula", content=b"x", headers=h).status_code == 422
        assert cliente.post("/api/arquivos?classe=zt_vazio", content=b"", headers=h).status_code == 422
        assert sessao_a.get("/api/arquivos/naoehex64?classe=zt_api").status_code == 422
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_api_recusa_script_disfarcado_de_jpeg(cliente, sessao_a):
    """Item L7-03-b-antivirus-anexos, cláusula literal do portão: Content-Type declarado `image/jpeg` (a
    escolha do cliente, equivalente a nomear o arquivo `.jpg`), bytes reais de um script de shell — 415, nunca
    201; o objeto nunca chega a existir no Garage (não há chave para conferir, a varredura corre ANTES do PUT)."""
    tok = sessao_a.post("/api/tokens", json={"nome": "zt-arquivos-d", "escopos": ["admin:inquilino"]}).json()
    try:
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "image/jpeg"}
        r = cliente.post("/api/arquivos?classe=zt_disfarcado", content=b"#!/bin/sh\necho pwned\n", headers=h)
        assert r.status_code == 415, r.text
        corpo = r.json()
        assert corpo["erro"] == "conteudo_recusado"
        assert corpo["detalhe"]["tipo_detectado"] == "text/x-shellscript"
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_api_recusa_script_grande_disfarcado_de_png_antes_do_multipart(cliente, sessao_a):
    """Mesma cláusula, mas grande o bastante (> ARQUIVO_PARTE_BYTES) para abrir o caminho multipart: a
    varredura roda na 1ª parte, ANTES de `objetos.parte_iniciar` — nenhum multipart chega a abrir no Garage."""
    from app import limites

    tok = sessao_a.post("/api/tokens", json={"nome": "zt-arquivos-e", "escopos": ["admin:inquilino"]}).json()
    try:
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "image/png"}
        grande = b"#!/bin/sh\n" + b"echo pwned\n" * (limites.ARQUIVO_PARTE_BYTES // 10)
        assert len(grande) > limites.ARQUIVO_PARTE_BYTES
        r = cliente.post("/api/arquivos?classe=zt_disfarcado_grande", content=grande, headers=h)
        assert r.status_code == 415, r.text
        assert r.json()["erro"] == "conteudo_recusado"
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_api_uso_e_cota(sessao_a):
    r = sessao_a.get("/api/arquivos")
    assert r.status_code == 200
    corpo = r.json()
    assert "bytes_usados" in corpo and "cota_bytes" in corpo and corpo["bytes_usados"] >= 0


def test_taxa_de_transferencia_local(conexao_plat_app, medida):
    """Medida do portão (taxa_mb_s de escrita e leitura local, mesma máquina)."""
    from app import objetos

    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    dados = os.urandom(4 * 1024 * 1024)
    t0 = time.perf_counter()
    with conexao_plat_app.cursor() as cur:
        o = objetos.guardar(cur, "zt_taxa", dados, "application/octet-stream")
    conexao_plat_app.commit()
    dt_escrita = time.perf_counter() - t0
    t0 = time.perf_counter()
    lido = objetos.ler(o["chave"])
    dt_leitura = time.perf_counter() - t0
    assert lido == dados
    mb = len(dados) / (1024 * 1024)
    medida(ITEM)("escrita_mb_s", round(mb / dt_escrita, 2), "MB/s", "objetos.guardar de 4 MiB, local, PUT único")
    medida(ITEM)("leitura_mb_s", round(mb / dt_leitura, 2), "MB/s", "objetos.ler de 4 MiB, local")
    objetos.apagar(o["chave"])
