"""Varredura cruzada A→B gerada do OpenAPI (ADR 0002 seção 16.1, portão P6 executável): para cada (método,
caminho) do docs/openapi.json, quatro chamadas contra o recurso de B — (1) sessão de A, (2) token de A com
admin:inquilino, (3) sessão de A com X-Plat-Inquilino: demo2, (4) sem autenticação. Aceita-se só 401/403/404 (ou
o 2xx declarado de rota que age só sobre o chamador, com resposta sem dado de B). Antes e depois de CADA chamada
o digest de B (como plat_app no contexto de B) tem de ser igual. Medidas rotas_total e rotas_cobertas."""

from pathlib import Path

import pytest

from tests.api import cruzado_casos as cc
from tests.api.conftest import arquivo_openapi, novo_cliente
from tests.api.test_rls import contexto, ids_por_slug

# serial (07/09): cada chamada é cercada por um DIGEST DO INQUILINO B INTEIRO (_digest_b), para provar que a
# rota não escreveu nada lá. Qualquer worker do pytest-xdist que crie um usuário, um item ou um evento em demo2
# no mesmo instante muda esse resumo e reprova o teste por um motivo que nada tem a ver com o que ele prova
# (medido: 'POST /api/login [sem autenticação] alterou B: ...95 -> ...96'). Roda sozinho, com -n 0.
pytestmark = pytest.mark.serial

ROOT = Path(__file__).resolve().parents[2]
DIGEST_SQL = """
SELECT md5(coalesce(string_agg(x::text, ',' ORDER BY x::text), '')) AS d, count(*) AS n FROM (
  SELECT 'u', id::text, login, nome, coalesce(email, ''), perfil, coalesce(papel_id::text, ''), ativo::text,
         totp_ativo::text, trocar_senha::text FROM plat.usuario
  UNION ALL SELECT 'g', id::text, nome, coalesce(resumo, ''), dono_id::text, protegido::text, administrativo::text,
         visibilidade, entrada, contribuicao FROM plat.grupo
  UNION ALL SELECT 'm', grupo_id::text, usuario_id::text, papel, estado, '', '', '', '', '' FROM plat.grupo_membro
  UNION ALL SELECT 't', id::text, nome, coalesce(revogado_em::text, ''), coalesce(expira_em::text, ''),
         coalesce(renovado_por::text, ''), escopos::text, '', '', '' FROM plat.token_servico
  UNION ALL SELECT 'p', id::text, nome, perfil_minimo, '', '', '', '', '', '' FROM plat.papel_personalizado
  UNION ALL SELECT 'pp', papel_id::text, privilegio, '', '', '', '', '', '', '' FROM plat.papel_privilegio
  UNION ALL SELECT 's', token_hash, '', '', '', '', '', '', '', '' FROM plat.sessao
  UNION ALL SELECT 'i', id::text, slug, nome, ativo::text, config::text, '', '', '', '' FROM plat.tenant
) x
"""


def _rotas_do_openapi() -> list[tuple[str, str]]:
    spec = arquivo_openapi()
    return sorted((m.upper(), c) for c, ms in spec["paths"].items() for m in ms)


def _digest_b(con) -> tuple[str, int]:
    con.rollback()
    ids = ids_por_slug(con)
    contexto(con, ids["demo2"])
    with con.cursor() as cur:
        cur.execute(DIGEST_SQL)
        r = cur.fetchone()
    con.rollback()
    return r["d"], r["n"]


@pytest.fixture(scope="module")
def preparacao(sessao_a, sessao_b, sessao_plat, ids):
    p = cc.preparar(sessao_a, sessao_b, sessao_plat, ids)
    yield p
    cc.desfazer(p)


def test_cobertura_100_por_cento(medida):
    """Portão do item L0-02-e (filho de L0-02-tenant-auth): rotas_total = rotas_cobertas em
    tests/medidas/L0-02-e.json. A mesma medida também é gravada em L0-02-tenant-auth.json (convenção do item-pai,
    usada por MANUAL.md/ARQUITETURA.md/CHANGELOG.md desde o turno 2 para todo o bloco de identidade e acesso)."""
    rotas = _rotas_do_openapi()
    faltando = [r for r in rotas if r not in cc.CASOS]
    sobrando = [r for r in cc.CASOS if r not in rotas]
    for item in ("L0-02-tenant-auth", "L0-02-e"):
        medida(item)("rotas_total", len(rotas), "rotas", "len(paths×methods) de docs/openapi.json")
        medida(item)(
            "rotas_cobertas",
            len(rotas) - len(faltando),
            "rotas",
            "rotas do OpenAPI com caso em tests/api/cruzado_casos.py",
        )
    assert faltando == [], f"rotas sem caso cruzado: {faltando}"
    assert sobrando == [], f"casos de rota inexistente: {sobrando}"


