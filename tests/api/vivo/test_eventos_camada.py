"""Atualização viva por SSE (item L2-06-d-atualizacao-viva-sse): `GET /api/eventos/camadas`.

Cláusulas do portão cobertas aqui:
* UPDATE numa feição gera evento SSE em ≤ 1 s para o cliente assinado (latência medida) e NENHUM evento
  para cliente de outro inquilino (teste cruzado, dois inquilinos de verdade);
* reconexão recupera o que passou pelo cabeçalho `Last-Event-ID` (inclusive o inválido, que não derruba);
* fallback: com o fluxo desligado por configuração a rota responde 503 e o painel volta ao intervalo;
* limite de conexões por inquilino declarado (`app/limites.py`) e recusado com 429;
* coalescência na origem: uma edição em LOTE (um comando SQL, N linhas) gera UM evento, não N.
"""

import asyncio
import json
import threading
import time

import psycopg2
import pytest

from app import limites
from app.db import Contexto
from app.schema_ambiente import CursorSchemaAmbiente
from app.vivo import eventos as mod
from tests.api.test_rls import ids_por_slug
from tests.api.vivo.conftest import conectar_como, tabela_fisica

ITEM = "L2-06-d-atualizacao-viva-sse"


def _quadro(bruto: bytes) -> dict | None:
    """Um quadro SSE cru (`event:`/`id:`/`data:`) vira dicionário. `None` para o keepalive (comentário)."""
    texto = bruto.decode("utf-8")
    if texto.startswith(":"):
        return None
    quadro: dict = {"id": None, "dados": None}
    linhas_dados = []
    for linha in texto.splitlines():
        if linha.startswith("event:"):
            quadro["evento"] = linha[6:].strip()
        elif linha.startswith("id:"):
            quadro["id"] = linha[3:].strip()
        elif linha.startswith("data:"):
            linhas_dados.append(linha[5:].strip())
    if linhas_dados:
        quadro["dados"] = json.loads("\n".join(linhas_dados))
    return quadro if quadro.get("evento") else None


def _ler_fluxo(ctx, tenant_id, camadas, ultimo_id=None, ao_pronto=None, parar_em=1, maximo_s=30,
               usuario_id=1) -> list[dict]:
    """Lê o gerador SSE (`app.vivo.eventos.gerar`) diretamente, em vez de por HTTP.

    Por quê: o `starlette.testclient` não sustenta leitura de um fluxo que NÃO TERMINA — a conexão de
    eventos de camada só fecha no teto de 30 min (`VIVO_SSE_DURACAO_MAX_S`), e a rodada de teste estourou
    os 600 s do semáforo esperando o `with cliente.stream(...)` devolver o controle (medido nesta sessão).
    O fluxo de job consegue porque todo job termina; aqui não há fim natural. O que se testa direto é o
    MESMO objeto que a rota devolve ao `StreamingResponse` (`app/vivo/rotas.py`), com os mesmos argumentos;
    o que fica sem cobertura por este caminho é só o transporte HTTP, e esse é exercitado pelos testes de
    recusa acima (cabeçalhos, 404, 422, 401, 503), que respondem sem fluxo.

    `ao_pronto` é chamado depois do primeiro quadro (`pronto`) — é a deixa para editar a camada.
    """
    async def correr() -> list[dict]:
        colhidos: list[dict] = []
        gerador = mod.gerar(ctx, tenant_id, usuario_id, camadas, ultimo_id)
        inicio = time.monotonic()
        try:
            async for bruto in gerador:
                quadro = _quadro(bruto)
                if quadro is None:
                    if time.monotonic() - inicio > maximo_s:
                        break
                    continue
                quadro["chegou_em"] = time.monotonic()
                colhidos.append(quadro)
                if quadro["evento"] == "pronto" and ao_pronto is not None:
                    ao_pronto()
                if sum(1 for q in colhidos if q["evento"] == "camada") >= parar_em:
                    break
                if time.monotonic() - inicio > maximo_s:
                    break
        finally:
            await gerador.aclose()
        return colhidos

    return asyncio.run(correr())


