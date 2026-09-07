"""Os testes de segurança de upload (item L7-03-a) usam as MESMAS sessões/tokens da suíte de API: reexporta as
fixtures de `tests/api/conftest.py` (o pytest coleta fixture importada para o namespace do conftest)."""

from tests.api.conftest import (  # noqa: F401 — fixtures reexportadas
    cred,
    ids,
    limpeza_de_residuos,
    sessao_a,
    sessao_b,
    sessao_plat,
    token_a,
    usuarios_a,
    usuarios_b,
)
