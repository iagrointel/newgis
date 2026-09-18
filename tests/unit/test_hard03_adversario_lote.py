"""Prova do portão de HARD-03-adversario-por-linha-em-lote sobre a auditoria em lote
(`laco/adversario_lote.py`) e o guard de `laco/marcar_item.py`.

Cobre as três cláusulas do portão e a refutação registrada no laudo T9 linha-L7-2:

1. "laudo por item em laco/handoffs" — a auditoria casa item entregue ↔ laudo que o cita;
2. "taxa de refutação e lista de consertos" — saem do ledger, com a matemática conferida;
3. "nenhum item vira 'entregue com laudo' sem laudo" — `marcar_item.py entregue` é recusado
   sem laudo (regressão exata do T9: os cinco itens que ficaram entregues sem laudo prévio)
   e o lote reprova qualquer entregue sem laudo que já esteja no estado;
4. a refutação que o adversário ia tentar: "um portão que só passa com fixture falsa é
   detectado" — arquivo com NOME de laudo mas sem veredito/evidência de execução não conta,
   e handoff do próprio construtor (autorrelato) nunca conta.

Tudo contra um laco de mentira em tmp_path (PLAT_LACO), sem tocar no estado real.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
LACO_REPO = RAIZ / "laco"
sys.path.insert(0, str(LACO_REPO))

import adversario_lote  # noqa: E402

ITENS_T9 = (
    "L7-06-c-logs-consulta-req-id",
    "L7-06-d-paineis",
    "L7-04-a-manual-capturas-geradas",
    "L7-04-d-videos-por-tarefa",
    "L7-29-roteiro-demonstracao",
)

LAUDO_REAL = """# Laudo adversário — {item}

Adversário independente, não construí nada disto.

## Veredito: REFUTADO

## Evidência literal (comando e saída)
```bash
$ curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:8150/api/jobs
401
```
O portão dizia 403, veio 401 -> cláusula caiu.
"""

AUTORRELATO = """# Handoff do construtor — {item}

