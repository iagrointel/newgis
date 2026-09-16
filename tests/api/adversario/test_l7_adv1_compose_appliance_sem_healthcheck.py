"""Adversário de linha L7 operação (parte 1) — item `L7-01-a-compose-perfis`
(laudo `laco/handoffs/T9/linha-L7-laudo-adversario-1.md`).

Portão literal do item: "`docker compose --profile appliance up -d` em máquina com só docker sobe TODOS
os serviços com healthcheck verde em ≤ 10 min (medido)". Isso pressupõe que TODO serviço do perfil
`appliance` declare um `healthcheck:` — sem ele não existe "verde" para medir.

`deploy/compose/docker-compose.yml` hoje só declara `healthcheck:` para o serviço `db`. Os outros 6
serviços do perfil `appliance` (`garage`, `martin`, `titiler`, `api-appliance`, `worker-appliance`,
`nginx`) não têm bloco `healthcheck` nenhum — não é "não medido ainda", é "não escrito". Consistente com
`deploy/compose/VERSOES.txt`, que marca `plat-db`, `plat-garage`, `plat-martin`, `plat-titiler` e
`plat-nginx` como `PENDENTE` (nunca construídas) e com o comentário no topo do próprio compose ("disco a
95-96%").

Não precisa do daemon do Docker para provar isto — é leitura estática do YAML (`docker compose config`
também mostra o mesmo, mas o parse direto evita depender do daemon estar de pé nesta rodada).

xfail(strict=True): quando os 6 serviços restantes ganharem `healthcheck:` (e as imagens forem
construídas, o que é o alvo do próprio D21 do laço), este teste passa "de verdade"."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

COMPOSE = Path(__file__).resolve().parents[3] / "deploy" / "compose" / "docker-compose.yml"


def _servicos_do_perfil(perfil: str) -> dict:
    doc = yaml.safe_load(COMPOSE.read_text())
    return {
        nome: svc
        for nome, svc in doc["services"].items()
        if perfil in (svc.get("profiles") or [])
    }


@pytest.mark.xfail(
    strict=True,
    reason=(
        "deploy/compose/docker-compose.yml só define healthcheck: para o serviço 'db' no perfil "
        "appliance; garage/martin/titiler/api-appliance/worker-appliance/nginx não têm healthcheck "
        "nenhum, então o portão ('sobe todos os serviços com healthcheck verde') não pode ser satisfeito "
        "hoje — não é falta de medição, é ausência da declaração. Item L7-01-a-compose-perfis."
    ),
)
def test_todo_servico_appliance_tem_healthcheck():
    servicos = _servicos_do_perfil("appliance")
    assert len(servicos) >= 5, servicos  # sanidade: o compose tem de ter os serviços esperados
    sem_healthcheck = sorted(nome for nome, svc in servicos.items() if "healthcheck" not in svc)
    assert not sem_healthcheck, (
        f"serviços do perfil appliance sem healthcheck: {sem_healthcheck}"
    )
