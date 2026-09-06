"""Ataque adversarial independente ao grupo G4 do laço (itens L0-07-a-configuracoes-org, L0-09-metadado-catalogo,
L0-10-eventos-historico, L0-11-arquivos-objetos, L0-12-contrato-api-e-limites, L0-14-identidade-visual).

Regra deste arquivo: cada achado é um teste que afirma o comportamento CORRETO e está marcado
`xfail(strict=True)` com o motivo. Enquanto o defeito existir o teste é xfail; no dia em que alguém
consertar, o teste passa, o `strict` reprova a suíte e obriga a tirar a marca — é assim que o achado vira
prova. Os testes SEM marca no fim do arquivo registram o que o ataque NÃO conseguiu derrubar.

Nada aqui conserta nada: o papel é medir e derrubar. Laudo em
laco/handoffs/T3/ataque-g4-ADVERSARIO.md.
"""

import base64
import io
import re
import secrets
import subprocess
import time
from pathlib import Path

import pytest
from PIL import Image

from tests.api.conftest import PREFIXO_TESTE, entrar, novo_cliente

RAIZ = Path(__file__).resolve().parents[2]
WEB = RAIZ / "web"


# ---------------------------------------------------------------- apoio
def _corpo_org(org: dict) -> dict:
    return {
        "nome": org["nome"],
        "cor": org["cor"],
        "idioma_padrao": org["idioma_padrao"],
        "centro": org["mapa"]["centro"],
        "zoom": org["mapa"]["zoom"],
        "basemap": org["mapa"]["basemap"],
        "srid_padrao": org["mapa"]["srid_padrao"],
        "cota_bytes": org["armazenamento"]["cota_bytes"],
        "cota_usuarios": org["usuarios"]["cota"],
        "auth": dict(org["auth"]),
    }


def _png(lado: int = 64, cor: tuple = (200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (lado, lado), cor).save(buf, format="PNG")
    return buf.getvalue()


def _logo_novo(sessao_a) -> str:
    """Grava um logotipo com cor aleatória (sha256 novo a cada chamada) e devolve o sha256."""
    cor = (secrets.randbelow(200) + 30, secrets.randbelow(200) + 30, secrets.randbelow(200) + 30)
    r = sessao_a.post("/api/org/logo", json={"conteudo": base64.b64encode(_png(cor=cor)).decode()})
    assert r.status_code == 200, r.text
    return r.json()["logo"]


@pytest.fixture(scope="module")
def visualizador_a(sessao_a):
    """Usuário de perfil `visualizador` (nenhum privilégio administrativo) no inquilino demo."""
    login = f"{PREFIXO_TESTE}{secrets.token_hex(4)}"
    r = sessao_a.post(
        "/api/usuarios",
        json={"login": login, "nome": "Adversario G4 visualizador", "perfil": "visualizador",
              "papel_id": None, "email": None},
    )
    assert r.status_code == 201, r.text
    u, temporaria = r.json()["usuario"], r.json()["senha_temporaria"]
    c = novo_cliente()
    assert entrar(c, "demo", login, temporaria).status_code == 200
    senha = "Senha-definitiva-1" + secrets.token_hex(3)
    assert c.put("/api/eu/senha", json={"atual": temporaria, "nova": senha}).status_code == 204
    yield c
    sessao_a.delete(f"/api/usuarios/{u['id']}")


def _psql(sql: str) -> str:
    """psql como postgres (só leitura de metadado do schema da trilha; nunca produção)."""
    import os

    schema = os.environ.get("PLAT_SCHEMA", "plat")
    cmd = ["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-A", "-t", "-c",
           sql.replace("plat.", schema + ".")]
    saida = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert saida.returncode == 0, saida.stderr
    return saida.stdout.strip()


# ================================================================ TRANSVERSAL 1 — o contrato comitado
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-01: docs/openapi.json (o 'contrato comitado') está 28 rotas atrás do app vivo e nenhum "
           "teste compara os dois; make check não regenera nem confere. Como test_eventos.py e test_cruzado.py "
           "leem o arquivo comitado, toda rota nova escapa da cobertura de evento e da varredura cruzada.",
)
def test_openapi_comitado_igual_ao_app_vivo():
    import json

    from app.main import app

    vivo = json.loads(json.dumps(app.openapi(), ensure_ascii=False))
    disco = json.loads((RAIZ / "docs" / "openapi.json").read_text(encoding="utf-8"))
    rv = {(m.upper(), c) for c, ms in vivo["paths"].items() for m in ms}
    rd = {(m.upper(), c) for c, ms in disco["paths"].items() for m in ms}
    assert rv - rd == set(), sorted(rv - rd)


