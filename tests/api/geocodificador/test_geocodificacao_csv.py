"""Geocodificação de TABELA enviada pelo usuário (item L2-11-a-geocodificacao-csv), medida contra o CNEFE
2022 de Boa Vista/RR — o único município grande instalado nesta demo (140.505 endereços com número e
logradouro nomeado; a UF inteira foi instalada pelo item L2-11-b, `plat.geo_instalacao`).

O portão pede: 1.000 endereços de UM município com coordenada conhecida, >= 85 % com acerto 'número exato' a
<= 50 m, 0 % fora do município, pendentes na tela de revisão, arrasto gravando origem 'manual', e o tempo por
1.000 medido. Cada uma dessas cláusulas é um teste abaixo, e o número medido vai para
`tests/medidas/L2-11-a.json` (nome literal do portão) e para `tests/medidas/L2-11-a-geocodificacao-csv.json`.

O que a amostra tem de RUÍDO, de propósito (é a refutação do item): tipo de logradouro abreviado (RUA -> R.,
AVENIDA -> Av.), caixa mista e, num teste separado, CEP de outro município e número inexistente. O CNEFE já
vem sem acento (ASCII puro, conferido no item L2-11-b), então a prova de "sem acento" é feita pelo caminho
inverso: o endereço vai COM acento e tem de casar assim mesmo.

O job roda num worker de verdade (subprocesso, porta própria da trilha) — nada de executar a tarefa em
processo e chamar isso de job.
"""

from __future__ import annotations

import json
import os
import time
import uuid

import psycopg2
import pytest

from app.geocodificador import motor
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE, novo_cliente

COD_BOA_VISTA = 1400100
PORTA_WORKER = 18211          # porta própria desta trilha (o worker_extra do L0-05 usa 18159, e em 06/09
                              # outra trilha desta mesma máquina já ocupava a 18162: o WorkerExtra dá o /saude
                              # do processo ALHEIO por bom e o worker próprio morre calado — por isso a
                              # fixture abaixo confere que o /saude respondido é o do processo que ela subiu)
ITEM = "L2-11-a-geocodificacao-csv"
ITEM_PORTAO = "L2-11-a"       # nome literal do arquivo de medidas citado no portão
INVERSO_TIPO = {"RUA": "R.", "AVENIDA": "Av.", "TRAVESSA": "Trav.", "RODOVIA": "Rod.", "ESTRADA": "Est."}


# --------------------------------------------------------------------------- apoio


def _ruidoso(tipo: str, nome: str) -> str:
    """Abrevia o tipo de logradouro e embaralha a caixa, sem mudar o significado."""
    abrev = INVERSO_TIPO.get((tipo or "").upper(), tipo or "")
    palavras = (nome or "").split(" ")
    mistas = [p.lower() if i % 2 else p.title() for i, p in enumerate(palavras)]
    return f"{abrev} {' '.join(mistas)}".strip()


def _csv(cabecalho: list[str], linhas: list[list[str]]) -> bytes:
    corpo = [",".join(f'"{c}"' for c in cabecalho)]
    corpo += [",".join(f'"{str(c)}"' for c in linha) for linha in linhas]
    return ("\n".join(corpo) + "\n").encode("utf-8")


