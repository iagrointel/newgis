"""Achado 16/09 (wt/f2-ferrreg, família 'ferramenta não registrada'): `ferramentas.executar` falhava com
`FalhaDefinitiva: ferramenta não registrada: 'buffer'` porque o catálogo de manifestos (buffer, vetor, rede)
só era carregado por `app/ferramentas/rotas.py`, importado apenas pelo processo da API (`app/main.py`) — o
worker (`app/jobs/worker.py` → `app/jobs/tipos.py` → `app/ferramentas/executor.py`) nunca passava por lá.
Este teste prova a raiz do conserto sem tocar em `app.main`: importa só `app.jobs.tipos` (o que o worker de
fato importa) e afirma que `buffer` já está no catálogo — se alguém reintroduzir o carregamento do catálogo
num módulo que só a API importa, este teste reprova antes de chegar a um `job_log` de produção."""

import sys


def test_buffer_esta_no_catalogo_so_com_o_import_do_worker():
    for nome in list(sys.modules):
        if nome == "app.main" or nome.startswith("app.main."):
            raise AssertionError("app.main já estava importado neste processo de teste — o teste não prova "
                                 "nada isolado do processo da API; rode este arquivo sozinho")

    from app.ferramentas import registro
    from app.jobs.tipos import REGISTRO  # noqa: F401 — é exatamente o que app/jobs/worker.py importa

    assert "app.main" not in sys.modules, "importar app.jobs.tipos não deveria puxar app.main"
    f = registro.obter("buffer")
    assert f is not None, "buffer não está no catálogo GP só com o import que o worker faz"
    assert f.categoria == "proximidade"