# ================================================================ TRANSVERSAL 2 — cobertura de evento
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-02 (L0-10): a cobertura declarada de 100 % é medida contra o OpenAPI COMITADO. Contra o "
           "app vivo são 84 declarações para 111 rotas de escrita = 75,7 %; 27 rotas de escrita sem declaração.",
)
def test_cobertura_de_evento_100_por_cento_contra_o_app_vivo():
    from app.main import app
    from tests.api.eventos_esperados import EVENTOS_POR_ROTA

    vivo = app.openapi()
    escrita = {
        (m.upper(), c) for c, ms in vivo["paths"].items() for m in ms if m.upper() in ("POST", "PUT", "DELETE", "PATCH")
    }
    faltando = sorted(escrita - set(EVENTOS_POR_ROTA))
    assert faltando == [], faltando


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-03 (L0-10): a hipótese do item diz 'toda rota que altera estado grava 1 evento', mas o "
           "teste aceita declaração com lista VAZIA: 6 rotas estão declaradas como 'sem evento', entre elas "
           "POST e DELETE /api/arquivos, que criam e destroem objeto do inquilino.",
)
def test_nenhuma_rota_de_escrita_declarada_sem_evento():
    from tests.api.eventos_esperados import EVENTOS_POR_ROTA

    vazias = sorted(k for k, v in EVENTOS_POR_ROTA.items() if not v)
    assert vazias == [], vazias


# ================================================================ TRANSVERSAL 3 — quem define o teto
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-04 (L0-07-a + L0-11): o admin do INQUILINO eleva a própria cota de armazenamento por "
           "PUT /api/org sem teto superior (OrgEntrada.cota_bytes tem só `ge`), e o valor é propagado como cota "
           "do bucket do Garage. Medido: 20 GiB -> 9e18 bytes com HTTP 200, em máquina com 46 GB livres.",
)
def test_admin_do_inquilino_nao_eleva_a_propria_cota_de_armazenamento(sessao_a):
    original = sessao_a.get("/api/org").json()
    corpo = _corpo_org(original)
    corpo["cota_bytes"] = 9_000_000_000_000_000_000
    r = sessao_a.put("/api/org", json=corpo)
    try:
        assert r.status_code in (403, 422), f"{r.status_code} {r.text[:200]}"
    finally:
        sessao_a.put("/api/org", json=_corpo_org(original))


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-05 (L0-07-a): mesma falha na cota de USUÁRIOS — o admin do inquilino sobe o próprio teto "
           "de assentos por PUT /api/org (cota_usuarios só tem `ge`). Medido: 2.000 -> 1.000.000.000, HTTP 200.",
)
def test_admin_do_inquilino_nao_eleva_a_propria_cota_de_usuarios(sessao_a):
    original = sessao_a.get("/api/org").json()
    corpo = _corpo_org(original)
    corpo["cota_usuarios"] = 1_000_000_000
    r = sessao_a.put("/api/org", json=corpo)
    try:
        assert r.status_code in (403, 422), f"{r.status_code} {r.text[:200]}"
    finally:
        sessao_a.put("/api/org", json=_corpo_org(original))