class Lote:
    """Fluxo completo pela API: envia o arquivo, cria o item `arquivo`, cria a geocodificação e espera o job.
    Limpa a camada, o item e o lote no fim."""

    def __init__(self, sessao):
        self.sessao = sessao
        self.criados: list[str] = []      # geocodificacao_id
        self.arquivos: list[str] = []     # item_id de arquivo
        self._tok = None
        self._tok_id = None

    def _token(self) -> str:
        if self._tok is None:
            r = self.sessao.post("/api/tokens",
                                  json={"nome": f"{PREFIXO_TESTE}-geocod-{os.getpid()}",
                                        "escopos": ["admin:inquilino"]})
            assert r.status_code == 201, r.text
            self._tok = r.json()["token"]
            self._tok_id = r.json()["id"]
        return self._tok

    def liberar_token(self) -> None:
        if self._tok_id is not None:
            self.sessao.delete(f"/api/tokens/{self._tok_id}")
            self._tok_id = None

    def item_arquivo(self, conteudo: bytes, nome: str) -> str:
        sem_cookie = novo_cliente()
        r = sem_cookie.post("/api/arquivos?classe=camada_arquivo", content=conteudo,
                             headers={"authorization": f"Bearer {self._token()}",
                                      "content-type": "text/csv"})
        assert r.status_code == 201, r.text
        obj = r.json()
        r = self.sessao.post("/api/itens", json={
            "tipo": "arquivo", "titulo": f"{PREFIXO_TESTE} {nome}",
            "dados": {"chave": obj["chave"], "sha256": obj["sha256"], "bytes": obj["bytes"],
                      "content_type": obj["content_type"], "nome_original": nome},
        })
        assert r.status_code == 201, r.text
        iid = r.json()["id"]
        self.arquivos.append(iid)
        return iid

    def criar(self, conteudo: bytes, nome: str, mapeamento: dict, titulo: str | None = None,
               esperar: bool = True, timeout: float = 900) -> dict:
        arquivo_id = self.item_arquivo(conteudo, nome)
        r = self.sessao.post("/api/geocodificacoes", json={
            "arquivo_id": arquivo_id, "titulo": titulo or f"{PREFIXO_TESTE} {nome}",
            "mapeamento": mapeamento})
        assert r.status_code == 202, r.text
        gid = r.json()["geocodificacao_id"]
        self.criados.append(gid)
        if esperar:
            self.esperar(r.json()["job_id"], timeout)
        return self.detalhar(gid) | {"job_id": r.json()["job_id"]}

    def esperar(self, job_id: str, timeout: float = 900) -> dict:
        fim = time.monotonic() + timeout
        ultimo = None
        while time.monotonic() < fim:
            r = self.sessao.get(f"/api/jobs/{job_id}")
            assert r.status_code == 200, r.text
            ultimo = r.json()
            if ultimo["estado"] in ("concluido", "falhou", "cancelado"):
                return ultimo
            time.sleep(0.3)
        pytest.fail(f"job {job_id} não terminou em {timeout} s: {json.dumps(ultimo)[:500]}")

    def detalhar(self, gid: str) -> dict:
        r = self.sessao.get(f"/api/geocodificacoes/{gid}")
        assert r.status_code == 200, r.text
        return r.json()

    def linhas(self, gid: str, estado: str | None = None, limite: int = 500) -> list[dict]:
        q = f"?limite={limite}" + (f"&estado={estado}" if estado else "")
        r = self.sessao.get(f"/api/geocodificacoes/{gid}/linhas{q}")
        assert r.status_code == 200, r.text
        return r.json()["linhas"]


@pytest.fixture(scope="module")
def worker_lote(env):
    """Worker de verdade, em subprocesso, com o ambiente da trilha e porta própria."""
    from tests.api.jobs.conftest import WorkerExtra

    w = WorkerExtra(env, f"teste-geocod-{os.getpid()}", 1, PORTA_WORKER)
    saude = w.saude()
    assert saude["pid"] == w.proc.pid, (
        f"a porta {PORTA_WORKER} já era de outro worker ({saude['worker']}); escolha outra em PORTA_WORKER")
    yield w
    w.parar()


@pytest.fixture
def lote(sessao_a, worker_lote, env):
    ferramenta = Lote(sessao_a)
    yield ferramenta
    ferramenta.liberar_token()
    _limpar(env, ferramenta)


def _limpar(env, ferramenta: Lote) -> None:
    from app.catalogo import destruidores
    from tests.api.test_rls import contexto, ids_por_slug

    if not (ferramenta.criados or ferramenta.arquivos):
        return
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
            adm = cur.fetchone()["usuario_id"]
        contexto(con, ids["demo"], usuario_id=adm, login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
            camadas = []
            for gid in ferramenta.criados:
                cur.execute("SELECT item_id FROM plat.geocodificacao WHERE id = %s::uuid", (gid,))
                r = cur.fetchone()
                if r and r["item_id"]:
                    camadas.append(str(r["item_id"]))
            cur.execute("DELETE FROM plat.geocodificacao WHERE id = ANY(%s::uuid[])", (ferramenta.criados,))
            for iid in camadas + ferramenta.arquivos:
                cur.execute("SELECT tipo, dados, miniatura_chave FROM plat.item WHERE id = %s::uuid", (iid,))
                item = cur.fetchone()
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (iid,))
                if item is not None:
                    try:
                        destruidores.destruir(cur, item["tipo"], item["dados"], item["miniatura_chave"],
                                              lambda *_a, **_k: None)
                    except Exception:  # noqa: BLE001 - limpeza de teste, nunca derruba o resultado
                        pass
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (iid,))
        con.commit()
    finally:
        con.close()


