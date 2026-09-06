"""Upload retomável (item L0-04-a-upload-arquivo; ADR 0005 seção 3): portão de pronto e refutação do
adversário, via `POST /api/uploads` -> `PUT .../partes/{n}` -> `POST .../concluir`. Sessão de cookie só para
montar o token de serviço (mesma regra de `app.rotas_arquivos`); o envio em si é sempre por Bearer, sem cookie
(o corpo de PUT é byte cru, CSRF sob cookie exige JSON)."""

from __future__ import annotations

import hashlib
import time
import zipfile
from io import BytesIO

import psycopg2
import psycopg2.extras
import pytest

from app import db as banco
from app import objetos
from tests.api.conftest import PREFIXO_TESTE, novo_cliente
from tests.api.test_rls import contexto as _rls_contexto
from tests.api.test_rls import ids_por_slug
from app.schema_ambiente import CursorSchemaAmbiente  # honra PLAT_SCHEMA (make homolog / bases por trilha)


class Uploader:
    """Fábrica do fluxo completo (token -> iniciar -> partes -> concluir), com limpeza no teardown."""

    def __init__(self, sessao):
        self.sessao = sessao
        self._tok: str | None = None
        self._tok_id: str | None = None
        self.uploads: list[str] = []
        self.arquivos: list[str] = []

    def token(self) -> str:
        if self._tok is None:
            r = self.sessao.post(
                "/api/tokens", json={"nome": f"{PREFIXO_TESTE}-uploads", "escopos": ["admin:inquilino"]}
            )
            assert r.status_code == 201, r.text
            self._tok = r.json()["token"]
            self._tok_id = r.json()["id"]
        return self._tok

    def cliente(self):
        c = novo_cliente()
        return c

    def cabecalho(self) -> dict:
        return {"authorization": f"Bearer {self.token()}"}

    def iniciar(
        self, nome: str, dados: bytes, tipo_declarado: str, sha256: str | None = None, esperado: int = 201
    ) -> dict:
        c = self.cliente()
        corpo = {"nome": nome, "bytes": len(dados), "tipo_declarado": tipo_declarado}
        if sha256:
            corpo["sha256"] = sha256
        r = c.post("/api/uploads", json=corpo, headers=self.cabecalho())
        assert r.status_code == esperado, r.text
        if esperado == 201:
            self.uploads.append(r.json()["id"])
        return r

    def enviar_partes(self, upload_id: str, dados: bytes, parte_bytes: int, extra_headers: dict | None = None):
        c = self.cliente()
        n = 1
        i = 0
        respostas = []
        while i < len(dados):
            pedaco = dados[i : i + parte_bytes]
            headers = dict(self.cabecalho())
            if extra_headers:
                headers.update(extra_headers)
            r = c.put(f"/api/uploads/{upload_id}/partes/{n}", content=pedaco, headers=headers)
            respostas.append(r)
            i += parte_bytes
            n += 1
        return respostas

    def concluir(self, upload_id: str, sha256: str | None = None, esperado: int = 202) -> dict:
        c = self.cliente()
        corpo = {"sha256": sha256} if sha256 else {}
        r = c.post(f"/api/uploads/{upload_id}/concluir", json=corpo, headers=self.cabecalho())
        assert r.status_code == esperado, r.text
        if esperado == 202:
            self.arquivos.append(r.json()["arquivo_id"])
        return r

    def liberar_token(self) -> None:
        if self._tok_id is not None:
            self.sessao.delete(f"/api/tokens/{self._tok_id}")
            self._tok_id = None


@pytest.fixture
def up_a(sessao_a):
    u = Uploader(sessao_a)
    yield u
    u.liberar_token()
    for iid in u.arquivos:
        try:
            sessao_a.delete(f"/api/itens/{iid}")
        except Exception:  # noqa: BLE001 — limpeza best-effort
            pass
    for upid in u.uploads:
        try:
            c = u.cliente()
            c.delete(f"/api/uploads/{upid}", headers=u.cabecalho())
        except Exception:  # noqa: BLE001
            pass