# ================================================================ TRANSVERSAL 4 — dentro do inquilino não há dono
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-06 (L0-11, GRAVE): DELETE /api/arquivos/{sha256} exige só `autenticado()` — nenhum "
           "privilégio, nenhuma checagem de dono. Um usuário de perfil `visualizador` (só leitura) apaga "
           "qualquer objeto do inquilino, inclusive o logotipo da organização: HTTP 204. Sob token o mesmo "
           "verbo exige escopo admin:inquilino (403 com catalogo:ler) — a sessão de cookie não exige nada.",
)
def test_visualizador_nao_apaga_objeto_do_inquilino(sessao_a, visualizador_a):
    sha = _logo_novo(sessao_a)
    r = visualizador_a.delete(f"/api/arquivos/{sha}?classe=org_logo")
    assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-07 (L0-11): GET /api/arquivos/{sha256} também não checa privilégio nem dono — um "
           "`visualizador` baixa os bytes de qualquer objeto do inquilino conhecendo o sha256.",
)
def test_visualizador_nao_le_objeto_de_outro_usuario(sessao_a, visualizador_a):
    sha = _logo_novo(sessao_a)
    r = visualizador_a.get(f"/api/arquivos/{sha}?classe=org_logo")
    assert r.status_code == 403, f"{r.status_code} {len(r.content)} bytes"


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-08 (L0-10 + L0-11): apagar um objeto do inquilino não gera evento nenhum. A rota está "
           "declarada 'sem evento' em eventos_esperados.py, então o guardião de cobertura aprova. Destruição "
           "de dado sem rastro é exatamente o que o portão do L0-10 promete impedir.",
)
def test_apagar_arquivo_grava_evento(sessao_a):
    sha = _logo_novo(sessao_a)
    antes = sessao_a.get("/api/eventos?limite=1").json()["total"]
    assert sessao_a.delete(f"/api/arquivos/{sha}?classe=org_logo").status_code == 204
    depois = sessao_a.get("/api/eventos?limite=1").json()["total"]
    assert depois > antes, f"nenhum evento novo ({antes} -> {depois})"


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-09 (L0-11): objetos.apagar() abre `db.db()` SEM contexto de inquilino; a política RLS "
           "`p_arquivo` (tenant_id = plat.tenant_atual()) casa com zero linhas e o UPDATE de apagado_em é "
           "engolido em silêncio. Resultado: todo apagar deixa órfão 'linha sem objeto' e GET /api/org "
           "continua apontando para um logotipo que já não existe.",
)
def test_apagar_objeto_marca_a_linha_como_apagada(sessao_a):
    sha = _logo_novo(sessao_a)
    assert sessao_a.delete(f"/api/arquivos/{sha}?classe=org_logo").status_code == 204
    varredura = sessao_a.get("/api/arquivos/_varredura").json()
    orfaos = [o for o in varredura["sem_objeto"] if o["sha256"] == sha]
    assert orfaos == [], varredura


