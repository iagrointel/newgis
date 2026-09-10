"""Portão literal do item L7-33-modo-somente-leitura: ligar o modo bloqueia escrita com mensagem, mapa e
exportação continuam, a faixa fica visível pelo GET /api/modo; desligar devolve tudo; job em execução no
momento de ligar termina sem se perder (prova.progresso, 120 s) e o pendente comum fica pausado até
desligar; `plat modo` com motivo obrigatório grava a trilha; refutação = varrer TODAS as rotas de escrita
do OpenAPI tentando escrever durante o modo (um 2xx é reprovação).

Usa `plat_worker` (via `scripts/plat`, PLAT_DSN_WORKER da trilha) para ligar/desligar — a API nunca liga o
próprio modo. Cada teste desliga o modo no `finally`, mesmo em falha, para não vazar estado para o resto
da suíte."""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from tests import jobs_sessao
from tests.api.jobs.conftest import criar_job, esperar

pytestmark = pytest.mark.lento

RAIZ = Path(__file__).resolve().parents[3]
PLAT = RAIZ / "scripts" / "plat"


@pytest.fixture
def conexao_plat_worker(env):
    """Conexão como plat_worker (a única role com EXECUTE em modo_ligar/modo_desligar, migração
    20260906T2109): fixture local ao item — não existe no conftest partilhado da fila e criar uma aqui
    evita mexer em arquivo que outras trilhas também tocam. autocommit=False, como jobs_sessao.conectar:
    o teste chama rollback() explicitamente entre as chamadas que devem falhar."""
    dsn = env.get("PLAT_DSN_WORKER") or os.environ.get("PLAT_DSN_WORKER")
    if not dsn:
        pytest.skip("sem PLAT_DSN_WORKER no ambiente (rode a suíte com a role do worker exportada)")
    con = jobs_sessao.conectar(dsn)
    try:
        yield con
    finally:
        con.rollback()
        con.close()


