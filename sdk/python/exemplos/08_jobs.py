"""Exemplo 8/10 — criar um job e esperar o resultado (`.jobs.esperar()`).

Sem worker vivo o job fica "pendente" para sempre; o teste (`tests/sdk/test_exemplos.py`) sobe um
worker de verdade (`app.jobs.worker`) só para este exemplo. `prova.progresso` é o tipo de
diagnóstico do próprio produto (`app/jobs/tipos_prova.py`), não é mock do SDK."""

from __future__ import annotations

from plat import Plataforma
from plat_gerado.api.jobs import criar_job_api_jobs_post as rt_criar_job
from plat_gerado.models.criar_job_api_jobs_post_corpo import CriarJobApiJobsPostCorpo


def main(url: str, inquilino: str, login: str, senha: str) -> None:
    p = Plataforma.entrar(url, inquilino, login, senha, nome_token="sdk-python-exemplo-08")
    try:
        corpo = CriarJobApiJobsPostCorpo.from_dict(
            {"tipo": "prova.progresso", "parametros": {"passos": 3, "duracao_s": 1}}
        )
        resposta = rt_criar_job.sync_detailed(client=p._cliente, body=corpo)
        assert resposta.status_code == 201, resposta.content
        import json

        job_id = json.loads(resposta.content)["id"]
        print(f"job criado: {job_id}")

        job = p.jobs.esperar(job_id, tempo_limite_s=30, intervalo_s=0.5)
        assert job["estado"] == "concluido", job
        print(f"job {job['estado']}: progresso={job['progresso']}, resultado={job.get('resultado')}")
    finally:
        p.tokens.revogar(p.token_id)
        p.fechar()


if __name__ == "__main__":
    from _ambiente import do_ambiente

    main(*do_ambiente())