# ================================================================ TRANSVERSAL 5 — append-only de verdade
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-10 (L0-10, GRAVE): a cláusula literal do portão ('plat_app não consegue UPDATE/DELETE em "
           "evento') PASSA, mas plat_app tem EXECUTE em plat.evento_expurgar(int), SECURITY DEFINER, sem "
           "filtro de inquilino e sem validar o argumento. `SELECT plat.evento_expurgar(-1)` faz DROP TABLE na "
           "partição do mês CORRENTE e apaga a auditoria de TODOS os inquilinos. Mesma exposição em "
           "plat.log_expurgar(int). Hoje nenhuma rota chama a função (ver fronteira do laudo), mas qualquer "
           "injeção de SQL na aplicação vira apagamento total de rastro.",
)
def test_plat_app_nao_pode_apagar_particao_de_evento():
    import os

    schema = os.environ.get("PLAT_SCHEMA", "plat")
    concedidas = _psql(
        f"SELECT string_agg(f, ',') FROM (VALUES ('{schema}.evento_expurgar(int)'), ('{schema}.log_expurgar(int)')) "
        f"AS v(f) WHERE has_function_privilege('{schema}_app', f, 'EXECUTE')"
    )
    assert concedidas == "", f"plat_app tem EXECUTE em: {concedidas} (DROP TABLE da partição do mês corrente)"


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-11 (L0-10): a hipótese pede retenção de 12 meses com partição mensal e o portão pede "
           "'partição do mês seguinte criada pelo periódico'. Não existe periódico nenhum: as 5 tarefas de "
           "PERIODICOS não citam evento_particao_garantir nem evento_expurgar/log_expurgar. As partições saíram "
           "de um generate_series(0,3) da migração 003 — depois disso a criação depende do tratamento de "
           "check_violation dentro de evento_registrar, e a retenção de 12 meses nunca roda.",
)
def test_periodico_cria_particao_do_mes_seguinte_e_aplica_retencao():
    fonte = "\n".join(p.read_text(encoding="utf-8") for p in (RAIZ / "app").rglob("*.py"))
    faltam = [f for f in ("evento_particao_garantir", "evento_expurgar", "log_expurgar") if f not in fonte]
    assert faltam == [], f"nenhuma tarefa/periódico da aplicação chama: {faltam}"


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-12 (L0-10): o portão pede 'exportação CSV/JSON' da auditoria e mede 100 mil eventos em "
           "CSV ≤ 10 s. GET /api/eventos não tem parâmetro `formato`: com ?formato=csv devolve JSON e ignora o "
           "parâmetro. Só /api/log (log de acesso HTTP) exporta CSV. A medida de 10 s não existe.",
)
def test_eventos_exportam_csv(sessao_a):
    r = sessao_a.get("/api/eventos?formato=csv&limite=1")
    assert "text/csv" in (r.headers.get("content-type") or ""), r.headers.get("content-type")


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-13 (L0-10): o portão pede a tela 'Auditoria' do admin com filtro por usuário e período e "
           "captura. Não existe web/admin/auditoria.html; web/admin/ tem grupos, log, organizacao, papeis, "
           "tokens e usuarios. O item está marcado 'entregue' no estado.json com essa cláusula por fazer.",
)
def test_tela_auditoria_existe():
    assert (WEB / "admin" / "auditoria.html").exists(), sorted(p.name for p in (WEB / "admin").glob("*.html"))


# ================================================================ L0-12 — contrato e limites
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-14 (L0-12): o portão exige 'rate limit medido (101ª requisição em 60 s = 429 com "
           "Retry-After)'. Não há limite de taxa na API: 140 GET /api/eu em 0,8 s devolveram 140×200. O nginx "
           "só limita /api/login e /api/login/2fa, e com limit_req_status 429 SEM Retry-After — o cabeçalho "
           "que docs/CONTRATO_API.md promete não é emitido em lugar nenhum do repositório.",
)
def test_limite_de_taxa_na_api(sessao_a):
    codigos = [sessao_a.get("/api/eu").status_code for _ in range(140)]
    assert 429 in codigos, {c: codigos.count(c) for c in set(codigos)}


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-15 (L0-12): o portão exige 'teste que provoca cada código de erro e confere o JSON' para "
           "os 12 códigos declarados em docs/CONTRATO_API.md. Não existe arquivo de teste do contrato "
           "(tests/api/ não tem test_contrato*), nem lint que reprove rota nova sem esquema de resposta.",
)
def test_existe_teste_do_contrato_e_lint_de_esquema_de_resposta():
    testes = sorted(p.name for p in (RAIZ / "tests" / "api").glob("test_contrato*.py"))
    assert testes, "sem tests/api/test_contrato*.py"


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-16 (L0-12): docs/CONTRATO_API.md declara Retry-After no 429 e não há uma ocorrência do "
           "cabeçalho em app/, deploy/ ou tests/ — limite documentado que a API (e o nginx) não aplica, "
           "exatamente o alvo nomeado na refutação do item.",
)
def test_retry_after_existe_no_codigo_ou_no_nginx():
    alvos = list((RAIZ / "app").rglob("*.py")) + list((RAIZ / "deploy").rglob("*.conf"))
    achou = any("Retry-After" in p.read_text(encoding="utf-8", errors="ignore") for p in alvos)
    assert achou, "Retry-After só aparece em docs/CONTRATO_API.md"