@pytest.fixture(scope="module")
def verdade_1000(env):
    """1.000 endereços de Boa Vista com coordenada conhecida do IBGE (amostra aleatória com semente fixa)."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT setseed(0.2026)")
            cur.execute(
                "SELECT e.tipo_logradouro, e.nome_logradouro, e.numero, e.cep, e.localidade, "
                "  m.nome AS municipio, u.sigla AS uf, e.lat, e.lon, e.cod_municipio "
                "FROM plat.geo_endereco e JOIN plat.geo_municipio m ON m.cod = e.cod_municipio "
                "JOIN plat.geo_uf u ON u.cod = m.cod_uf "
                "WHERE e.cod_municipio = %s AND e.numero IS NOT NULL AND e.numero > 0 "
                "  AND e.nome_logradouro <> 'SEM DENOMINACAO' ORDER BY random() LIMIT 1000",
                (COD_BOA_VISTA,),
            )
            linhas = [dict(r) for r in cur.fetchall()]
    finally:
        con.rollback()
        con.close()
    if len(linhas) < 1000:
        pytest.skip("CNEFE de Boa Vista/RR não instalado nesta base (item L2-11-b)")
    return linhas


def _conexao_do_inquilino(env):
    """Conexão como a role da aplicação COM o contexto de inquilino posto (`plat.tenant_id`). Sem isso a RLS
    FORCE da camada (plat.camada_preparar) esconde toda linha e o teste leria zero achando que não há ponto —
    foi o que aconteceu na primeira rodada desta suíte."""
    from tests.api.test_rls import contexto, ids_por_slug

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    ids = ids_por_slug(con)
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(con, ids["demo"], usuario_id=adm, login="admin")
    return con


def _gravar(medida, nome: str, valor, unidade: str, comando: str) -> None:
    """Grava a MESMA medida nos dois arquivos: o nome literal do portão e o nome do item."""
    medida(ITEM_PORTAO)(nome, valor, unidade, comando)
    medida(ITEM)(nome, valor, unidade, comando)


# --------------------------------------------------------------------------- portão


@pytest.fixture(scope="module")
def lote_1000(sessao_a, worker_lote, verdade_1000, env):
    """O lote de 1.000 endereços, geocodificado UMA vez para o módulo inteiro (o job leva minutos)."""
    ferramenta = Lote(sessao_a)
    conteudo = _csv(
        ["id", "logradouro", "numero", "municipio", "uf"],
        [[i, _ruidoso(r["tipo_logradouro"], r["nome_logradouro"]), r["numero"], r["municipio"], r["uf"]]
         for i, r in enumerate(verdade_1000, start=1)],
    )
    inicio = time.monotonic()
    detalhe = ferramenta.criar(conteudo, "cnefe_boa_vista_1000.csv",
                                {"logradouro": "logradouro", "numero": "numero",
                                 "municipio": "municipio", "uf": "uf"},
                                titulo=f"{PREFIXO_TESTE} 1000 endereços de Boa Vista")
    detalhe["segundos_parede"] = time.monotonic() - inicio
    detalhe["ferramenta"] = ferramenta
    detalhe["bytes"] = len(conteudo)
    yield detalhe
    ferramenta.liberar_token()
    _limpar(env, ferramenta)


def test_1000_enderecos_acerto_numero_exato_a_50_m(lote_1000, verdade_1000, medida):
    """Cláusula 1 e 2 do portão: >= 85 % com acerto 'número exato' a <= 50 m, e 0 % fora do município."""
    assert lote_1000["estado"] == "concluida", lote_1000
    assert lote_1000["linhas_total"] == 1000, lote_1000
    ferramenta = lote_1000["ferramenta"]
    linhas = []  # o teto de página é 500 (limites.GEOCOD_LINHAS_PAGINA_MAX): duas páginas
    for deslocamento in (0, 500):
        r = ferramenta.sessao.get(
            f"/api/geocodificacoes/{lote_1000['id']}/linhas?limite=500&deslocamento={deslocamento}")
        assert r.status_code == 200, r.text
        linhas += r.json()["linhas"]
    assert len(linhas) == 1000, len(linhas)

    por_n = {li["n"]: li for li in linhas}
    exatos_50 = 0
    fora_do_municipio = 0
    distancias = []
    for i, verdade in enumerate(verdade_1000, start=1):
        li = por_n[i]
        if li["lon"] is None:
            continue
        d = motor.distancia_m(li["lon"], li["lat"], verdade["lon"], verdade["lat"])
        distancias.append(d)
        if li["tipo_acerto"] == "numero_exato" and d <= 50:
            exatos_50 += 1
        if li["cod_municipio"] != verdade["cod_municipio"]:
            fora_do_municipio += 1

    pct_exato = exatos_50 / 1000 * 100
    pct_fora = fora_do_municipio / 1000 * 100
    distancias.sort()
    mediana = distancias[len(distancias) // 2] if distancias else None
    nome = "test_1000_enderecos_acerto_numero_exato_a_50_m"
    _gravar(medida, "lote_1000_universo", 1000, "endereços", nome)
    _gravar(medida, "lote_1000_acerto_numero_exato_50m", round(pct_exato, 1), "%", nome)
    _gravar(medida, "lote_1000_fora_do_municipio", round(pct_fora, 1), "%", nome)
    _gravar(medida, "lote_1000_erro_mediano", round(mediana, 1) if mediana is not None else None, "m", nome)
    _gravar(medida, "lote_1000_resolvidas", lote_1000["resolvidas"], "linhas", nome)
    _gravar(medida, "lote_1000_pendentes", lote_1000["pendentes"], "linhas", nome)
    assert pct_exato >= 85, f"acerto 'número exato' a <= 50 m em {pct_exato:.1f}% (portão: 85%)"
    assert pct_fora == 0, f"{fora_do_municipio} ponto(s) fora do município pedido"


def test_1000_enderecos_tempo_medido(lote_1000, medida):
    """Cláusula 6 do portão: tempo por 1.000 endereços MEDIDO (não é limiar, é registro)."""
    resumo = lote_1000["resumo"] or {}
    nome = "test_1000_enderecos_tempo_medido"
    _gravar(medida, "lote_1000_segundos_no_job", resumo.get("segundos"), "s", nome)
    _gravar(medida, "lote_1000_segundos_por_1000", resumo.get("segundos_por_1000"), "s/1000", nome)
    _gravar(medida, "lote_1000_segundos_de_parede", round(lote_1000["segundos_parede"], 1), "s", nome)
    _gravar(medida, "lote_1000_arquivo_bytes", lote_1000["bytes"], "bytes", nome)
    _gravar(medida, "lote_1000_cache_taxa_acerto", resumo.get("cache_taxa_acerto"), "fração", nome)
    assert resumo.get("segundos") and resumo["segundos"] > 0, resumo


def test_camada_publicada_tem_colunas_de_qualidade(lote_1000, env):
    """A camada de pontos nasce com pontuação, tipo de acerto e ORIGEM — é o que separa medido de arrastado."""
    item_id = lote_1000["item_id"]
    assert item_id, lote_1000
    sessao = lote_1000["ferramenta"].sessao
    r = sessao.get(f"/api/itens/{item_id}")
    assert r.status_code == 200, r.text
    dados = r.json()["dados"]
    assert dados["geometria"] == "Point" and dados["srid"] == 4326
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s", (dados["schema"], dados["tabela"]))
            colunas = {r["column_name"] for r in cur.fetchall()}
    finally:
        con.rollback()
        con.close()
    for obrigatoria in ("geo_score", "geo_tipo_acerto", "geo_origem", "geo_municipio_cod", "geom", "linha"):
        assert obrigatoria in colunas, f"coluna {obrigatoria} ausente na camada publicada: {sorted(colunas)}"


def test_ficha_de_proveniencia_traz_a_versao_da_base_de_enderecos(lote_1000):
    """Cláusula do item: 'ficha de proveniência com a versão da base de endereços'."""
    base = lote_1000["base_enderecos"]
    assert base["base"].startswith("CNEFE 2022"), base
    ufs = {u["uf"] for u in base["ufs_instaladas"]}
    assert "RR" in ufs, base
    rr = next(u for u in base["ufs_instaladas"] if u["uf"] == "RR")
    assert rr["enderecos"] > 250_000 and rr["sha256_zip"] and rr["instalado_em"], rr
    sessao = lote_1000["ferramenta"].sessao
    dados = sessao.get(f"/api/itens/{lote_1000['item_id']}").json()["dados"]
    proc = dados["procedencia"]
    assert proc["sha256"] and proc["metodo"] and proc["gerador"], proc
    assert proc["base_enderecos"]["ufs_instaladas"], proc
    assert any("centróide" in li or "centro do município" in li for li in proc["limites"]), proc["limites"]


# --------------------------------------------------------------------------- refutação do adversário


def test_nenhum_ponto_no_centroide_do_municipio_sem_estar_marcado(lote_1000, env):
    """Refutação literal: 'confere que nenhum ponto cai no centroide do município sem estar marcado como
    tal'. A prova é geométrica, direto na camada: todo ponto a menos de 1 m do centróide de algum município
    do CNEFE tem de ter geo_tipo_acerto = 'aproximado_no_municipio'."""
    sessao = lote_1000["ferramenta"].sessao
    dados = sessao.get(f"/api/itens/{lote_1000['item_id']}").json()["dados"]
    con = _conexao_do_inquilino(env)
    try:
        with con.cursor() as cur:
            cur.execute(
                f'SELECT c.linha, c.geo_tipo_acerto, m.nome '
                f'FROM "{dados["schema"]}"."{dados["tabela"]}" c '
                "JOIN plat.geo_municipio m ON ST_DWithin(c.geom::geography, "
                "  ST_SetSRID(ST_MakePoint(m.centro_lon, m.centro_lat), 4326)::geography, 1.0) "
                "WHERE c.geo_tipo_acerto IS DISTINCT FROM 'aproximado_no_municipio'"
            )
            disfarcados = cur.fetchall()
    finally:
        con.rollback()
        con.close()
    assert disfarcados == [], f"ponto no centróide do município sem estar marcado: {disfarcados[:5]}"


def test_adversario_abreviacao_acento_cep_errado_e_numero_inexistente(lote, verdade_1000, env):
    """Endereços sujos de propósito, um por caso, todos do mesmo arquivo:
      1-2. abreviação (R./Av.) e caixa mista — já provado em massa no lote de 1.000, aqui de novo isolado;
      3. COM acento (o CNEFE é ASCII: a dobra tem de acontecer no banco, por `unaccent`);
      4. CEP de OUTRO município junto do município certo — inconsistência, nunca ponto silencioso;
      5. número que não existe na via — recuo marcado, nunca 'numero_exato';
      6. logradouro que não existe em lugar nenhum — pendente com motivo.
    Nenhum destes pode virar ponto no centróide do município sem o tipo de acerto dizer isso."""
    modelo = verdade_1000[0]
    via = f"{modelo['tipo_logradouro']} {modelo['nome_logradouro']}"
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT e.cep FROM plat.geo_endereco e WHERE e.cod_uf = 14 AND e.cep IS NOT NULL "
                "AND e.cod_municipio <> %s LIMIT 1", (COD_BOA_VISTA,))
            cep_de_outro = cur.fetchone()["cep"]
            cur.execute(
                "SELECT max(numero) AS maximo FROM plat.geo_endereco WHERE cod_municipio = %s "
                "AND logradouro_norm = upper(public.unaccent(%s))", (COD_BOA_VISTA, via))
            maximo = (cur.fetchone() or {}).get("maximo") or 1000
    finally:
        con.rollback()
        con.close()

    com_acento = via.replace("A", "Á", 1) if "A" in via else via
    casos = [
        ["1", _ruidoso(modelo["tipo_logradouro"], modelo["nome_logradouro"]), modelo["numero"],
         "Boa Vista", "RR", ""],
        ["2", via.lower(), modelo["numero"], "boa vista", "rr", ""],
        ["3", com_acento, modelo["numero"], "Boa Vista", "RR", ""],
        ["4", via, modelo["numero"], "Boa Vista", "RR", cep_de_outro],
        ["5", via, str(int(maximo) + 900000)[:6], "Boa Vista", "RR", ""],
        ["6", "RUA QUE NAO EXISTE ZZQQXX", "10", "Boa Vista", "RR", ""],
    ]
    conteudo = _csv(["caso", "logradouro", "numero", "municipio", "uf", "cep"], casos)
    detalhe = lote.criar(conteudo, "adversario.csv",
                          {"logradouro": "logradouro", "numero": "numero", "municipio": "municipio",
                           "uf": "uf", "cep": "cep"})
    assert detalhe["estado"] == "concluida", detalhe
    linhas = {li["n"]: li for li in lote.linhas(detalhe["id"])}
    assert len(linhas) == 6, linhas

    for n in (1, 2, 3):
        li = linhas[n]
        assert li["estado"] == "resolvida", (n, li)
        assert li["tipo_acerto"] in ("numero_exato", "interpolado_na_face"), (n, li)
        d = motor.distancia_m(li["lon"], li["lat"], modelo["lon"], modelo["lat"])
        assert d <= 50, f"caso {n} caiu a {d:.0f} m do ponto do IBGE"

    # 4: CEP de outro município com o município certo = inconsistência declarada, sem ponto
    assert linhas[4]["estado"] == "pendente", linhas[4]
    assert "CEP" in (linhas[4]["motivo"] or ""), linhas[4]
    assert linhas[4]["lon"] is None, linhas[4]

    # 5: número inexistente = recuo MARCADO, nunca 'numero_exato'
    assert linhas[5]["tipo_acerto"] != "numero_exato", linhas[5]
    assert linhas[5]["tipo_acerto"] in ("interpolado_na_face", "aproximado_no_logradouro"), linhas[5]
    assert linhas[5]["avisos"], "recuo sem aviso"

    # 6: logradouro inexistente = recuo para o município, MARCADO como tal (nunca ponto silencioso)
    seis = linhas[6]
    if seis["estado"] == "resolvida":
        assert seis["tipo_acerto"] == "aproximado_no_municipio", seis
        assert any("centro do município" in a for a in seis["avisos"]), seis
    else:
        assert seis["motivo"], seis


# --------------------------------------------------------------------------- linha ruim e teto de tamanho


def test_linha_malformada_nao_derruba_o_lote(lote, verdade_1000):
    """Regra do turno: 'linha malformada não derruba o trabalho todo'. Arquivo com 3 linhas boas e 3 ruins:
    o job CONCLUI, as boas viram ponto e as ruins ficam registradas com motivo."""
    bons = verdade_1000[:3]
    linhas = [[i, f"{r['tipo_logradouro']} {r['nome_logradouro']}", r["numero"], "Boa Vista", "RR"]
              for i, r in enumerate(bons, start=1)]
    conteudo = _csv(["id", "logradouro", "numero", "municipio", "uf"], linhas)
    # três linhas quebradas coladas no fim: colunas faltando, linha em branco e só o separador
    conteudo += b'"4","Rua sem o resto"\n\n",,,,"\n'
    detalhe = lote.criar(conteudo, "com_linha_ruim.csv",
                          {"logradouro": "logradouro", "numero": "numero", "municipio": "municipio",
                           "uf": "uf"})
    assert detalhe["estado"] == "concluida", detalhe
    assert detalhe["resolvidas"] == 3, detalhe
    assert detalhe["malformadas"] >= 2, detalhe
    ruins = lote.linhas(detalhe["id"], estado="malformada")
    assert all(li["motivo"] for li in ruins), ruins
    assert detalhe["item_id"], "a camada tinha de ser publicada mesmo com linha ruim no arquivo"


def test_teto_de_tamanho_recusa_o_arquivo(lote, monkeypatch):
    """Prova do teto com BYTES REAIS: o teto é baixado para 64 KiB e um arquivo de 128 KiB de verdade é
    enviado — a recusa (413) vem do comprimento REAL do objeto lido do armazenamento, não do que o cliente
    declara. O valor de produção (32 MiB) fica conferido por asserção; um envio de 33 MiB não foi feito
    porque o disco desta máquina está a 98 % (D21) — está escrito no handoff do item."""
    from app import limites

    assert limites.GEOCOD_ARQUIVO_BYTES_MAX == 32 * 1024 * 1024
    monkeypatch.setattr(limites, "GEOCOD_ARQUIVO_BYTES_MAX", 64 * 1024)
    linha = b'"1","Rua A","10","Boa Vista","RR"\n'
    conteudo = b'"id","logradouro","numero","municipio","uf"\n' + linha * (128 * 1024 // len(linha))
    assert len(conteudo) > 64 * 1024
    arquivo_id = lote.item_arquivo(conteudo, "grande_demais.csv")
    r = lote.sessao.post("/api/geocodificacoes", json={
        "arquivo_id": arquivo_id, "titulo": f"{PREFIXO_TESTE} grande demais",
        "mapeamento": {"logradouro": "logradouro", "municipio": "municipio"}})
    assert r.status_code == 413, r.text
    assert r.json()["erro"] == "arquivo_grande_demais", r.text
    assert r.json()["detalhe"]["teto_bytes"] == 64 * 1024


def test_colunas_propostas_pela_api(lote):
    conteudo = _csv(["Logradouro", "Nº", "Cidade", "UF", "Cliente"], [["Rua A", "1", "Boa Vista", "RR", "x"]])
    arquivo_id = lote.item_arquivo(conteudo, "so_cabecalho.csv")
    r = lote.sessao.post("/api/geocodificacoes/colunas", json={"arquivo_id": arquivo_id})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["colunas"] == ["Logradouro", "Nº", "Cidade", "UF", "Cliente"]
    assert corpo["mapeamento_proposto"]["municipio"] == "Cidade"
    assert "endereco" in corpo["campos_aceitos"]


def test_mapeamento_invalido_e_422(lote):
    conteudo = _csv(["a", "b"], [["1", "2"]])
    arquivo_id = lote.item_arquivo(conteudo, "sem_endereco.csv")
    r = lote.sessao.post("/api/geocodificacoes", json={
        "arquivo_id": arquivo_id, "titulo": "x", "mapeamento": {"uf": "a"}})
    assert r.status_code == 422 and r.json()["erro"] == "mapeamento_invalido", r.text


# --------------------------------------------------------------------------- revisão manual


@pytest.fixture
def lote_com_pendente(lote, verdade_1000):
    """Um lote pequeno com uma linha que o motor NÃO resolve (logradouro inexistente e sem município), para
    provar a tela de revisão e o arrasto."""
    bom = verdade_1000[1]
    conteudo = _csv(
        ["id", "logradouro", "numero", "municipio", "uf"],
        [["1", f"{bom['tipo_logradouro']} {bom['nome_logradouro']}", bom["numero"], "Boa Vista", "RR"],
         ["2", "ZZQQXXWWKKVV NAO EXISTE", "1", "", ""]],
    )
    detalhe = lote.criar(conteudo, "com_pendente.csv",
                          {"logradouro": "logradouro", "numero": "numero", "municipio": "municipio",
                           "uf": "uf"})
    assert detalhe["estado"] == "concluida", detalhe
    return detalhe


def test_pendente_aparece_na_lista_de_revisao(lote, lote_com_pendente):
    """Cláusula 3 do portão: 'pendentes aparecem na tela de revisão'. A tela lê esta rota com estado=pendente."""
    assert lote_com_pendente["pendentes"] == 1, lote_com_pendente
    pendentes = lote.linhas(lote_com_pendente["id"], estado="pendente")
    assert [li["n"] for li in pendentes] == [2], pendentes
    assert pendentes[0]["lon"] is None and pendentes[0]["motivo"], pendentes[0]
    r = lote.sessao.get(f"/geocodificacoes/{lote_com_pendente['id']}")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"], r.status_code


def test_arrasto_grava_coordenada_com_origem_manual(lote, lote_com_pendente, env):
    """Cláusula 4 do portão: 'o arrasto grava a coordenada com origem manual'. A rota que a tela chama no
    evento `dragend` é esta; a prova vai até o ponto DENTRO da camada publicada."""
    gid = lote_com_pendente["id"]
    r = lote.sessao.put(f"/api/geocodificacoes/{gid}/linhas/2", json={"lon": -60.6733, "lat": 2.8235})
    assert r.status_code == 200, r.text
    assert r.json()["origem"] == "manual" and r.json()["tipo_acerto"] == "manual", r.json()

    linha = next(li for li in lote.linhas(gid) if li["n"] == 2)
    assert linha["estado"] == "resolvida" and linha["origem"] == "manual", linha
    assert abs(linha["lon"] - (-60.6733)) < 1e-9 and abs(linha["lat"] - 2.8235) < 1e-9, linha
    assert linha["score"] is None, "coordenada arrastada não tem pontuação de máquina"

    detalhe = lote.detalhar(gid)
    assert detalhe["manuais"] == 1 and detalhe["pendentes"] == 0, detalhe

    dados = lote.sessao.get(f"/api/itens/{detalhe['item_id']}").json()["dados"]
    con = _conexao_do_inquilino(env)
    try:
        with con.cursor() as cur:
            cur.execute(
                f'SELECT geo_origem, geo_tipo_acerto, geo_score, ST_X(geom) AS x, ST_Y(geom) AS y '
                f'FROM "{dados["schema"]}"."{dados["tabela"]}" WHERE linha = 2')
            ponto = cur.fetchone()
    finally:
        con.rollback()
        con.close()
    assert ponto is not None, "o ponto arrastado tinha de existir na camada"
    assert ponto["geo_origem"] == "manual" and ponto["geo_score"] is None, ponto
    assert abs(ponto["x"] - (-60.6733)) < 1e-9 and abs(ponto["y"] - 2.8235) < 1e-9, ponto


def test_regeocodificar_so_pendentes_e_nao_apaga_o_manual(lote, verdade_1000):
    """Cláusula 5 do portão: 're-geocodificar só os pendentes'. Duas linhas pendentes; uma é arrastada à mão
    antes de refazer — depois de refazer, a arrastada continua manual e intacta."""
    bom = verdade_1000[2]
    conteudo = _csv(
        ["id", "logradouro", "numero", "municipio", "uf"],
        [["1", f"{bom['tipo_logradouro']} {bom['nome_logradouro']}", bom["numero"], "Boa Vista", "RR"],
         ["2", "ZZQQXX NAO EXISTE UM", "1", "", ""],
         ["3", "ZZQQXX NAO EXISTE DOIS", "2", "", ""]],
    )
    detalhe = lote.criar(conteudo, "refazer.csv",
                          {"logradouro": "logradouro", "numero": "numero", "municipio": "municipio",
                           "uf": "uf"})
    gid = detalhe["id"]
    assert detalhe["pendentes"] == 2, detalhe

    r = lote.sessao.put(f"/api/geocodificacoes/{gid}/linhas/2", json={"lon": -60.60, "lat": 2.80})
    assert r.status_code == 200, r.text

    r = lote.sessao.post(f"/api/geocodificacoes/{gid}/regeocodificar", json={})
    assert r.status_code == 202, r.text
    assert r.json()["pendentes"] == 1, r.json()
    lote.esperar(r.json()["job_id"], timeout=300)

    final = lote.detalhar(gid)
    assert final["estado"] == "concluida", final
    assert final["resumo"]["so_pendentes"] is True, final["resumo"]
    assert final["resumo"]["linhas_geocodificadas_nesta_execucao"] == 1, final["resumo"]
    linhas = {li["n"]: li for li in lote.linhas(gid)}
    assert linhas[2]["origem"] == "manual" and abs(linhas[2]["lon"] - (-60.60)) < 1e-9, linhas[2]
    assert linhas[1]["origem"] == "automatica", linhas[1]
    assert linhas[3]["estado"] == "pendente", linhas[3]

    r = lote.sessao.post(f"/api/geocodificacoes/{gid}/regeocodificar", json={})
    assert r.status_code == 202, r.text
    lote.esperar(r.json()["job_id"], timeout=300)


def test_lote_de_outro_inquilino_e_404(lote, lote_com_pendente, sessao_b):
    r = sessao_b.get(f"/api/geocodificacoes/{lote_com_pendente['id']}")
    assert r.status_code == 404, r.text
    r = sessao_b.put(f"/api/geocodificacoes/{lote_com_pendente['id']}/linhas/1",
                      json={"lon": -60.0, "lat": 2.0})
    assert r.status_code == 404, r.text


def test_rotas_exigem_sessao(cliente):
    assert cliente.get("/api/geocodificacoes").status_code == 401
    assert cliente.post("/api/geocodificacoes", json={"arquivo_id": str(uuid.uuid4()), "titulo": "x"}
                        ).status_code == 401