def test_quantas_rotas_tem_alvo_real_de_b(preparacao, medida):
    """A conta que a marca de "100 %" escondia. Cobertura é o piso — diz que a rota ENTROU na varredura.
    O que decide o valor de cada caso é o ALVO: se o identificador que A pede é um recurso que B criou de
    verdade nesta rodada, a RLS está sendo posta à prova; se é o UUID nulo (ou um literal `zz-`), o caso só
    prova que um id de ninguém dá 404 — cruzamento honesto, mas fraco, e é preciso dizer qual é qual.

    Medido em 18/09/2026, depois de as sete levas fecharem 960/960. A medida anterior de
    `tests/medidas/L0-02-e.json` dizia 138/138 = "100 %" e era de 06/09, quando a API servia 138 rotas.
    """
    p = preparacao
    identificadores_de_b = {
        str(p.item_b["id"]), str(p.rede_b["id"]), str(p.conexao_b["id"]), str(p.usuario_b["id"]),
        str(p.grupo_b["id"]), str(p.papel_b["id"]), str(p.token_b["id"]), str(p.inquilino_b),
        str(p.job_b.get("id", "")), str(p.agenda_b.get("id", "")), str(p.pasta_b.get("id", "")),
        str(p.convite_b.get("id", "")), str(p.conjunto_b.get("id", "")), str(p.fator_b.get("id", "")),
        str(p.execucao_b.get("id", "")), str(p.modelo_amc_b.get("id", "")),
        str(p.conjunto_amc_b.get("id", "")), str(p.execucao_amc_b.get("id", "")),
        str(p.webhook_b.get("id", "")), str(p.preset_amc_b.get("id", "")), "demo2",
    } - {""}
    com_alvo_real, sem_alvo_real = [], []
    for (metodo, caminho), caso in sorted(cc.CASOS.items()):
        url = caso.url(p)
        corpo = caso.corpo(p)
        texto = f"{url} {corpo}"
        (com_alvo_real if any(i in texto for i in identificadores_de_b) else sem_alvo_real).append(
            f"{metodo} {caminho}")
    for item in ("L0-02-tenant-auth", "L0-02-e"):
        medida(item)(
            "rotas_com_alvo_real_de_b", len(com_alvo_real), "rotas",
            "casos cuja URL ou corpo cita um identificador de um recurso que demo2 criou nesta rodada")
        medida(item)(
            "rotas_sem_alvo_real_de_b", len(sem_alvo_real), "rotas",
            "casos que apontam UUID nulo ou literal zz-: provam que id de ninguem da 404, nao que o id DE B da")
    # não é um portão: é o retrato. O portão de cobertura é test_cobertura_100_por_cento.
    assert len(com_alvo_real) + len(sem_alvo_real) == len(cc.CASOS)
    print(f"\nalvo REAL de B: {len(com_alvo_real)} rotas | sem alvo de B: {len(sem_alvo_real)} rotas")


def _chamar(cliente, metodo, url, corpo, headers):
    kw = {"headers": headers}
    if corpo is not None:
        kw["json"] = corpo
    return cliente.request(metodo, url, **kw)


@pytest.mark.parametrize("metodo,caminho", _rotas_do_openapi(), ids=lambda x: x if isinstance(x, str) else str(x))
def test_rota_nao_cruza(metodo, caminho, preparacao, token_a, conexao_plat_app, cliente):
    p = preparacao
    caso = cc.CASOS.get((metodo, caminho))
    assert caso is not None, (metodo, caminho)
    url, corpo = caso.url(p), caso.corpo(p)
    base = cc.PADRAO
    sessao = novo_cliente() if caso.descartavel else p.sessao_a
    chamadas = [
        ("sessão de A", sessao, {}, caso.aceita | base),
        (
            "token de A (admin:inquilino)",
            cliente,
            {"Authorization": f"Bearer {token_a['token']}"},
            (caso.aceita if caso.publico or caso.proprio else frozenset()) | base,
        ),
        (
            "sessão de A + X-Plat-Inquilino",
            sessao,
            {"X-Plat-Inquilino": "demo2"},
            (caso.aceita if caso.publico else frozenset()) | base,
        ),
        ("sem autenticação", cliente, {}, (caso.aceita if caso.publico else frozenset()) | base),
    ]
    for nome, cli, headers, aceitos in chamadas:
        antes = _digest_b(conexao_plat_app)
        r = _chamar(cli, metodo, url, corpo, headers)
        depois = _digest_b(conexao_plat_app)
        assert r.status_code in aceitos, (
            f"{metodo} {url} [{nome}] → {r.status_code} (aceitos {sorted(aceitos)}): {r.text[:300]}"
        )
        assert antes == depois, f"{metodo} {url} [{nome}] alterou B: {antes} → {depois}"
        if not caso.descartavel:
            # nenhuma rota invalida a sessão de quem chama como efeito colateral (só o logout, que usa cliente próprio)
            viva = p.sessao_a.get("/api/eu")
            assert viva.status_code == 200, (
                f"{metodo} {url} [{nome}] derrubou a sessão de A: {viva.status_code} {viva.text[:200]}; "
                f"cookie no jar: {bool(p.sessao_a.cookies.get('plat_sessao'))}; set-cookie da resposta: "
                f"{r.headers.get('set-cookie')}"
            )
        if 200 <= r.status_code < 300 and r.status_code != 204:
            j = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
            caso.verificar(p, j)
            caso.limpar(p, j)