# ================================================================ L0-07-a — o portão completo
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-17 (L0-07-a): o portão exige blocos de página inicial (≤ 15 blocos, ≤ 8 links por bloco) "
           "e que 16 blocos devolvam 422 com o caminho do erro. O modelo OrgEntrada não tem o campo: 3 blocos "
           "válidos são recusados com 'campo desconhecido', logo a cláusula do 422 com caminho nunca pôde ser "
           "medida. Idem galeria em destaque, banner de aviso, termo de acesso e domínio de e-mail na tela.",
)
def test_pagina_inicial_aceita_blocos(sessao_a):
    original = sessao_a.get("/api/org").json()
    corpo = _corpo_org(original)
    corpo["pagina_inicial"] = {"blocos": [{"tipo": "texto", "texto": "bloco do adversário"}]}
    r = sessao_a.put("/api/org", json=corpo)
    try:
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    finally:
        sessao_a.put("/api/org", json=_corpo_org(original))


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-18 (L0-07-a): a refutação do item manda injetar HTML no texto do banner e conferir que "
           "sai saneado, e exigir ao menos 1 contato administrativo. Nenhum dos dois campos existe — a "
           "refutação não é reprovada nem aprovada: não há o que atacar, o que significa portão não cumprido.",
)
def test_banner_de_aviso_e_saneado(sessao_a):
    original = sessao_a.get("/api/org").json()
    corpo = _corpo_org(original)
    corpo["banner"] = "<script>alert(1)</script>ok"
    r = sessao_a.put("/api/org", json=corpo)
    try:
        assert r.status_code == 200 and "<script>" not in r.text, f"{r.status_code} {r.text[:200]}"
    finally:
        sessao_a.put("/api/org", json=_corpo_org(original))


# ================================================================ L0-11 — saúde obrigatória
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-19 (L0-11): o portão diz '/saude marca garage como obrigatório a partir deste item'. "
           "app/saude.py decide o status só pelo banco (linha 79: 200 if banco == 'ok' else 503); com o Garage "
           "inalcançável a plataforma continua respondendo 200 e 'saudável'.",
)
def test_saude_reprova_quando_o_garage_esta_fora(cliente, monkeypatch):
    from app import saude as mod

    original = mod.sondar_servico
    monkeypatch.setattr(mod, "sondar_servico", lambda url: "erro" if url == mod.settings.PLAT_GARAGE_URL
                        else original(url))
    r = cliente.get("/saude")
    assert r.json()["servicos"]["garage"] == "erro", r.json()["servicos"]
    assert r.status_code == 503, f"{r.status_code} com garage em erro: {r.json()['servicos']}"


# ================================================================ L0-09 — metadado e catálogo
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-20 (L0-09): o portão exige CSW GetRecords além de OGC API Records, ISO 19115-3 além de "
           "19139, e editor de metadado na tela. Não há rota /csw nem tela de metadado; o próprio módulo "
           "app/catalogo/rotas_ogc.py registra o CSW como pendência. Item consta 'parcial' e continua parcial.",
)
def test_csw_e_editor_de_metadado_existem(cliente):
    from app.main import app

    caminhos = set(app.openapi()["paths"])
    tem_csw = any("csw" in c.lower() for c in caminhos)
    tem_tela = (WEB / "conteudo_metadado.html").exists() or (WEB / "js" / "catalogo" / "metadado.js").exists()
    assert tem_csw and tem_tela, {"csw": tem_csw, "tela": tem_tela}


