"""`CursorSchemaAmbiente` também reescreve consulta em BYTES (achado do item L4-01-modelo-rede,
06-07/09/2026): `psycopg2.extras.execute_values` monta a consulta final em bytes e chama
`cur.execute(bytes)` — sem o ramo de bytes, essa chamada ia direto ao schema `plat` de PRODUÇÃO
mesmo com PLAT_SCHEMA de uma trilha, porque o `isinstance(query, str)` original nunca via essas
consultas. Teste puramente de função, sem banco: só confere a reescrita de texto."""

from app.schema_ambiente import CursorSchemaAmbiente


def test_reescrever_bytes_troca_schema_quando_nao_padrao(monkeypatch):
    class _Settings:
        PLAT_SCHEMA = "plat_tx"
        PLAT_SCHEMA_TRABALHO = "plat_trabalho_tx"

    import app.settings as settings_mod

    monkeypatch.setattr(settings_mod, "settings", _Settings())
    entrada = b"INSERT INTO plat.rede_no (tenant_id) VALUES (1)"
    saida = CursorSchemaAmbiente._reescrever_bytes(entrada)
    assert saida == b"INSERT INTO plat_tx.rede_no (tenant_id) VALUES (1)"


def test_reescrever_bytes_e_no_op_no_schema_padrao(monkeypatch):
    class _Settings:
        PLAT_SCHEMA = "plat"
        PLAT_SCHEMA_TRABALHO = "plat_trabalho"

    import app.settings as settings_mod

    monkeypatch.setattr(settings_mod, "settings", _Settings())
    entrada = b"INSERT INTO plat.rede_no (tenant_id) VALUES (1)"
    assert CursorSchemaAmbiente._reescrever_bytes(entrada) is entrada


def test_reescrever_bytes_nao_toca_guc_current_setting(monkeypatch):
    class _Settings:
        PLAT_SCHEMA = "plat_tx"
        PLAT_SCHEMA_TRABALHO = "plat_trabalho_tx"

    import app.settings as settings_mod

    monkeypatch.setattr(settings_mod, "settings", _Settings())
    entrada = b"SELECT current_setting('plat.tenant_id', true), plat.rede_no.id FROM plat.rede_no"
    saida = CursorSchemaAmbiente._reescrever_bytes(entrada)
    assert saida == (
        b"SELECT current_setting('plat.tenant_id', true), plat_tx.rede_no.id FROM plat_tx.rede_no"
    )