def _plat(*args: str) -> dict:
    r = subprocess.run([str(PLAT), *args], cwd=RAIZ, env=os.environ.copy(),
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"plat {' '.join(args)} falhou: {r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def _ligar(motivo: str, inquilino: str | None = None, retry_after: int = 2) -> dict:
    args = ["modo", "ligar", "--motivo", motivo, "--retry-after", str(retry_after)]
    if inquilino:
        args += ["--inquilino", inquilino]
    return _plat(*args)


def _desligar(motivo: str, inquilino: str | None = None) -> dict:
    args = ["modo", "desligar", "--motivo", motivo]
    if inquilino:
        args += ["--inquilino", inquilino]
    return _plat(*args)


@pytest.fixture
def modo_global():
    """Liga o modo GLOBAL para o teste e garante desligar no fim, mesmo em falha."""
    ligado = False

    def _lig(motivo="teste automatizado L7-33", retry_after=2):
        nonlocal ligado
        m = _ligar(motivo, retry_after=retry_after)
        ligado = True
        return m

    yield _lig
    if ligado:
        _desligar("fim do teste automatizado L7-33")


@pytest.fixture
def modo_inquilino():
    """Liga o modo por INQUILINO (slug) para o teste; desliga no fim."""
    ligados = []

    def _lig(slug: str, motivo="teste automatizado L7-33 por inquilino", retry_after=2):
        m = _ligar(motivo, inquilino=slug, retry_after=retry_after)
        ligados.append(slug)
        return m

    yield _lig
    for slug in ligados:
        _desligar("fim do teste automatizado L7-33", inquilino=slug)


def test_cli_motivo_obrigatorio_e_grava_trilha(conexao_plat_worker):
    """`plat modo ligar/desligar` sem --motivo recusa (argparse não deixa nem chamar o SQL); com motivo,
    grava plat.sistema_trilha (append-only, uma linha por ação) — a SQL também recusa motivo vazio E
    motivo só de espaço (não é só a casca argparse), provado chamando a função direto. Cada chamada que
    deve falhar vai em cursor+rollback próprios: Postgres aborta a transação inteira no erro, então
    encadear duas chamadas que devem levantar exceção na MESMA transação faria a segunda falhar por
    'current transaction is aborted', mascarando a mensagem real."""
    r = subprocess.run([str(PLAT), "modo", "ligar"], cwd=RAIZ, env=os.environ.copy(),
                       capture_output=True, text=True, timeout=10)
    assert r.returncode != 0 and "motivo" in (r.stderr + r.stdout).lower()

    with conexao_plat_worker.cursor() as cur:
        with pytest.raises(Exception, match="motivo"):
            cur.execute("SELECT plat.modo_ligar('global', NULL, '   ', 'teste')")
    conexao_plat_worker.rollback()

    with conexao_plat_worker.cursor() as cur:
        with pytest.raises(Exception, match="motivo"):
            cur.execute("SELECT plat.modo_ligar('global', NULL, %s, 'teste')", ("",))
    conexao_plat_worker.rollback()

    antes = _contar_trilha(conexao_plat_worker, "modo_manutencao")
    try:
        m = _ligar("prova de trilha L7-33")
        assert m["ativo"] is True and m["motivo"] == "prova de trilha L7-33"
        depois_ligar = _contar_trilha(conexao_plat_worker, "modo_manutencao")
        assert depois_ligar == antes + 1
        m2 = _desligar("prova de trilha L7-33 (fim)")
        assert m2["ativo"] is False
        depois_desligar = _contar_trilha(conexao_plat_worker, "modo_manutencao")
        assert depois_desligar == antes + 2
    finally:
        pass


def _contar_trilha(con, chave: str) -> int:
    with con.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.sistema_trilha WHERE chave = %s", (chave,))
        n = cur.fetchone()["n"]
    con.rollback()
    return n


def test_escrita_bloqueada_leitura_mapa_e_exportacao_continuam(cliente_demo, worker_vivo, modo_global):
    """Ligado o modo: POST comum devolve 503 + Retry-After + Problem Details; GET (mapa/catálogo) segue 200;
    a exportação (`catalogo.exportar_lista`, tipo somente_leitura) é aceita, roda e conclui MESMO com o
    modo ligado — é a travessia declarada na hipótese do item."""
    modo_global(retry_after=7)

    antes = cliente_demo.get("/api/categorias")
    assert antes.status_code == 200

    r = cliente_demo.post("/api/grupos", json={"nome": "grupo bloqueado pelo modo L7-33"})
    assert r.status_code == 503, r.text
    assert r.headers.get("retry-after") == "7"
    corpo = r.json()
    assert corpo["erro"] == "modo_manutencao"
    assert corpo["detalhe"]["escopo"] == "global"
    assert "motivo" in corpo["detalhe"] and corpo["detalhe"]["motivo"]

    depois = cliente_demo.get("/api/categorias")
    assert depois.status_code == 200

    job = criar_job(cliente_demo, "catalogo.exportar_lista", {"formato": "csv"})
    assert job["somente_leitura"] is True
    concluido = esperar(cliente_demo, job["id"], timeout=30)
    assert concluido["estado"] == "concluido", concluido


def test_modo_por_inquilino_nao_afeta_outro(cliente_demo, cliente_demo2, modo_inquilino):
    """Modo ligado só para `demo`: escrita em `demo` bloqueia, escrita em `demo2` continua liberada."""
    modo_inquilino("demo")
    r_demo = cliente_demo.post("/api/grupos", json={"nome": "bloqueado no inquilino certo"})
    assert r_demo.status_code == 503, r_demo.text
    assert r_demo.json()["detalhe"]["escopo"] == "inquilino"

    r_demo2 = cliente_demo2.post("/api/grupos", json={"nome": "grupo do outro inquilino L7-33"})
    assert r_demo2.status_code in (200, 201), r_demo2.text
    if r_demo2.status_code == 201:
        gid = r_demo2.json().get("id")
        if gid:
            cliente_demo2.delete(f"/api/grupos/{gid}")


def test_api_modo_e_isentos_sempre_respondem(cliente_demo, cliente, modo_global):
    """`/api/modo`, `/saude`, `/api/versao` (o par real de monitoramento — `/status` da hipótese não
    existe neste código, ver app/modo.py) e login/logout nunca bloqueiam, mesmo com o modo ligado.
    O login/logout de prova usa `cliente` (sem cookie, session-scoped mas SEM sessão própria), nunca
    `cliente_demo`: esse é compartilhado por toda a suíte e um logout nele invalidaria a sessão para
    todo teste que rodar depois (achado ao rodar a suíte inteira, não só este arquivo)."""
    modo_global()
    assert cliente_demo.get("/api/modo").status_code == 200
    assert cliente_demo.get("/api/modo").json()["ativo"] is True
    assert cliente_demo.get("/saude").status_code in (200, 503)  # 503 só se banco cair, não pelo modo
    assert cliente_demo.get("/api/versao").status_code == 200
    r = cliente.post("/api/login", json={"inquilino": "demo", "login": "x", "senha": "x"})
    assert r.status_code != 503  # 401 é aceitável (credencial errada); nunca bloqueado pelo modo
    assert cliente.post("/api/logout").status_code != 503


def test_job_rodando_termina_pendente_pausa_e_retoma(cliente_demo, worker_vivo, conexao_plat_app, modo_inquilino,
                                                      medida):
    """Job de 2 min (prova.progresso) e um segundo job (curto) são criados ANTES do modo — criar um job
    comum DEPOIS de ligado o modo é escrita e o próprio POST /api/jobs já devolve 503 (provado à parte em
    test_escrita_bloqueada_leitura_mapa_e_exportacao_continuam e no varrimento do adversário); o portão
    deste item ('job em execução no momento de ligar termina ou pausa sem se perder') é sobre um job que
    JÁ estava na fila quando o modo liga, não sobre criar um novo durante o modo.

    O worker desta trilha sobe com um processo só (log 'processos=1'), então o job curto fica pendente
    atrás do longo mesmo sem modo nenhum — o modo então liga DEPOIS dos dois criados. Quando o job longo
    termina e o worker fica livre, plat.job_pegar ainda teria uma vaga para o curto, mas a cláusula do
    modo (não somente_leitura) o mantém pendente; só ao desligar ele é pego e conclui."""
    t0 = time.monotonic()
    rodando = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 120, "passos": 12})
    esperar(cliente_demo, rodando["id"], estados=("rodando",), timeout=20,
            condicao=lambda j: j["estado"] in ("rodando", "concluido"))

    pendente = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 5, "passos": 1,
                                                            "chave": "l7-33-pendente-sob-modo"})
    assert pendente["estado"] == "pendente", pendente  # atrás do longo, o único processo do worker está ocupado

    modo_inquilino("demo", retry_after=3)

    time.sleep(3)
    ainda = cliente_demo.get(f"/api/jobs/{pendente['id']}").json()
    assert ainda["estado"] == "pendente", f"job pendente não deveria sair da fila sob modo: {ainda}"

    concluido_rodando = esperar(cliente_demo, rodando["id"], timeout=150)
    tempo_rodando_s = round(time.monotonic() - t0, 1)
    assert concluido_rodando["estado"] == "concluido", concluido_rodando

    time.sleep(2)  # o worker fica livre aqui; sem a cláusula do modo ele pegaria o pendente agora mesmo
    ainda2 = cliente_demo.get(f"/api/jobs/{pendente['id']}").json()
    assert ainda2["estado"] == "pendente", "continuou pausado durante o modo mesmo após o outro job terminar"

    _desligar("teste automatizado L7-33 retomada", inquilino="demo")
    retomado = esperar(cliente_demo, pendente["id"], timeout=30)
    assert retomado["estado"] == "concluido", retomado

    gravar = medida("L7-33-modo-somente-leitura")
    gravar("job_2min_terminou_sob_modo_s", tempo_rodando_s, "s",
           "prova.progresso(120s) iniciado antes do modo, concluído com o modo ligado no meio da execução")