# ================================================================ L0-14 — identidade visual
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-21 (L0-14): cláusula (a) do portão — 'NENHUMA cor ou medida escrita à mão fora dos "
           "tokens; varredura reprova literal de cor em css/js'. Medido: 43 literais de cor nas folhas fora de "
           "web/estilo/tokens.css (style.css 21, mapa.css 9, tarefas.css 9, conteudo.css 4) e 9 em "
           "web/js/mapa/estilo.js. A varredura que o portão exige não existe em tests/ nem no Makefile.",
)
def test_sem_literal_de_cor_fora_dos_tokens():
    padrao = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)")
    fora = {}
    for arquivo in list(WEB.rglob("*.css")) + list((WEB / "js").rglob("*.js")):
        if "vendor" in arquivo.parts or arquivo.name == "tokens.css":
            continue
        n = len(padrao.findall(arquivo.read_text(encoding="utf-8", errors="ignore")))
        if n:
            fora[str(arquivo.relative_to(WEB))] = n
    assert fora == {}, fora


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-22 (L0-14): cláusulas (e) e (g) — página viva /estilo gerada dos tokens e as telas "
           "restiladas sobre os tokens. Não há rota /estilo. Das 19 telas HTML do produto (o portão ainda fala "
           "em 9), só 5 carregam web/estilo/tokens.css: login, uploads, mapa, aceitar_convite, redefinir_senha.",
)
def test_todas_as_telas_usam_os_tokens_e_existe_pagina_estilo():
    from app.main import app

    telas = sorted(list(WEB.glob("*.html")) + list((WEB / "admin").glob("*.html")))
    sem_token = [t.name for t in telas if "estilo/tokens.css" not in t.read_text(encoding="utf-8", errors="ignore")]
    tem_estilo = any(c.rstrip("/").endswith("/estilo") for c in app.openapi()["paths"])
    assert sem_token == [] and tem_estilo, {"sem_tokens": sem_token, "rota_estilo": tem_estilo}


# ================================================================ contrato: erro interno disfarçado de 403
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-23 (L0-12): app/auth/comum.py::erro_do_banco converte QUALQUER "
           "psycopg2.errors.InsufficientPrivilege (SQLSTATE 42501 — GRANT faltando, schema errado, papel mal "
           "configurado: defeito do servidor) em 403 sem_permissao 'operação fora do inquilino da sessão'. Pela "
           "própria tabela de docs/CONTRATO_API.md 403 é 'sem privilégio' do chamador; aqui o servidor afirma "
           "sobre o inquilino do usuário um fato que não mediu, e esconde erro de configuração. Medido: "
           "POST /api/papeis devolve esse 403 quando o erro real é 'permission denied for schema plat'.",
)
def test_privilegio_insuficiente_do_banco_nao_vira_403_de_inquilino():
    import psycopg2

    from app.auth.comum import erro_do_banco

    erro = erro_do_banco(psycopg2.errors.InsufficientPrivilege("permission denied for schema plat"))
    assert erro.status_code >= 500, f"{erro.status_code} {getattr(erro, 'erro', '')}"


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G4-24 (transversal, atinge a prova de isolamento): CursorSchemaAmbiente reescreve `plat.` em "
           "execute() e callproc(), mas NÃO em executemany(). app/auth/rotas_usuarios.py usa executemany em "
           "POST e PUT /api/papeis, então em qualquer ambiente isolado (PLAT_SCHEMA != plat: trilha ou "
           "make homolog) essas rotas batem no schema `plat` de produção e recebem 42501. Efeito medido nesta "
           "base: tests/api/test_cruzado.py — a varredura A->B que prova isolamento em toda rota — termina com "
           "1 failed e 168 errors, ou seja, a garantia de isolamento não é exercida fora de produção.",
)
def test_cursor_de_schema_reescreve_executemany():
    from app.schema_ambiente import CursorSchemaAmbiente

    assert "executemany" in CursorSchemaAmbiente.__dict__, sorted(CursorSchemaAmbiente.__dict__)