Tudo pronto, testes passando, medido em banca. Veredito: refutado nada.
Comando rodado: make check -> verde.
"""


def _faz_laco(tmp_path: Path, itens, ledger=(), arquivos=()) -> Path:
    """Monta um laco mínimo: estado.json com `itens` [(id, estado)] e `ledger`, e arquivos
    (caminho-relativo, texto) sob handoffs/."""
    laco = tmp_path / "laco"
    (laco / "handoffs").mkdir(parents=True)
    (laco / "estado.json").write_text(json.dumps({
        "turno": 9,
        "backlog": [{"id": i, "estado": e} for i, e in itens],
        "ledger": list(ledger),
        "placar": {"turnos": 9},
    }), encoding="utf-8")
    for rel, texto in arquivos:
        p = laco / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
    return laco


def _marca(laco: Path, *args, env_extra=None) -> subprocess.CompletedProcess:
    env = dict(os.environ, PLAT_LACO=str(laco), **(env_extra or {}))
    return subprocess.run(
        [sys.executable, str(LACO_REPO / "marcar_item.py"), *args],
        capture_output=True, text=True, env=env, timeout=60)


def test_laudo_real_conta_e_autorrelato_nao(tmp_path):
    laco = _faz_laco(tmp_path, [("L9-01-a-foo", "entregue"), ("L9-01-b-bar", "entregue")],
                     arquivos=[
                         ("handoffs/T9/L9-01-a-foo-laudo-adversario.md", LAUDO_REAL.format(item="L9-01-a-foo")),
                         ("handoffs/T9/L9-01-b-bar.md", AUTORRELATO.format(item="L9-01-b-bar")),
                     ])
    com = adversario_lote.itens_com_laudo(laco, ["L9-01-a-foo", "L9-01-b-bar"])
    assert list(com) == ["L9-01-a-foo"], f"autorrelato do construtor contou como laudo: {com}"


def test_laudo_falso_sem_evidencia_nao_conta(tmp_path):
    """A refutação anunciada: portão que só passa com fixture falsa. Arquivo com nome de
    laudo, citando o item, mas sem veredito nem comando/saída — não pode valer."""
    falso = "# linha-L9-laudo-adversario-1\n\nOlhei o item L9-02-a-baz e parece tudo certo.\n"
    laco = _faz_laco(tmp_path, [("L9-02-a-baz", "entregue")],
                     arquivos=[("handoffs/T9/linha-L9-laudo-adversario-1.md", falso)])
    assert not adversario_lote.itens_com_laudo(laco, ["L9-02-a-baz"])
    r = adversario_lote.auditar(laco)
    assert r["sem_laudo"] == ["L9-02-a-baz"]


def test_regressao_t9_cinco_entregues_sem_laudo_previo(tmp_path):
    """Exatamente o achado do laudo T9 linha-L7-2: os cinco itens entregues com só o handoff
    do construtor (T3/T4/T8) — o portão do lote reprova e nomeia os cinco."""
    arquivos = [(f"handoffs/T3/{i}.md", AUTORRELATO.format(item=i)) for i in ITENS_T9]
    arquivos.append(("handoffs/T9/linha-L7-laudo-adversario-1.md",
                     LAUDO_REAL.format(item="L7-99-z-outro-item-qualquer")))
    laco = _faz_laco(tmp_path, [(i, "entregue") for i in ITENS_T9] + [("L7-99-z-outro-item-qualquer", "entregue")],
                     arquivos=arquivos)
    r = adversario_lote.auditar(laco)
    assert sorted(r["sem_laudo"]) == sorted(ITENS_T9)
    proc = subprocess.run([sys.executable, str(LACO_REPO / "adversario_lote.py"),
                           "--laco", str(laco), "--portao"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    for i in ITENS_T9:
        assert i in proc.stdout


def test_portao_passa_quando_todo_entregue_tem_laudo(tmp_path):
    laco = _faz_laco(tmp_path, [(i, "entregue") for i in ITENS_T9],
                     arquivos=[("handoffs/T9/linha-L7-laudo-adversario-2.md",
                                LAUDO_REAL.format(item=" e ".join(ITENS_T9)))])
    proc = subprocess.run([sys.executable, str(LACO_REPO / "adversario_lote.py"),
                           "--laco", str(laco), "--portao"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_taxa_de_refutacao_e_lista_de_consertos(tmp_path):
    ledger = [
        {"item": "L9-10-a", "estado": "refutado", "nota": "adversario G9: caiu a clausula 2"},
        {"item": "L9-10-b", "estado": "refutado", "nota": "adversario G9: caiu tudo"},
        {"item": "L9-10-c", "estado": "entregue", "nota": "adversario G9: portao reproduzido, nada caiu"},
        {"item": "L9-10-a", "estado": "entregue", "nota": "conserto do achado G9, reprovado"},
        {"item": "L9-10-d", "estado": "entregue", "nota": "construtor marca sem adversario"},
    ]
    laco = _faz_laco(tmp_path, [("L9-10-a", "entregue"), ("L9-10-b", "refutado"),
                                ("L9-10-c", "entregue"), ("L9-10-d", "entregue")],
                     ledger=ledger,
                     arquivos=[("handoffs/T9/g9-ADVERSARIO.md",
                                LAUDO_REAL.format(item="L9-10-a L9-10-b L9-10-c L9-10-d"))])
    r = adversario_lote.auditar(laco)
    assert sorted(r["auditados"]) == ["L9-10-a", "L9-10-b", "L9-10-c"]
    assert sorted(r["refutados"]) == ["L9-10-a", "L9-10-b"]  # taxa 2/3
    assert r["consertos"] == ["L9-10-a"]  # b continua refutado; c nunca caiu


def test_marcar_recusa_entregue_sem_laudo_e_nao_toca_estado(tmp_path):
    laco = _faz_laco(tmp_path, [("L9-20-a-x", "parcial")])
    proc = _marca(laco, "L9-20-a-x", "entregue", "prova qualquer", "abc1234")
    assert proc.returncode != 0
    assert "HARD-03" in proc.stderr
    estado = json.loads((laco / "estado.json").read_text(encoding="utf-8"))
    assert estado["backlog"][0]["estado"] == "parcial", "a recusa alterou o estado"


def test_marcar_aceita_entregue_com_laudo(tmp_path):
    laco = _faz_laco(tmp_path, [("L9-21-a-x", "parcial")],
                     arquivos=[("handoffs/T9/L9-21-a-x-laudo-adversario.md",
                                LAUDO_REAL.format(item="L9-21-a-x"))])
    proc = _marca(laco, "L9-21-a-x", "entregue", "laudo T9 acima", "abc1234")
    assert proc.returncode == 0, proc.stderr
    estado = json.loads((laco / "estado.json").read_text(encoding="utf-8"))
    assert estado["backlog"][0]["estado"] == "entregue"


def test_override_do_dono_passa_mas_fica_gritado_no_ledger(tmp_path):
    laco = _faz_laco(tmp_path, [("L9-22-a-x", "parcial")])
    proc = _marca(laco, "L9-22-a-x", "entregue", "caso especial",
                  env_extra={"PLAT_MARCAR_SEM_LAUDO": "decisao do dono em 18/09"})
    assert proc.returncode == 0, proc.stderr
    estado = json.loads((laco / "estado.json").read_text(encoding="utf-8"))
    nota = estado["ledger"][-1]["nota"]
    assert "SEM-LAUDO(dono)" in nota and "decisao do dono" in nota
    r = adversario_lote.auditar(laco)  # e o lote continua apontando o furo
    assert r["sem_laudo"] == ["L9-22-a-x"] and len(r["sem_laudo_dono"]) == 1


def test_laco_real_do_repositorio_audita_sem_quebrar():
    """Robustez: a auditoria roda sobre o laco/ versionado (foto do estado) sem exceção e
    com saída estruturada — o número em si é da foto, não se asserta."""
    proc = subprocess.run([sys.executable, str(LACO_REPO / "adversario_lote.py"),
                           "--laco", str(LACO_REPO), "--portao"],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode in (0, 1), proc.stderr
    assert "taxa de refutação:" in proc.stdout
    assert "por linha" in proc.stdout
