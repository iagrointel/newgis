"""Adversário de linha L7 operação (parte 1) — item `L7-19-segredos-e-certificados`
(laudo `laco/handoffs/T9/linha-L7-laudo-adversario-1.md`).

A hipótese do PRÓPRIO item já registra: "token admin do Garage da prova está em claro em `garage.toml` —
corrigir". As unidades `plat-api`/`plat-worker` evoluíram e hoje usam `LoadCredential=` para `PLAT_SECRET`
(com `PLAT_SECRET_ANTERIOR` para a rotação), `PLAT_DSN` e `PLAT_GARAGE_ADMIN_TOKEN` — mais do que a nota
anterior do ledger ("2 de 5") registrava. Mas a unidade `plataforma-garage` (o processo que fala o
protocolo Garage de verdade, e que está na lista de "nunca reiniciar" desta rodada — este teste só LÊ) usa
`ExecStart=.../garage -c /home/dev/plataforma/pipeline/garage/garage.toml server`: um arquivo comum em
disco, fora de `/run/credentials`, permissão 600 mas dono `dev` (o mesmo usuário que roda TODO processo
desta máquina, sessões de outros agentes incluídas) — não root, não `LoadCredential`, sem expirar. E
`rpc_secret` nem está entre os 5 nomes que `scripts/segredo_rotacionar.py` conhece: não existe rotação
para ele.

Este teste só faz o que a regra 3 do brief permite: extrai NOMES de chave por regex (nunca o valor) do
arquivo, e confere permissão/dono. Nunca imprime, nunca faz `cat`/`grep` do conteúdo além do nome da
chave.

xfail(strict=True): quando `rpc_secret`/`admin_token` do Garage saírem de um arquivo comum para
`LoadCredential=` (ou equivalente) e ganharem rotação no `segredo_rotacionar.py`, este teste passa."""

from __future__ import annotations

import re
import stat
from pathlib import Path

import pytest

GARAGE_TOML = Path("/home/dev/plataforma/pipeline/garage/garage.toml")
ROTACIONAR = Path(__file__).resolve().parents[3] / "scripts" / "segredo_rotacionar.py"
NOME_CHAVE = re.compile(r"^([a-z_]+)\s*=", re.MULTILINE)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "/home/dev/plataforma/pipeline/garage/garage.toml (usado pela unidade plataforma-garage, "
        "ExecStart=... -c .../garage.toml) guarda rpc_secret e admin_token em texto claro num arquivo "
        "comum (não LoadCredential=), 600 dev:dev — legível por qualquer processo rodando como o usuário "
        "dev, que é todo processo desta máquina. rpc_secret nem está entre os 5 nomes que "
        "scripts/segredo_rotacionar.py sabe rotacionar. Item L7-19-segredos-e-certificados: a hipótese do "
        "próprio item já pedia para 'corrigir' isto."
    ),
)
def test_garage_toml_nao_guarda_segredo_em_arquivo_comum():
    if not GARAGE_TOML.exists():
        pytest.skip(f"{GARAGE_TOML} não existe nesta máquina")
    nomes = set(NOME_CHAVE.findall(GARAGE_TOML.read_text()))
    achados_sensiveis = nomes & {"rpc_secret", "admin_token"}
    assert not achados_sensiveis, (
        f"{GARAGE_TOML} ainda guarda {sorted(achados_sensiveis)} em texto claro fora de LoadCredential"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "scripts/segredo_rotacionar.py só conhece PLAT_SECRET | PLAT_DSN | PLAT_DSN_WORKER | "
        "PLAT_GARAGE_ADMIN_TOKEN | PLAT_GARAGE_CHAVE_S3:<slug> — rpc_secret do Garage (usado para RPC "
        "entre nós do cluster) não tem rotação nenhuma. Item L7-19-segredos-e-certificados."
    ),
)
def test_rpc_secret_do_garage_tem_rotacao():
    texto = ROTACIONAR.read_text()
    assert "rpc_secret" in texto.lower() or "RPC_SECRET" in texto, (
        "nenhuma menção a rpc_secret em scripts/segredo_rotacionar.py — sem mecanismo de rotação"
    )


def test_garage_toml_ao_menos_nao_e_legivel_por_outros():
    """Controle: a permissão do arquivo (0600) bloqueia OUTROS usuários — o problema medido é o mesmo
    usuário (dev) rodando todo processo desta máquina, não uma permissão 644 óbvia. Isto PASSA (não é
    xfail): serve para não perder de vista, no futuro, se a permissão regredir para algo pior."""
    if not GARAGE_TOML.exists():
        pytest.skip(f"{GARAGE_TOML} não existe nesta máquina")
    modo = stat.S_IMODE(GARAGE_TOML.stat().st_mode)
    assert modo & 0o077 == 0, f"garage.toml legível/gravável por grupo ou outros: {oct(modo)}"