def _editar(env, camada: dict, atraso_s: float = 0.0, linhas: int | None = None) -> dict:
    """Uma edição na tabela física da camada. Devolve {'em': instante do COMMIT} — é do COMMIT que o
    Postgres solta o NOTIFY, então é dele que a latência tem de ser contada."""
    schema, tabela = tabela_fisica(env, camada["camada_id"], camada["slug"])
    marca = {}
    if atraso_s:
        time.sleep(atraso_s)
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            alvo = "" if linhas is None else f" WHERE fid IN (SELECT fid FROM \"{schema}\".\"{tabela}\" LIMIT {linhas})"
            cur.execute(f'UPDATE "{schema}"."{tabela}" SET valor = valor{alvo}')
        marca["em"] = time.monotonic()
        con.commit()
        marca["em"] = time.monotonic()
    finally:
        con.close()
    return marca


def _contar_eventos(env, camada: dict) -> int:
    con = conectar_como(env, camada["slug"])
    try:
        with con.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM plat.camada_evento WHERE camada_id = %s::uuid",
                        (camada["camada_id"],))
            return cur.fetchone()["n"]
    finally:
        con.close()


# ---------------------------------------------------------------- recusas (sem fluxo: respondem na hora)

def test_camada_de_outro_inquilino_e_404(sessao_b, camada_a):
    r = sessao_b.get(f"/api/eventos/camadas?camadas={camada_a['camada_id']}")
    assert r.status_code == 404 and r.json()["erro"] == "camada_inexistente", r.text


def test_lista_vazia_e_camadas_demais_sao_recusadas(sessao_a, camada_a):
    assert sessao_a.get("/api/eventos/camadas?camadas=").status_code == 400
    muitas = ",".join([camada_a["camada_id"]] * (limites.VIVO_SSE_CAMADAS_MAX + 1))
    r = sessao_a.get(f"/api/eventos/camadas?camadas={muitas}")
    # a lista é deduplicada DEPOIS do teto: pedir 51 vezes a mesma camada ainda é pedir 51 camadas
    assert r.status_code == 422 and r.json()["erro"] == "camadas_demais", r.text


def test_id_que_nao_e_uuid_e_404(sessao_a):
    r = sessao_a.get("/api/eventos/camadas?camadas=nao-e-uuid")
    assert r.status_code == 404 and r.json()["erro"] == "camada_invalida", r.text


def test_sem_sessao_e_401(cliente, camada_a):
    r = cliente.get(f"/api/eventos/camadas?camadas={camada_a['camada_id']}")
    assert r.status_code == 401


# ---------------------------------------------------------------- empurrão

@pytest.fixture()
def ctx_a(conexao_plat_app, camada_a):
    return Contexto(ids_por_slug(conexao_plat_app)["demo"], 1, "teste-vivo")


@pytest.fixture()
def ctx_b(conexao_plat_app, camada_b):
    return Contexto(ids_por_slug(conexao_plat_app)["demo2"], 1, "teste-vivo")


def _observar(env, camada: dict) -> None:
    """Instala o gatilho de notificação na tabela física (o que a rota faz ao abrir a conexão)."""
    con = conectar_como(env, camada["slug"])
    try:
        with con.cursor() as cur:
            cur.execute("SELECT plat.camada_observar(%s::uuid) AS ok", (camada["camada_id"],))
            assert cur.fetchone()["ok"] is True
    finally:
        con.close()


