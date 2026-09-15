"""Refutação da correção de 20260915T1500_auditoria_apagar_inquilino.sql.

Defeito: `plat.tenant_apagar_interno` apagava toda tabela do schema com `tenant_id`, inclusive
`plat.auditoria`, e o gatilho `plat.tg_auditoria_imutavel()` recusava com `auditoria_imutavel` — a
fixture `inquilino_temporario` (tests/api/conftest.py) e outras 9 suítes erravam no teardown por isso.

Este arquivo prova as três pontas do desenho ao mesmo tempo:
  1. a imutabilidade de `plat.auditoria` continua de pé para DELETE direto, fora da função
     (`test_delete_direto_fora_da_funcao_continua_barrado`);
  2. UPDATE continua barrado mesmo com a marca nova ligada — só DELETE é liberado, e só dentro da função
     (`test_update_continua_barrado_mesmo_com_a_marca_ligada`);
  3. apagar um inquilino de verdade (pela rota) devolve 204 e não deixa nenhuma linha de auditoria daquele
     inquilino para trás (`test_apagar_inquilino_apaga_a_propria_auditoria_e_devolve_204`).
"""

import subprocess

import pytest

from tests.api.conftest import InquilinoTemporario


def _psql(sql: str, schema: str) -> str:
    """psql como postgres (dono de plat.auditoria): só assim o teste alcança o GATILHO em si, sem o REVOKE
    de plat_app na frente disfarçando qualquer coisa de falta de privilégio. Mesmo padrão de
    tests/api/test_auditoria.py::_psql (env pelo `sudo ... env`, nunca por `env=` do subprocess: sudo
    limpa o ambiente e sem isso o search_path cai em `public`)."""
    cmd = ["sudo", "-n", "-u", "postgres", "env", f"PGOPTIONS=-c search_path={schema},public",
           "psql", "-d", "iagro_sat", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql]
    try:
        saida = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:  # sem sudo/psql nesta máquina
        pytest.skip(f"sudo/psql indisponível: {e}")
    if saida.returncode != 0:
        erro = saida.stderr.strip()
        if "sudo:" in erro and "password" in erro:
            pytest.skip(f"sudo sem senha indisponível para postgres: {erro[:120]}")
    return saida.stdout.strip()


def _psql_falha(sql: str, schema: str) -> str:
    """Como `_psql`, mas para chamadas em que se ESPERA erro: devolve o stderr (nunca levanta)."""
    cmd = ["sudo", "-n", "-u", "postgres", "env", f"PGOPTIONS=-c search_path={schema},public",
           "psql", "-d", "iagro_sat", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql]
    try:
        saida = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:
        pytest.skip(f"sudo/psql indisponível: {e}")
    if saida.returncode == 0:
        pytest.fail(f"esperava erro e não veio nenhum: {sql[:120]!r} -> stdout={saida.stdout.strip()!r}")
    erro = saida.stderr.strip()
    if "sudo:" in erro and "password" in erro:
        pytest.skip(f"sudo sem senha indisponível para postgres: {erro[:120]}")
    return erro


@pytest.fixture(scope="module")
def schema(env) -> str:
    return env.get("PLAT_SCHEMA") or "plat"


@pytest.fixture
def linha_marcada(schema):
    """Uma linha de auditoria sintética, presa ao inquilino `demo`, só para os testes 1 e 2 apagarem/editarem
    (nunca uma linha de negócio de verdade). Limpa no fim com a marca de expurgo — o mesmo caminho legítimo
    que `plat.auditoria_expurgar()` usa, provando de novo que ELE continua funcionando."""
    marca = "zt-imutavel-apagar-inquilino"
    _psql(f"INSERT INTO auditoria(tenant_id, acao, origem) "
          f"SELECT t.id, '{marca}', 'aplicacao' FROM tenant t WHERE t.slug = 'demo'", schema)
    id_ = _psql(f"SELECT id FROM auditoria WHERE acao = '{marca}' ORDER BY id DESC LIMIT 1", schema)
    yield int(id_)
    _psql(f"SET plat.auditoria_expurgo = '1'; DELETE FROM auditoria WHERE acao = '{marca}'", schema)


def test_delete_direto_fora_da_funcao_continua_barrado(linha_marcada, schema):
    """DELETE direto na linha, sem a marca `plat.apagando_inquilino` (ninguém fora de
    plat.tenant_apagar_interno a liga): continua caindo no RAISE EXCEPTION 'auditoria_imutavel', mesmo
    como postgres (dono da tabela) — dono sozinho nunca bastou, e continua não bastando."""
    erro = _psql_falha(f"DELETE FROM auditoria WHERE id = {linha_marcada}", schema)
    assert "auditoria_imutavel" in erro, erro


def test_update_continua_barrado_mesmo_com_a_marca_ligada(linha_marcada, schema):
    """A marca nova só libera DELETE. UPDATE, mesmo com ela ligada e como dono, continua recusado —
    do contrário a correção teria aberto uma porta para MASCARAR linha viva, não só apagar inquilino."""
    erro = _psql_falha(
        f"SET plat.apagando_inquilino = '1'; UPDATE auditoria SET acao = 'forjado' WHERE id = {linha_marcada}",
        schema,
    )
    assert "auditoria_imutavel" in erro, erro
    # a linha original sobrevive intacta (a tentativa de UPDATE não colou nada, nem parcialmente)
    intacta = _psql(f"SELECT acao FROM auditoria WHERE id = {linha_marcada}", schema)
    assert intacta == "zt-imutavel-apagar-inquilino", intacta


def test_apagar_inquilino_apaga_a_propria_auditoria_e_devolve_204(sessao_plat, schema):
    """Ponta a ponta pela API: criar um inquilino descartável, deixar rastro de auditoria nele (a própria
    criação do papel já deixa uma linha, via evento), apagar e conferir as duas coisas que o defeito
    original quebrava — o 204 (virava 409 auditoria_imutavel) e zero linha de auditoria daquele tenant_id
    sobrando (a tabela não tem FK para tenant, então nada além do gatilho impediria resíduo)."""
    inq = InquilinoTemporario(sessao_plat)
    tenant_id = inq.id
    apagado = False
    try:
        r = inq.admin.post("/api/papeis", json={"nome": "zt-papel-p-auditoria", "privilegios": ["conteudo.criar"]})
        assert r.status_code == 201, r.text

        antes = int(_psql(f"SELECT count(*) FROM auditoria WHERE tenant_id = {tenant_id}", schema))
        assert antes > 0, "a criação do papel deveria ter deixado ao menos uma linha de auditoria"

        r = sessao_plat.delete(f"/api/plataforma/inquilinos/{tenant_id}")
        assert r.status_code == 204, r.text
        apagado = True

        depois = int(_psql(f"SELECT count(*) FROM auditoria WHERE tenant_id = {tenant_id}", schema))
        assert depois == 0, f"{depois} linha(s) de auditoria do inquilino apagado sobraram"
    finally:
        if not apagado:
            inq.apagar()
