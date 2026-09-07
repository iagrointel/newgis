"""Item L0-14-cli-admin: a linha de comando `plat` faz por script o que o console faz pela tela.

Cada teste roda o executável de verdade (`scripts/plat`, em subprocesso, contra um uvicorn próprio) e
compara o EFEITO com o da rota equivalente chamada pelo cliente HTTP da suíte: mesmo resultado e mesmo
evento gravado. Também prova as regras de segurança do item: senha nunca por argumento, arquivo de
credencial frouxo recusado e falha sem vazamento quando quem executa não tem acesso ao ambiente.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import time
from pathlib import Path

import pytest

from tests.api.conftest import CREDENCIAIS, CREDENCIAIS_TOTP, PREFIXO_TESTE

RAIZ = Path(__file__).resolve().parents[2]
PLAT = RAIZ / "scripts" / "plat"
PORTA_PREFERIDA = int(os.environ.get("PLAT_CLI_PORTA_TESTE", "8358"))


def _porta_livre(inicio: int) -> int:
    for porta in range(inicio, inicio + 40):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", porta)) != 0:
                return porta
    pytest.skip(f"nenhuma porta livre a partir de {inicio}")
    raise AssertionError


@pytest.fixture(scope="module")
def api(env):
    """Sobe um uvicorn desta árvore só para a CLI falar por HTTP de verdade (a CLI não usa ASGI em memória)."""
    porta = _porta_livre(PORTA_PREFERIDA)
    processo = subprocess.Popen(
        [str(RAIZ / "venv" / "bin" / "python"), "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(porta), "--no-access-log"],
        cwd=RAIZ, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**os.environ, **{k: v for k, v in env.items() if v is not None}},
    )
    base = f"http://127.0.0.1:{porta}"
    try:
        import urllib.error
        import urllib.request

        fim = time.monotonic() + 60
        while time.monotonic() < fim:
            if processo.poll() is not None:
                pytest.fail(f"uvicorn de teste morreu com código {processo.returncode}")
            try:
                with urllib.request.urlopen(base + "/saude", timeout=2) as r:
                    if r.status == 200:
                        break
            except (urllib.error.URLError, OSError):
                time.sleep(0.5)
        else:
            pytest.fail(f"o uvicorn de teste não respondeu em {base}/saude em 60 s")
        yield base
    finally:
        processo.terminate()
        try:
            processo.wait(timeout=15)
        except subprocess.TimeoutExpired:
            processo.kill()


def _ambiente(api: str) -> dict[str, str]:
    return {
        **os.environ,
        "PLAT_CLI_URL": api,
        "PLAT_CREDENCIAIS_ARQUIVO": str(CREDENCIAIS),
        "PLAT_CREDENCIAIS_TOTP_ARQUIVO": str(CREDENCIAIS_TOTP),
    }


def plat(api: str, *args: str, entrada: str | None = None, espera_codigo: int = 0) -> dict | list | str:
    """Roda `scripts/plat --json ...` e devolve a saída decodificada (ou o texto, quando não é JSON)."""
    r = subprocess.run([str(PLAT), *args], capture_output=True, text=True, input=entrada,
                       env=_ambiente(api), cwd=RAIZ, timeout=300)
    assert r.returncode == espera_codigo, f"plat {' '.join(args)} -> {r.returncode}\n{r.stdout}\n{r.stderr}"
    if "--json" in args and r.stdout.strip():
        return json.loads(r.stdout)
    return r.stdout


def plat_bruto(api: str, *args: str, entrada: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([str(PLAT), *args], capture_output=True, text=True, input=entrada,
                          env=_ambiente(api), cwd=RAIZ, timeout=300)


def eventos_de(sessao, tipo: str, limite: int = 50) -> list[dict]:
    r = sessao.get(f"/api/eventos?tipo={tipo}&limite={limite}")
    assert r.status_code == 200, r.text
    return r.json()["itens"]


@pytest.fixture(scope="module")
def superadmin_pronto(sessao_plat):
    """Garante o segundo fator ligado e o segredo no arquivo antes de a CLI tentar entrar como superadmin."""
    return sessao_plat


# ---------------------------------------------------------------- inquilino
def test_inquilino_criar_pela_cli_tem_o_mesmo_efeito_da_rota(api, sessao_plat, superadmin_pronto, tmp_path):
    """Cria um inquilino pela CLI e outro pela rota; os dois nascem iguais e gravam o mesmo evento."""
    arquivo_senha = tmp_path / "senha.txt"
    arquivo_senha.write_text("Senha-de-teste-7ab\n", encoding="utf-8")
    arquivo_senha.chmod(0o600)
    slug_cli = f"{PREFIXO_TESTE}-inq-{secrets.token_hex(3)}"
    slug_rota = f"{PREFIXO_TESTE}-inq-{secrets.token_hex(3)}"
    try:
        pela_cli = plat(api, "--json", "--configurar-2fa", "inquilino", "criar", "--slug", slug_cli,
                        "--nome", "Inquilino pela linha de comando", "--admin-login", "admin",
                        "--admin-nome", "Administrador", "--senha-arquivo", str(arquivo_senha))
        r = sessao_plat.post("/api/plataforma/inquilinos", json={
            "slug": slug_rota, "nome": "Inquilino pela rota", "admin_login": "admin",
            "admin_nome": "Administrador", "config": {}})
        assert r.status_code == 201, r.text
        pela_rota = r.json()

        assert pela_cli["criado"] is True and pela_cli["slug"] == slug_cli
        assert pela_cli["admin"]["login"] == pela_rota["admin"]["login"] == "admin"
        assert "senha_temporaria" not in pela_cli, "com --senha-arquivo a senha definitiva já foi aplicada"

        lista = {t["slug"]: t for t in sessao_plat.get("/api/plataforma/inquilinos").json()}
        assert set(lista[slug_cli]) == set(lista[slug_rota]), "o registro do inquilino tem o mesmo formato"
        assert lista[slug_cli]["ativo"] is lista[slug_rota]["ativo"] is True

        tipos = {(e["alvo_tipo"], e["tipo"]) for e in eventos_de(sessao_plat, "inquilinos/criar")}
        assert ("inquilino", "inquilinos/criar") in tipos
        propriedades = {e["propriedades"]["slug"] for e in eventos_de(sessao_plat, "inquilinos/criar")}
        assert {slug_cli, slug_rota} <= propriedades, "a CLI grava o mesmo evento que a rota"

        # a senha definitiva escrita pela CLI é a que o admin usa (login de verdade, pela API)
        entrada = sessao_plat.post  # marcador de leitura; o login vai por cliente novo abaixo
        assert entrada is not None
        from tests.api.conftest import entrar, novo_cliente

        c = novo_cliente()
        r = entrar(c, slug_cli, "admin", "Senha-de-teste-7ab")
        assert r.status_code == 200 and r.json()["ok"] is True, r.text
    finally:
        for slug in (slug_cli, slug_rota):
            for t in sessao_plat.get("/api/plataforma/inquilinos").json():
                if t["slug"] == slug:
                    sessao_plat.delete(f"/api/plataforma/inquilinos/{t['id']}")


def test_inquilino_criar_se_nao_existir_e_idempotente(api, sessao_plat, superadmin_pronto):
    """É o que o install.sh precisa: rodar de novo não falha nem cria nada."""
    saida = plat(api, "--json", "--configurar-2fa", "inquilino", "criar", "--slug", "demo",
                 "--nome", "Inquilino de demonstração", "--admin-login", "admin",
                 "--admin-nome", "Administrador", "--se-nao-existir")
    assert saida["criado"] is False and saida["slug"] == "demo"
    antes = len(sessao_plat.get("/api/plataforma/inquilinos").json())
    plat(api, "--json", "--configurar-2fa", "inquilino", "criar", "--slug", "demo", "--nome", "x",
         "--admin-login", "admin", "--admin-nome", "y", "--se-nao-existir")
    assert len(sessao_plat.get("/api/plataforma/inquilinos").json()) == antes


def test_inquilino_cota_pela_cli_e_pela_rota_leem_o_mesmo(api, sessao_a):
    pela_cli = plat(api, "--json", "--inquilino", "demo", "inquilino", "cota")
    pela_rota = sessao_a.get("/api/org").json()
    assert pela_cli["armazenamento"]["cota_bytes"] == pela_rota["armazenamento"]["cota_bytes"]
    assert pela_cli["usuarios"]["cota"] == pela_rota["usuarios"]["cota"]

    original = pela_rota["usuarios"]["cota"]
    try:
        depois = plat(api, "--json", "--inquilino", "demo", "inquilino", "cota", "--usuarios", str(original - 1))
        assert depois["usuarios"]["cota"] == original - 1
        assert sessao_a.get("/api/org").json()["usuarios"]["cota"] == original - 1
        assert any(e["tipo"] == "org/configurar" for e in eventos_de(sessao_a, "org/configurar"))
    finally:
        plat(api, "--json", "--inquilino", "demo", "inquilino", "cota", "--usuarios", str(original))


def test_inquilino_suspender_e_reativar_gravam_os_eventos_da_rota(api, sessao_plat, superadmin_pronto):
    slug = f"{PREFIXO_TESTE}-inq-{secrets.token_hex(3)}"
    r = sessao_plat.post("/api/plataforma/inquilinos", json={
        "slug": slug, "nome": "Inquilino a suspender", "admin_login": "admin", "admin_nome": "A", "config": {}})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    try:
        plat(api, "--configurar-2fa", "inquilino", "suspender", slug)
        assert next(t for t in sessao_plat.get("/api/plataforma/inquilinos").json() if t["id"] == tid)["ativo"] is False
        plat(api, "--configurar-2fa", "inquilino", "reativar", slug)
        assert next(t for t in sessao_plat.get("/api/plataforma/inquilinos").json() if t["id"] == tid)["ativo"] is True
        for tipo in ("inquilinos/suspender", "inquilinos/reativar"):
            assert any(e["alvo_id"] == str(tid) or str(e["alvo_id"]) == str(tid)
                       for e in eventos_de(sessao_plat, tipo)), f"sem evento {tipo}"
    finally:
        sessao_plat.delete(f"/api/plataforma/inquilinos/{tid}")


# ---------------------------------------------------------------- usuário
def test_usuario_criar_redefinir_desabilitar_como_a_rota(api, sessao_a, usuarios_a):
    login_cli = f"{PREFIXO_TESTE}{secrets.token_hex(4)}"
    criado_cli = plat(api, "--json", "--inquilino", "demo", "usuario", "criar",
                      "--login", login_cli, "--nome", "Usuário pela CLI", "--perfil", "editor")
    criado_rota, _ = usuarios_a.criar(perfil="editor")
    try:
        assert set(criado_cli["usuario"]) == set(criado_rota)
        assert criado_cli["usuario"]["perfil"] == criado_rota["perfil"] == "editor"
        assert criado_cli["senha_temporaria"], "sem --senha-arquivo a CLI devolve a senha temporária"

        redefinida = plat(api, "--json", "--inquilino", "demo", "usuario", "redefinir-senha", login_cli)
        assert redefinida["senha_temporaria"] != criado_cli["senha_temporaria"]

        plat(api, "--inquilino", "demo", "usuario", "desabilitar", login_cli)
        assert sessao_a.get(f"/api/usuarios/{criado_cli['usuario']['id']}").json()["ativo"] is False
        plat(api, "--inquilino", "demo", "usuario", "reabilitar", login_cli)
        assert sessao_a.get(f"/api/usuarios/{criado_cli['usuario']['id']}").json()["ativo"] is True

        criados = {e["alvo_id"] for e in eventos_de(sessao_a, "usuarios/criar", 200)}
        assert str(criado_cli["usuario"]["id"]) in {str(x) for x in criados}
        assert str(criado_rota["id"]) in {str(x) for x in criados}
        assert any(str(e["alvo_id"]) == str(criado_cli["usuario"]["id"])
                   for e in eventos_de(sessao_a, "usuarios/redefinir_senha", 200))
    finally:
        sessao_a.delete(f"/api/usuarios/{criado_cli['usuario']['id']}")


def test_usuario_listar_devolve_a_mesma_pagina_da_rota(api, sessao_a):
    pela_cli = plat(api, "--json", "--inquilino", "demo", "usuario", "listar", "--limite", "5")
    pela_rota = sessao_a.get("/api/usuarios?limite=5").json()
    assert pela_cli["total"] == pela_rota["total"]
    assert [u["id"] for u in pela_cli["itens"]] == [u["id"] for u in pela_rota["itens"]]


# ---------------------------------------------------------------- token
def test_token_criar_e_revogar_como_a_rota(api, sessao_a):
    criado = plat(api, "--json", "--inquilino", "demo", "token", "criar",
                  "--nome", f"{PREFIXO_TESTE}-cli", "--escopo", "catalogo:ler")
    try:
        assert criado["token"].startswith("plat_") and criado["prefixo"] in criado["token"]
        lista = sessao_a.get("/api/tokens?todos=1").json()
        assert criado["id"] in [t["id"] for t in lista]
        assert any(str(e["alvo_id"]) == str(criado["id"]) for e in eventos_de(sessao_a, "tokens/criar", 200))
    finally:
        plat(api, "--inquilino", "demo", "token", "revogar", str(criado["id"]))
    revogado = [t for t in sessao_a.get("/api/tokens?todos=1").json() if t["id"] == criado["id"]]
    assert revogado and revogado[0]["revogado_em"] is not None
    assert any(str(e["alvo_id"]) == str(criado["id"]) for e in eventos_de(sessao_a, "tokens/revogar", 200))


# ---------------------------------------------------------------- camada, job, evento
def test_camada_importar_cria_a_mesma_importacao_que_a_tela(api, sessao_a, tmp_path):
    """Sem esperar o worker: o que se compara é o par (importação criada, job de inspeção enfileirado) e o
    evento `importacoes/criar` — os mesmos que a tela produz nos três primeiros passos."""
    arquivo = tmp_path / "pontos.geojson"
    arquivo.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"nome": "a"}, "geometry": {"type": "Point", "coordinates": [-47.9, -15.8]}},
    ]}), encoding="utf-8")
    saida = plat(api, "--json", "--inquilino", "demo", "camada", "importar", str(arquivo),
                 "--formato", "geojson", "--crs", "4326", "--sem-esperar")
    importacao = sessao_a.get(f"/api/importacoes/{saida['importacao_id']}").json()
    assert importacao["formato"] == "geojson"
    assert sessao_a.get(f"/api/jobs/{saida['job_inspecao']}").json()["tipo"] == "ingestao.inspecionar"
    assert any(e["propriedades"].get("importacao_id") == saida["importacao_id"]
               for e in eventos_de(sessao_a, "importacoes/criar", 200))
    sessao_a.delete(f"/api/importacoes/{saida['importacao_id']}")
    sessao_a.delete(f"/api/itens/{saida['arquivo_id']}")


def test_job_listar_cancelar_e_repetir_como_a_rota(api, sessao_a, tmp_path):
    """O job vem do próprio fluxo de importação (nenhum tipo de mentira criado para o teste)."""
    arquivo = tmp_path / "job.geojson"
    arquivo.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    saida = plat(api, "--json", "--inquilino", "demo", "camada", "importar", str(arquivo),
                 "--formato", "geojson", "--sem-esperar")
    job_id = saida["job_inspecao"]
    try:
        listados = plat(api, "--json", "--inquilino", "demo", "job", "listar", "--limite", "50")
        pela_rota = sessao_a.get("/api/jobs?limite=50").json()
        assert listados["total"] == pela_rota["total"]
        assert job_id in [j["id"] for j in listados["itens"]]

        cancelado = plat(api, "--json", "--inquilino", "demo", "job", "cancelar", job_id)
        assert cancelado["estado"] in ("cancelado", "cancelando")
        assert sessao_a.get(f"/api/jobs/{job_id}").json()["estado"] in ("cancelado", "cancelando")

        repetido = plat(api, "--json", "--inquilino", "demo", "job", "repetir", job_id)
        assert repetido["id"] != job_id and repetido["tipo"] == cancelado["tipo"]
        assert sessao_a.get(f"/api/jobs/{repetido['id']}").status_code == 200
        assert any(e["propriedades"].get("de") == job_id for e in eventos_de(sessao_a, "jobs/criar", 200))
        sessao_a.post(f"/api/jobs/{repetido['id']}/cancelar", json={})
    finally:
        sessao_a.delete(f"/api/importacoes/{saida['importacao_id']}")
        sessao_a.delete(f"/api/itens/{saida['arquivo_id']}")


def test_evento_exportar_bate_com_a_rota(api, sessao_a, tmp_path):
    destino = tmp_path / "eventos.csv"
    saida = plat(api, "--json", "--inquilino", "demo", "evento", "exportar",
                 "--formato", "csv", "--maximo", "20", "--saida", str(destino))
    linhas = destino.read_text(encoding="utf-8").strip().splitlines()
    assert linhas[0].startswith("id,em,tipo,ator_id,ator_login")
    assert len(linhas) - 1 == saida["exportados"] <= 20
    assert saida["total"] == sessao_a.get("/api/eventos?limite=1").json()["total"]

    em_json = plat(api, "--json", "--inquilino", "demo", "evento", "exportar", "--maximo", "5")
    assert len(em_json["itens"]) if isinstance(em_json, dict) else len(em_json) <= 5


# ---------------------------------------------------------------- segurança
def test_senha_em_argumento_e_recusada(api, tmp_path):
    r = plat_bruto(api, "--inquilino", "demo", "usuario", "criar", "--login", "ztx", "--nome", "X",
                   "--senha", "senha-em-argumento")
    assert r.returncode == 2, r.stdout
    assert "não existe de propósito" in r.stderr and "--senha-arquivo" in r.stderr
    assert "senha-em-argumento" not in r.stdout


def test_arquivo_de_senha_frouxo_e_recusado(api, tmp_path):
    frouxo = tmp_path / "senha_frouxa.txt"
    frouxo.write_text("Senha-de-teste-7ab\n", encoding="utf-8")
    frouxo.chmod(0o644)
    r = plat_bruto(api, "--configurar-2fa", "inquilino", "criar", "--slug", f"{PREFIXO_TESTE}-nao-vai",
                   "--nome", "X", "--admin-login", "admin", "--admin-nome", "A",
                   "--senha-arquivo", str(frouxo))
    assert r.returncode == 2
    assert "chmod 600" in r.stderr
    assert "Senha-de-teste-7ab" not in r.stderr + r.stdout


def test_sem_acesso_as_credenciais_falha_sem_vazar(api, tmp_path, env):
    """O adversário roda a CLI como quem não tem o .env nem o arquivo de credenciais."""
    limpo = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path),
             "PLAT_CLI_URL": api, "PLAT_CREDENCIAIS_ARQUIVO": str(tmp_path / "nao_existe.txt")}
    r = subprocess.run([str(PLAT), "--inquilino", "demo", "usuario", "listar"],
                       capture_output=True, text=True, env=limpo, cwd=RAIZ, timeout=120)
    assert r.returncode == 2
    assert "não existe" in r.stderr
    assert "Traceback" not in r.stderr, "erro previsto não pode sair com rastro de pilha"
    saida = r.stdout + r.stderr
    for segredo in (env.get("PLAT_SECRET"), env.get("PLAT_DSN"), env.get("PLAT_DSN_WORKER")):
        if segredo:
            assert segredo not in saida
            assert segredo.split("@")[0].split(":")[-1] not in saida, "nem a senha da role pode aparecer"


def test_camada_para_inquilino_inexistente_falha_limpo(api, tmp_path):
    arquivo = tmp_path / "x.geojson"
    arquivo.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    r = plat_bruto(api, "--inquilino", f"{PREFIXO_TESTE}-nao-existe", "camada", "importar", str(arquivo),
                   "--formato", "geojson", "--sem-esperar")
    assert r.returncode == 2
    assert "não tem a linha do inquilino" in r.stderr
    assert "Traceback" not in r.stderr


# ---------------------------------------------------------------- ajuda e documentação
def _todos_os_parsers():
    import argparse

    from app.cli.principal import montar_parser

    raiz = montar_parser()
    pilha, saida = [("plat", raiz)], []
    while pilha:
        nome, p = pilha.pop()
        saida.append((nome, p))
        for acao in p._actions:  # noqa: SLF001
            if isinstance(acao, argparse._SubParsersAction):  # noqa: SLF001
                pilha.extend((f"{nome} {n}", sp) for n, sp in acao.choices.items())
    return saida


INGLES_PROIBIDO = ("usage:", "positional arguments", "options:", "optional arguments",
                   "show this help message", "default:", "error:")


def test_ajuda_de_todo_comando_esta_em_portugues():
    for nome, parser in _todos_os_parsers():
        texto = parser.format_help().lower()
        for palavra in INGLES_PROIBIDO:
            assert palavra not in texto, f"`{nome} --help` ainda tem texto em inglês: {palavra!r}"
        assert "uso:" in texto


def test_ajuda_pela_linha_de_comando_de_verdade(api):
    r = plat_bruto(api, "--help")
    assert r.returncode == 0
    assert "uso: plat" in r.stdout and "opções:" in r.stdout
    for palavra in INGLES_PROIBIDO:
        assert palavra not in r.stdout.lower()


def test_docs_cli_esta_gerado_do_argparse():
    from app.cli.documentacao import gerar
    from app.cli.principal import montar_parser

    esperado = gerar(montar_parser())
    atual = (RAIZ / "docs" / "CLI.md").read_text(encoding="utf-8")
    assert atual == esperado, "docs/CLI.md está velho; rode `scripts/plat docs` e comite o resultado"


def test_todo_subcomando_esta_no_docs():
    atual = (RAIZ / "docs" / "CLI.md").read_text(encoding="utf-8")
    for nome, _ in _todos_os_parsers():
        assert f"`{nome}`" in atual, f"{nome} não aparece em docs/CLI.md"


def test_install_usa_a_cli_para_os_inquilinos_de_demonstracao():
    """Cláusula do portão: quem cria demo/demo2 na instalação é `plat inquilino criar`, com a senha vindo de
    arquivo modo 600 — nunca de argumento."""
    texto = (RAIZ / "install.sh").read_text(encoding="utf-8")
    assert "plat inquilino criar" in texto or "scripts/plat inquilino criar" in texto
    trecho = texto[texto.index("inquilino criar"):]
    trecho = trecho[: trecho.index("\n\n")] if "\n\n" in trecho else trecho
    assert "--senha-arquivo" in trecho or "--senha-stdin" in trecho
    assert "--senha " not in trecho