@pytest.mark.lento
def test_update_chega_ao_cliente_assinado_em_ate_um_segundo(ctx_a, camada_a, env, medida):
    cid = camada_a["camada_id"]
    _observar(env, camada_a)
    marca: dict = {}
    linha = threading.Thread(target=lambda: marca.update(_editar(env, camada_a, atraso_s=1.0)), daemon=True)
    quadros = _ler_fluxo(ctx_a, ctx_a.tenant_id, [cid], ao_pronto=linha.start, parar_em=1, maximo_s=40)
    linha.join(timeout=10)

    assert quadros[0]["evento"] == "pronto"
    assert cid in quadros[0]["dados"]["camadas"] and cid in quadros[0]["dados"]["versoes"]
    de_camada = [q for q in quadros if q["evento"] == "camada"]
    assert de_camada, "nenhum evento de camada chegou em 40 s"
    quadro = de_camada[0]
    assert quadro["dados"]["camada"] == cid and quadro["dados"]["versao"] >= 1
    assert quadro["dados"]["operacao"] == "update"
    assert quadro["id"] and quadro["id"].isdigit(), quadro["id"]
    latencia = quadro["chegou_em"] - marca["em"]
    assert latencia <= 1.0, f"evento levou {latencia:.3f}s (cláusula do portão: <= 1 s)"
    medida(ITEM)("latencia_commit_ate_evento_s", round(latencia, 3), "s",
                 "do COMMIT do UPDATE na tabela da camada até o quadro SSE chegar ao consumidor "
                 "(um assinante, uma camada, gerador lido no mesmo processo)")


@pytest.mark.lento
def test_edicao_de_um_inquilino_nao_chega_ao_outro(ctx_b, camada_a, camada_b, env):
    """Teste cruzado do portão: B assina a camada DELE; a edição acontece na camada de A; B não pode ver
    nada. A rota já nega a camada alheia com 404 (teste acima); aqui a barreira medida é a do FLUXO."""
    cid_b = camada_b["camada_id"]
    _observar(env, camada_a)
    _observar(env, camada_b)
    linha = threading.Thread(target=lambda: _editar(env, camada_a, atraso_s=1.0), daemon=True)
    # espera 8 s (8x o teto de 1 s da cláusula de latência) sem nunca parar por evento: se algo vazasse,
    # apareceria muito antes disso
    quadros = _ler_fluxo(ctx_b, ctx_b.tenant_id, [cid_b], ao_pronto=linha.start, parar_em=99, maximo_s=8)
    linha.join(timeout=10)
    vazados = [q["dados"] for q in quadros if q["evento"] == "camada"]
    assert vazados == [], f"cliente de B recebeu evento de A: {vazados}"


@pytest.mark.lento
def test_reconexao_recupera_o_que_passou_por_last_event_id(ctx_a, camada_a, env):
    cid = camada_a["camada_id"]
    _observar(env, camada_a)
    antes = _contar_eventos(env, camada_a)
    _editar(env, camada_a)  # duas edições com NINGUÉM conectado: só o Last-Event-ID as recupera
    _editar(env, camada_a)
    assert _contar_eventos(env, camada_a) == antes + 2
    quadros = _ler_fluxo(ctx_a, ctx_a.tenant_id, [cid], ultimo_id=0, parar_em=antes + 2, maximo_s=25)
    recuperados = [(int(q["id"]), q["dados"]["versao"]) for q in quadros if q["evento"] == "camada"]
    assert len(recuperados) >= 2, recuperados
    assert [i for i, _ in recuperados] == sorted(i for i, _ in recuperados), "ids fora de ordem"
    assert [v for _, v in recuperados] == sorted(v for _, v in recuperados), "versões fora de ordem"


def test_last_event_id_invalido_e_tratado_como_ausente():
    """Refutação do item: `Last-Event-ID` inválido. O cabeçalho é lido na rota
    (`app/vivo/rotas.py::ultimo_id_do_cabecalho`); só dígito vale, e qualquer outra coisa vira "sem
    reenvio" em vez de erro. Sem isso, um cabeçalho forjado derrubaria a conexão com 500 (ou entraria
    como parâmetro numa consulta)."""
    from app.vivo.rotas import ultimo_id_do_cabecalho as ler

    assert ler("0") == 0 and ler("41") == 41
    for ruim in (None, "", " ", "-1", "1.5", "abc", "'; DROP TABLE --", "1 OR 1=1", "٣"):
        assert ler(ruim) is None, ruim


