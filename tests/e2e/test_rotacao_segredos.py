"""Item L7-19-segredos-e-certificados, cláusula 1 do portão: `plat segredo rotacionar <nome>` para CADA
um dos 5 segredos, com prova de que o valor antigo deixa de funcionar e o serviço não cai (0 5xx medido).

Lento e destrutivo de propósito (cria/apaga role de Postgres, unidade systemd, bucket no Garage) — nunca
toca `plat-api`/`plat-worker`/`nginx`/`postgres` de PRODUÇÃO (limite duro do item): os 4 segredos que
precisam de restart são provados contra `plat-teste-segredo-{a,b,garage}` (systemd, socket activation,
criados e apagados por `scripts/prova_segredos_l7_19.py`); o 5º (chave S3 por inquilino) não reinicia
nada — é medido contra o Garage real com um bucket descartável (`scripts/prova_garage_chave_s3.py`).

Exige `sudo -n` (sem senha) para systemctl/psql/journalctl; pula com mensagem quando não há."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.lento
ROOT = Path(__file__).resolve().parents[2]


def _sudo_ok() -> bool:
    return subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0


def _rodar(script: str, timeout: int = 120) -> tuple[int, str, str]:
    r = subprocess.run(
        ["sudo", "-n", sys.executable, str(ROOT / "scripts" / script)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=timeout,
    )
    return r.returncode, r.stdout, r.stderr


def _todos_5xx(bruta: dict) -> int:
    total = 0
    for v in bruta["rotacoes"].values():
        restarts = [v["restart"]] if v.get("restart") else v.get("restart_cadeia", [])
        total += sum(r["codigo_5xx"] for r in restarts)
    return total


@pytest.fixture(autouse=True)
def _precisa_de_sudo():
    if not _sudo_ok():
        pytest.skip("sudo -n indisponível nesta máquina — cláusula não checada, nunca 'aprovada por padrão'")


def test_quatro_segredos_com_restart_rotacionam_sem_5xx_e_invalidam_o_valor_antigo():
    codigo, saida, erro = _rodar("prova_segredos_l7_19.py")
    if codigo != 0:
        pytest.fail(f"scripts/prova_segredos_l7_19.py falhou (código {codigo}):\n{saida[-4000:]}\n{erro[-2000:]}")
    bruta = json.loads((ROOT / "tests" / "medidas" / "_prova_segredos_bruta.json").read_text(encoding="utf-8"))
    assert bruta["status"] == "ok", bruta
    assert _todos_5xx(bruta) == 0, "houve resposta 5xx durante alguma rotação com restart"

    rot = bruta["rotacoes"]
    assert rot["PLAT_DSN"]["senha_antiga_ainda_autentica"] is False
    assert rot["PLAT_DSN_WORKER"]["senha_antiga_ainda_autentica"] is False
    assert rot["PLAT_GARAGE_ADMIN_TOKEN"]["token_antigo_ainda_autentica"] is False
    assert rot["PLAT_GARAGE_ADMIN_TOKEN"]["token_novo_autentica"] is True
    # PLAT_SECRET: dupla-chave — o valor antigo vira ANTERIOR, não "para de funcionar" (é o ponto do item:
    # sessão aberta sobrevive 24h); a prova de que o mecanismo respeita isso é tests/unit/test_seguranca_rotacao.py
    assert rot["PLAT_SECRET"]["sha_anterior_gravado"] == rot["PLAT_SECRET"]["sha_antigo"]
    assert rot["PLAT_SECRET"]["sha_novo"] != rot["PLAT_SECRET"]["sha_antigo"]


def test_chave_s3_por_inquilino_rotaciona_sem_reiniciar_nada_e_invalida_a_antiga():
    codigo, saida, erro = _rodar("prova_garage_chave_s3.py")
    if codigo != 0:
        pytest.fail(f"scripts/prova_garage_chave_s3.py falhou (código {codigo}):\n{saida[-4000:]}\n{erro[-2000:]}")
    resultado = json.loads((ROOT / "tests" / "medidas" / "_prova_garage_chave_s3.json").read_text(encoding="utf-8"))
    assert resultado["chave_nova_funciona"] is True
    assert resultado["chave_antiga_falha_depois_de_apagada"] is True
    assert resultado["restart"] is None  # a cláusula "e o serviço não cai" aqui é trivial: nada reinicia
    assert resultado["saude_plat_api_antes"] == 200
    assert resultado["saude_plat_api_depois"] == 200