def test_adversario_openapi_todas_as_rotas_de_escrita_bloqueadas(cliente_demo, modo_global):
    """Refutação do item: varre docs/openapi.json (nunca lista à mão) por toda rota POST/PUT/PATCH/DELETE e
    tenta cada uma com o modo ligado. Um único 2xx reprova o item. Caminhos {param} recebem um valor
    qualquer — o middleware decide pelo verbo HTTP e o caminho concreto, antes de qualquer resolução de rota, então
    o recurso não precisar existir não enfraquece a prova."""
    modo_global(retry_after=1)
    openapi = json.loads((RAIZ / "docs" / "openapi.json").read_text(encoding="utf-8"))
    isentos = {"/api/login", "/api/login/2fa", "/api/login/ldap", "/api/logout", "/api/modo"}
    verbos = {"post", "put", "patch", "delete"}
    testadas, bloqueadas, permitidas_por_isencao = 0, 0, []
    for caminho, metodos in openapi["paths"].items():
        if caminho in isentos:
            continue
        alvo = caminho
        for nome_param in ("id", "slug", "tenant_id", "job_id", "path"):
            alvo = alvo.replace(f"{{{nome_param}}}", "1")
        import re

        alvo = re.sub(r"\{[^}]+\}", "1", alvo)
        for metodo, _spec in metodos.items():
            if metodo not in verbos:
                continue
            testadas += 1
            corpo = {} if metodo != "delete" else None
            resp = cliente_demo.request(metodo.upper(), alvo, json=corpo)
            if resp.status_code == 503:
                bloqueadas += 1
            elif 200 <= resp.status_code < 300:
                if caminho == "/api/jobs" and metodo == "post":
                    permitidas_por_isencao.append((metodo, caminho, resp.status_code))
                    continue
                pytest.fail(f"{metodo.upper()} {caminho} devolveu {resp.status_code} com o modo ligado "
                           f"(deveria ser 503): {resp.text[:300]}")
    assert testadas >= 20, f"só {testadas} rotas de escrita achadas no openapi.json — varredura suspeita"
    assert bloqueadas >= testadas - len(permitidas_por_isencao) - 5, (
        f"{testadas - bloqueadas} rotas de escrita não devolveram 503 nem 2xx explicado; "
        f"investigar antes de aprovar")