def test_edicao_em_lote_gera_um_evento_so(camada_a, env):
    """Coalescência na origem (refutação: 1.000 edições não podem virar 1.000 refetch). O gatilho é POR
    COMANDO: um UPDATE que toca N linhas emite UM evento. O navegador ainda agrupa por fonte com atraso de
    1 s (`web/js/vivo/assinatura.js`), mas a primeira redução acontece no banco."""
    _observar(env, camada_a)
    antes = _contar_eventos(env, camada_a)
    _editar(env, camada_a, linhas=50)
    depois = _contar_eventos(env, camada_a)
    assert depois - antes == 1, f"50 linhas num comando geraram {depois - antes} eventos"


# ---------------------------------------------------------------- limites e interruptor

def test_limite_de_conexoes_por_inquilino_e_por_usuario():
    """O mecanismo que o portão manda declarar (`VIVO_SSE_POR_INQUILINO`/`VIVO_SSE_POR_USUARIO`). Testado
    direto na função que a rota chama antes de abrir o fluxo — abrir 1.000 conexões HTTP de verdade a
    partir de um processo síncrono não é possível com o TestClient (achado registrado em
    tests/api/jobs/test_jobs_sse.py), e o que decide o 429 é esta contagem.

    O usuário 1 enche a cota DELE (10) e a conexão 11 é 429; usuários diferentes somam até a cota do
    inquilino (100) e a conexão 101 é 429 — os dois tetos são independentes."""
    tenant = 999999998
    for u in range(1, 100):
        mod._por_usuario.pop((tenant, u), None)
    mod._por_inquilino.pop(tenant, None)
    try:
        for _ in range(limites.VIVO_SSE_POR_USUARIO):
            mod.reservar(tenant, 1)
        with pytest.raises(mod.ErroAPI) as exc:
            mod.reservar(tenant, 1)
        assert exc.value.status_code == 429 and exc.value.erro == "sse_limite_usuario"
        assert mod._por_usuario[(tenant, 1)] == limites.VIVO_SSE_POR_USUARIO, "reserva recusada não incrementou"

        usuario = 2
        while mod._por_inquilino[tenant] < limites.VIVO_SSE_POR_INQUILINO:
            mod.reservar(tenant, usuario)
            if mod._por_usuario[(tenant, usuario)] >= limites.VIVO_SSE_POR_USUARIO:
                usuario += 1
        with pytest.raises(mod.ErroAPI) as exc:
            mod.reservar(tenant, usuario + 1)
        assert exc.value.status_code == 429 and exc.value.erro == "sse_limite_inquilino"

        mod._liberar(tenant, 1)
        assert mod._por_inquilino[tenant] == limites.VIVO_SSE_POR_INQUILINO - 1
        mod.reservar(tenant, 1)  # a vaga liberada volta a caber
    finally:
        mod._por_inquilino.pop(tenant, None)
        for u in range(1, 200):
            mod._por_usuario.pop((tenant, u), None)


def test_com_sse_desligado_a_rota_responde_503(sessao_a, camada_a, monkeypatch):
    """Fallback por intervalo: desligado o fluxo, a rota diz 503 `sse_desligado` e o navegador cai no
    intervalo de atualização de cada fonte (`web/js/paineis/render.js`), sem tela quebrada."""
    import dataclasses

    from app import settings as mod_settings

    # `settings` é um dataclass congelado (app/settings.py): troca-se o OBJETO no módulo, não o campo — a
    # rota lê `app.settings.settings` a cada chamada exatamente para que este interruptor seja testável.
    monkeypatch.setattr(mod_settings, "settings",
                        dataclasses.replace(mod_settings.settings, PLAT_SSE_LIGADO=False))
    r = sessao_a.get(f"/api/eventos/camadas?camadas={camada_a['camada_id']}")
    assert r.status_code == 503 and r.json()["erro"] == "sse_desligado", r.text