def _csv_de(tamanho: int) -> bytes:
    """CSV determinístico e reproduzível, sem byte nulo (prova o tipo `csv`), do tamanho exato pedido."""
    linha = b"talhao,area_ha,cultura\n1,12.50,soja\n"
    repeticoes = tamanho // len(linha) + 1
    return (linha * repeticoes)[:tamanho]


def _zip_com(entradas: dict[str, bytes]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for nome, conteudo in entradas.items():
            zf.writestr(nome, conteudo)
    return buf.getvalue()


# ---------------------------------------------------------------- portão de pronto
def test_100mb_em_7_partes_com_reenvio_da_4_sha256_igual(up_a, medida):
    """Cláusula literal do portão: 100 MB em 7 partes, parte 4 reenviada, sha256 do objeto == sha256 local."""
    tamanho = 100 * 1024 * 1024  # 100 MiB -> ceil(104857600 / 16777216) = 7 partes
    dados = _csv_de(tamanho)
    sha_local = hashlib.sha256(dados).hexdigest()

    r = up_a.iniciar(f"{PREFIXO_TESTE}-cem-mb.csv", dados, "csv")
    corpo = r.json()
    upload_id = corpo["id"]
    assert corpo["partes"] == 7, corpo
    assert corpo["parte_bytes"] == 16 * 1024 * 1024

    t0 = time.monotonic()
    parte_bytes = corpo["parte_bytes"]
    respostas = up_a.enviar_partes(upload_id, dados, parte_bytes)
    for r_parte in respostas:
        assert r_parte.status_code == 200, r_parte.text
    ultima = respostas[-1].json()
    assert ultima["recebidas"] == 7 and ultima["faltam"] == []

    # reenvia a parte 4 (índice 3), fora de ordem em relação ao fluxo original -- idempotente
    c = up_a.cliente()
    inicio_p4 = 3 * parte_bytes
    pedaco_p4 = dados[inicio_p4 : inicio_p4 + parte_bytes]
    r4 = c.put(f"/api/uploads/{upload_id}/partes/4", content=pedaco_p4, headers=up_a.cabecalho())
    assert r4.status_code == 200, r4.text
    assert r4.json()["recebidas"] == 7 and r4.json()["faltam"] == []

    resultado = up_a.concluir(upload_id, sha256=sha_local)
    corpo_final = resultado.json()
    elapsed = time.monotonic() - t0
    assert corpo_final["sha256"] == sha_local
    assert corpo_final["bytes"] == tamanho

    medida("L0-04-a-upload-arquivo")(
        "taxa_upload_mb_s", round((tamanho / (1024 * 1024)) / elapsed, 2), "MB/s",
        "tests/api/uploads/test_uploads.py::test_100mb_em_7_partes_com_reenvio_da_4_sha256_igual",
    )


def test_partes_fora_de_ordem_tambem_fecham(up_a):
    """"partes fora de ordem" (addPart da Esri): envia a última parte antes da primeira."""
    tamanho = 3 * 1024 * 1024  # cabe em 1 parte (< 16 MiB) -- usa arquivo maior para ter >= 2 partes reais
    tamanho = 20 * 1024 * 1024
    dados = _csv_de(tamanho)
    r = up_a.iniciar(f"{PREFIXO_TESTE}-fora-de-ordem.csv", dados, "csv")
    corpo = r.json()
    upload_id = corpo["id"]
    parte_bytes = corpo["parte_bytes"]
    assert corpo["partes"] == 2
    c = up_a.cliente()
    p2 = dados[parte_bytes:]
    p1 = dados[:parte_bytes]
    r2 = c.put(f"/api/uploads/{upload_id}/partes/2", content=p2, headers=up_a.cabecalho())
    assert r2.status_code == 200, r2.text
    assert r2.json()["faltam"] == [1]
    r1 = c.put(f"/api/uploads/{upload_id}/partes/1", content=p1, headers=up_a.cabecalho())
    assert r1.status_code == 200, r1.text
    assert r1.json()["faltam"] == []
    resultado = up_a.concluir(upload_id, sha256=hashlib.sha256(dados).hexdigest())
    assert resultado.json()["bytes"] == tamanho


def test_gpkg_com_conteudo_zip_recusado_mensagem_exata(up_a):
    """Cláusula literal do portão: '.gpkg com conteúdo zip recusado com "conteúdo não corresponde ao tipo"'."""
    dados = _zip_com({"nao_e_gpkg.bin": b"qualquer coisa"})
    r = up_a.iniciar(f"{PREFIXO_TESTE}-falso.gpkg", dados, "gpkg")
    upload_id = r.json()["id"]
    up_a.enviar_partes(upload_id, dados, r.json()["parte_bytes"])
    resultado = up_a.concluir(upload_id, esperado=422)
    corpo = resultado.json()
    assert corpo["erro"] == "conteudo_nao_corresponde"
    assert "conteúdo não corresponde ao tipo" in corpo["mensagem"]
    # o objeto recusado não fica no bucket nem no upload continua "iniciado" (pode-se abortar sem 500)
    c = up_a.cliente()
    r_ver = c.get(f"/api/uploads/{upload_id}", headers=up_a.cabecalho())
    assert r_ver.status_code == 200
    assert r_ver.json()["estado"] == "iniciado"  # concluir falhou -> upload NÃO fica "concluido"


def test_arquivo_acima_do_maximo_413_antes_de_qualquer_byte(up_a):
    """Refutação do adversário: arquivo de 2,1 GiB (acima do teto desta fase) -> 413, e NENHUM byte é aceito
    (a checagem é só sobre o tamanho DECLARADO em POST /api/uploads, que não carrega corpo de arquivo)."""
    tamanho = int(2.1 * 1024 * 1024 * 1024)
    c = novo_cliente()
    r = c.post(
        "/api/uploads",
        json={"nome": f"{PREFIXO_TESTE}-gigante.zip", "bytes": tamanho, "tipo_declarado": "zip"},
        headers=up_a.cabecalho(),
    )
    assert r.status_code == 413, r.text
    assert r.json()["erro"] == "arquivo_grande"


def test_cota_insuficiente_413_antes_de_qualquer_byte(sessao_b, env):
    """Cláusula literal do portão (mecanismo de COTA, distinto do teto por arquivo acima): reduz a cota do
    inquilino B para um valor pequeno, declara um upload maior que a cota disponível -> 413 'cota' antes de
    qualquer parte ser enviada; restaura a cota original no fim (o inquilino B é o de teste cruzado da
    suíte -- outros testes o usam, mas a suíte inteira roda serializada por um `flock` só, então a janela de
    mutação nunca é concorrente com outro `pytest`)."""
    up_b = Uploader(sessao_b)
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    # SEM autocommit: `set_config(..., true)` (LOCAL) só vale dentro da transação corrente -- com autocommit
    # cada instrução vira sua própria transação e o contexto de RLS desapareceria antes da próxima consulta.
    try:
        tenant_id = ids_por_slug(con)["demo2"]
        _rls_contexto(con, tenant_id)  # RLS de plat.tenant exige id = tenant_atual() até para o próprio SELECT
        with con.cursor() as cur:
            cur.execute("SELECT cota_bytes FROM plat.tenant WHERE id = %s", (tenant_id,))
            cota_original = cur.fetchone()["cota_bytes"]
            cota_teste = 10 * 1024 * 1024  # 10 MiB de cota
            cur.execute("UPDATE plat.tenant SET cota_bytes = %s WHERE id = %s", (cota_teste, tenant_id))
            con.commit()
        try:
            c = novo_cliente()
            r = c.post(
                "/api/uploads",
                json={"nome": f"{PREFIXO_TESTE}-sem-cota.csv", "bytes": 20 * 1024 * 1024, "tipo_declarado": "csv"},
                headers=up_b.cabecalho(),
            )
            assert r.status_code == 413, r.text
            assert r.json()["erro"] == "cota"
            detalhe = r.json()["detalhe"]
            assert detalhe["cota_bytes"] == cota_teste
        finally:
            # o commit acima encerrou a transação e com ela o `set_config(..., true)` (LOCAL); precisa religar
            # o contexto de RLS antes desta 2ª escrita, senão a restauração afeta 0 linhas silenciosamente
            _rls_contexto(con, tenant_id)
            with con.cursor() as cur:
                cur.execute("UPDATE plat.tenant SET cota_bytes = %s WHERE id = %s", (cota_original, tenant_id))
                con.commit()
    finally:
        up_b.liberar_token()
        con.close()


def test_tipo_desconhecido_422(up_a):
    c = novo_cliente()
    r = c.post(
        "/api/uploads",
        json={"nome": "x.foo", "bytes": 100, "tipo_declarado": "formato-que-nao-existe"},
        headers=up_a.cabecalho(),
    )
    assert r.status_code == 422
    assert r.json()["erro"] == "tipo_desconhecido"


# ---------------------------------------------------------------- refutação do adversário (aqui de antemão)
def test_zip_bomba_1_milhao_de_entradas_recusado(up_a):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(1500):  # já acima do ZIP_ENTRADAS_MAX (1.000); 1 milhão travaria o teste em RAM à toa
            zf.writestr(f"f{i}.txt", b"a")
    dados = buf.getvalue()
    r = up_a.iniciar(f"{PREFIXO_TESTE}-bomba.zip", dados, "zip")
    upload_id = r.json()["id"]
    up_a.enviar_partes(upload_id, dados, r.json()["parte_bytes"])
    resultado = up_a.concluir(upload_id, esperado=422)
    assert resultado.json()["erro"] == "conteudo_nao_corresponde"
    assert "entradas" in resultado.json()["mensagem"]


def test_zip_caminho_dotdot_recusado(up_a):
    dados = _zip_com({"../fora_do_diretorio.txt": b"conteudo malicioso"})
    r = up_a.iniciar(f"{PREFIXO_TESTE}-traversal.zip", dados, "zip")
    upload_id = r.json()["id"]
    up_a.enviar_partes(upload_id, dados, r.json()["parte_bytes"])
    resultado = up_a.concluir(upload_id, esperado=422)
    assert resultado.json()["erro"] == "conteudo_nao_corresponde"


def test_duas_conclusoes_concorrentes_a_segunda_ve_ja_concluido(up_a):
    """Refutação: "duas sessões subindo o mesmo uploadId" -- aqui, duas *conclusões* concorrentes (o caso mais
    perigoso: as duas fechariam o multipart e criariam DOIS itens `arquivo` do mesmo objeto sem o FOR UPDATE).
    threads reais (não apenas chamadas sequenciais) para provar a serialização no banco."""
    import threading

    tamanho = 1 * 1024 * 1024
    dados = _csv_de(tamanho)
    r = up_a.iniciar(f"{PREFIXO_TESTE}-corrida.csv", dados, "csv")
    upload_id = r.json()["id"]
    up_a.enviar_partes(upload_id, dados, r.json()["parte_bytes"])

    resultados = []

    def _concluir():
        c = novo_cliente()
        resp = c.post(f"/api/uploads/{upload_id}/concluir", json={}, headers=up_a.cabecalho())
        resultados.append(resp)

    t1 = threading.Thread(target=_concluir)
    t2 = threading.Thread(target=_concluir)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    assert len(resultados) == 2
    status = sorted(r.status_code for r in resultados)
    assert status == [202, 409], [ (r.status_code, r.text) for r in resultados ]
    perdedor = next(r for r in resultados if r.status_code == 409)
    assert perdedor.json()["erro"] == "ja_concluido"
    ganhador = next(r for r in resultados if r.status_code == 202)
    up_a.arquivos.append(ganhador.json()["arquivo_id"])


def test_duas_sessoes_enviando_partes_diferentes_ao_mesmo_tempo(up_a):
    """Refutação literal do item: "duas sessões subindo o mesmo uploadId" no caso BENIGNO (o `addPart` da Esri
    permite isso de propósito) -- duas sessões do MESMO usuário, cada uma enviando uma parte DIFERENTE,
    concorrentes de verdade (threads), têm de terminar as duas OK e o conjunto fechar sem corrupção."""
    import threading

    tamanho = 48 * 1024 * 1024  # 3 partes de 16 MiB
    dados = _csv_de(tamanho)
    r = up_a.iniciar(f"{PREFIXO_TESTE}-corrida-partes.csv", dados, "csv")
    upload_id = r.json()["id"]
    parte_bytes = r.json()["parte_bytes"]
    assert r.json()["partes"] == 3

    resultados: dict[int, object] = {}

    def _enviar(n: int):
        c = novo_cliente()
        inicio = (n - 1) * parte_bytes
        pedaco = dados[inicio : inicio + parte_bytes]
        resultados[n] = c.put(f"/api/uploads/{upload_id}/partes/{n}", content=pedaco, headers=up_a.cabecalho())

    fios = [threading.Thread(target=_enviar, args=(n,)) for n in (1, 2, 3)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join(timeout=30)

    assert len(resultados) == 3
    for n, r_parte in resultados.items():
        assert r_parte.status_code == 200, (n, r_parte.text)
    ultimo = resultados[3].json()
    assert ultimo["recebidas"] == 3 and ultimo["faltam"] == []

    resultado = up_a.concluir(upload_id, sha256=hashlib.sha256(dados).hexdigest())
    assert resultado.json()["bytes"] == tamanho


def test_parte_de_outro_usuario_404(up_a, sessao_b):
    """"mesma regra dos itens": upload de A não existe para B (nem 403 -- 404, para não revelar)."""
    tamanho = 1024
    dados = _csv_de(tamanho)
    r = up_a.iniciar(f"{PREFIXO_TESTE}-privado.csv", dados, "csv")
    upload_id = r.json()["id"]
    up_b = Uploader(sessao_b)
    c = novo_cliente()
    r_ver = c.get(f"/api/uploads/{upload_id}", headers=up_b.cabecalho())
    assert r_ver.status_code == 404
    r_parte = c.put(f"/api/uploads/{upload_id}/partes/1", content=dados, headers=up_b.cabecalho())
    assert r_parte.status_code == 404
    up_b.liberar_token()


def test_content_length_divergente_422(up_a):
    dados = _csv_de(4096)
    r = up_a.iniciar(f"{PREFIXO_TESTE}-cl.csv", dados, "csv")
    upload_id = r.json()["id"]
    c = up_a.cliente()
    # o próprio httpx calcula o Content-Length certo para `content=`; força um corpo MENOR que o declarado (1
    # parte só, tamanho == bytes_declarado) para provar que o servidor confere o tamanho de verdade
    r2 = c.put(f"/api/uploads/{upload_id}/partes/1", content=dados[:-10], headers=up_a.cabecalho())
    assert r2.status_code == 422
    assert r2.json()["erro"] == "tamanho_parte_invalido"


def test_parte_sha256_divergente_422(up_a):
    dados = _csv_de(4096)
    r = up_a.iniciar(f"{PREFIXO_TESTE}-partesha.csv", dados, "csv")
    upload_id = r.json()["id"]
    c = up_a.cliente()
    headers = dict(up_a.cabecalho())
    headers["x-parte-sha256"] = "0" * 64
    r2 = c.put(f"/api/uploads/{upload_id}/partes/1", content=dados, headers=headers)
    assert r2.status_code == 422
    assert r2.json()["erro"] == "parte_sha256_divergente"


def test_concluir_com_partes_faltando_409(up_a):
    tamanho = 20 * 1024 * 1024
    dados = _csv_de(tamanho)
    r = up_a.iniciar(f"{PREFIXO_TESTE}-incompleto.csv", dados, "csv")
    upload_id = r.json()["id"]
    parte_bytes = r.json()["parte_bytes"]
    c = up_a.cliente()
    r1 = c.put(f"/api/uploads/{upload_id}/partes/1", content=dados[:parte_bytes], headers=up_a.cabecalho())
    assert r1.status_code == 200
    resultado = up_a.concluir(upload_id, esperado=409)
    assert resultado.json()["erro"] == "partes_faltando"
    assert resultado.json()["detalhe"]["faltam"] == [2]


def test_abortar_libera_a_reserva_de_cota(up_a, env):
    """A cota reservada por um upload em curso soma no cálculo de `POST /api/uploads` seguinte; abortar libera
    (a reserva É a soma de bytes_declarado com estado='iniciado', não um contador separado -- ver a migração)."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        tenant_id = ids_por_slug(con)["demo"]
    finally:
        con.close()
    ctx = banco.Contexto(tenant_id, 0, "teste")
    dados = _csv_de(1024 * 1024)
    r = up_a.iniciar(f"{PREFIXO_TESTE}-reserva.csv", dados, "csv")
    upload_id = r.json()["id"]
    with banco.db(ctx) as cur:
        cur.execute("SELECT plat.upload_reservado_bytes(%s) AS r", (tenant_id,))
        reservado_com_upload = cur.fetchone()["r"]
    assert reservado_com_upload >= len(dados)
    c = up_a.cliente()
    r_del = c.delete(f"/api/uploads/{upload_id}", headers=up_a.cabecalho())
    assert r_del.status_code == 204
    up_a.uploads.remove(upload_id)
    with banco.db(ctx) as cur:
        cur.execute("SELECT plat.upload_reservado_bytes(%s) AS r", (tenant_id,))
        reservado_sem_upload = cur.fetchone()["r"]
    assert reservado_sem_upload == reservado_com_upload - len(dados)


# ---------------------------------------------------------------- periódico de expurgo (24 h)
def test_upload_incompleto_some_em_24h_pelo_periodico(up_a, env):
    from app.uploads.periodicos import uploads_expirar

    dados = _csv_de(1024 * 1024)
    r = up_a.iniciar(f"{PREFIXO_TESTE}-expira.csv", dados, "csv")
    upload_id = r.json()["id"]
    up_a.uploads.remove(upload_id)  # o periódico o apaga; não sobra pro teardown tentar de novo

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        tenant_id = ids_por_slug(con)["demo"]
        _rls_contexto(con, tenant_id)
        with con.cursor() as cur:
            cur.execute(
                "UPDATE plat.upload SET atualizado_em = now() - interval '25 hours' WHERE id = %s::uuid",
                (upload_id,),
            )
            cur.execute(
                "SELECT tenant_id, usuario_id, upload_s3_id FROM plat.upload WHERE id = %s::uuid", (upload_id,)
            )
            linha = cur.fetchone()
            con.commit()  # a alteração precisa ser visível para a conexão NOVA que uploads_expirar vai abrir
    finally:
        con.close()

    class _CtxFalso:
        def db(self):
            return banco.db(banco.Contexto(linha["tenant_id"], linha["usuario_id"], "teste"))

        def progresso(self, pct, mensagem=""):
            pass

        def log(self, nivel, mensagem):
            pass

    resultado = uploads_expirar(_CtxFalso(), horas=24)
    assert resultado["candidatos"] >= 1
    assert resultado["abortados"] >= 1

    with banco.db(banco.Contexto(linha["tenant_id"], linha["usuario_id"], "teste")) as cur:
        cur.execute("SELECT estado FROM plat.upload WHERE id = %s::uuid", (upload_id,))
        assert cur.fetchone()["estado"] == "expirado"
    with pytest.raises(objetos.UploadInexistente):
        # o periódico já chamou parte_abortar(upload_s3_id) por dentro; a 2ª tentativa não acha mais a linha em
        # plat.arquivo_upload (apagada) -- prova que o multipart do Garage foi mesmo fechado, não só o rótulo
        with banco.db(banco.Contexto(linha["tenant_id"], linha["usuario_id"], "teste")) as cur:
            objetos.parte_abortar(cur, linha["upload_s3_id"])


def test_tipos_aceitos_lista_publica(up_a):
    c = novo_cliente()
    r = c.get("/api/uploads/tipos", headers=up_a.cabecalho())
    assert r.status_code == 200
    nomes = {t["tipo"] for t in r.json()}
    assert {"shapefile.zip", "gpkg", "geojson", "csv", "kml", "kmz", "gpx", "xlsx", "dxf", "dwg", "gdb.zip",
            "parquet", "fgb", "gml", "zip"} <= nomes