# ================================================================ o que AGUENTOU o ataque (sem xfail)
def test_isolamento_entre_inquilinos_aguentou(sessao_a, sessao_b):
    """B não lê objeto, item, metadado ISO nem registro OGC de A; superadmin não escreve config de A."""
    sha = _logo_novo(sessao_a)
    assert sessao_b.get(f"/api/arquivos/{sha}?classe=org_logo").status_code == 404
    r = sessao_a.post(
        "/api/itens",
        json={"tipo": "mapa", "titulo": f"{PREFIXO_TESTE} adversario g4", "resumo": "x", "tags": ["a"],
              "dados": {"esquema_versao": 1, "corpo": {}}},
    )
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    try:
        assert sessao_b.get(f"/api/itens/{iid}/metadado.xml").status_code == 404
        assert sessao_b.get(f"/ogc/records/collections/catalogo/items/{iid}").status_code == 404
    finally:
        sessao_a.patch(f"/api/itens/{iid}", json={"protegido": False})
        sessao_a.delete(f"/api/itens/{iid}")


def test_superadmin_nao_escreve_config_de_outro_inquilino(sessao_plat, sessao_a):
    corpo = _corpo_org(sessao_a.get("/api/org").json())
    corpo["nome"] = "SEQUESTRADO"
    r = sessao_plat.put("/api/org", json=corpo, headers={"X-Plat-Inquilino": "demo"})
    assert r.status_code == 400 and r.json()["erro"] == "cabecalho_nao_aceito", r.text
    assert sessao_a.get("/api/org").json()["nome"] != "SEQUESTRADO"


def test_metadado_iso_escapa_xml_injetado(sessao_a):
    """Título com <script>, ]]> e & sai como XML bem formado e sem marcação crua."""
    import xml.etree.ElementTree as ET

    veneno = f'{PREFIXO_TESTE} <script>alert(1)</script> ]]> & "x" <![CDATA[y]]>'
    r = sessao_a.post(
        "/api/itens",
        json={"tipo": "mapa", "titulo": veneno, "resumo": veneno, "tags": ["a"],
              "dados": {"esquema_versao": 1, "corpo": {}}},
    )
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    try:
        xml = sessao_a.get(f"/api/itens/{iid}/metadado.xml").text
        ET.fromstring(xml.encode())  # levanta se não for bem formado
        assert "<script>" not in xml
    finally:
        sessao_a.delete(f"/api/itens/{iid}")


def test_item_protegido_recusa_exclusao(sessao_a):
    r = sessao_a.post(
        "/api/itens",
        json={"tipo": "mapa", "titulo": f"{PREFIXO_TESTE} protegido g4", "resumo": "x", "tags": ["a"],
              "dados": {"esquema_versao": 1, "corpo": {}}},
    )
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    try:
        assert sessao_a.patch(f"/api/itens/{iid}", json={"protegido": True}).status_code == 200
        r = sessao_a.delete(f"/api/itens/{iid}")
        assert r.status_code == 409 and r.json()["erro"] == "item_protegido", r.text
    finally:
        sessao_a.patch(f"/api/itens/{iid}", json={"protegido": False})
        sessao_a.delete(f"/api/itens/{iid}")


def test_chave_com_travessia_de_caminho_recusada(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-g4-trav", "escopos": ["admin:inquilino"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    c = novo_cliente()
    cab = {"Authorization": "Bearer " + tok["token"], "Content-Type": "application/octet-stream"}
    try:
        assert c.post("/api/arquivos?classe=../etc", content=b"abc", headers=cab).status_code == 422
        assert c.post("/api/arquivos?classe=..", content=b"abc", headers=cab).status_code == 422
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_tempo_de_resposta_do_ataque_registrado(sessao_a):
    """Medida de apoio do laudo: latência de GET /api/eventos com a base da trilha."""
    t0 = time.time()
    r = sessao_a.get("/api/eventos?limite=100")
    assert r.status_code == 200
    assert time.time() - t0 < 5
