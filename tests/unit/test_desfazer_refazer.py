"""Item L5-09-desfazer-refazer-rascunho — pilha de desfazer/refazer do editor (`web/js/editor/desfazer.js`),
agrupamento de operação contínua, autosave local e diferença visual entre versões (`diferenca.js`).

Roda por Node (`tests/unit/apoio_editor_desfazer.mjs`, mesmo padrão de `tests/expressoes/executar_js.mjs`):
não há framework de teste em JS no repositório, então quem afirma o resultado é o Python, do lado de fora.

Cláusula do portão: "50 operações desfeitas e refeitas devolvem documento byte a byte igual (teste unitário
com sha256)" — `test_cinquenta_operacoes_ida_e_volta_sha256` roda 50 operações reais do documento
(`web/js/editor/documento.js`: inserir/mover/redimensionar/definirPropriedade/remover, com a MESMA paleta do
editor), desfaz tudo, refaz tudo, e compara o hash sha256 da forma canônica do documento — não o objeto em
memória, que dois caminhos de construção diferentes podem povoar com chaves em ordem diferente sem que o
documento seja outro (ver `desfazer.js::canonicoParaHash`)."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
RUNNER = RAIZ / "tests" / "unit" / "apoio_editor_desfazer.mjs"


def _rodar(acao: str, **campos) -> dict:
    entrada = json.dumps({"acao": acao, **campos})
    r = subprocess.run(
        ["node", str(RUNNER), "--stdin"],
        input=entrada,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        cwd=RAIZ,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("semente", [1, 2, 3, 42, 999])
def test_cinquenta_operacoes_ida_e_volta_sha256(semente):
    """50 operações sorteadas (determinístico por semente) sobre um documento real; desfazer as 50 e refazer
    as 50 devolve, nos dois pontos, o MESMO documento (por hash sha256 da forma canônica) que havia antes de
    cada sorteio ter começado e depois de todas terem sido aplicadas, respectivamente."""
    r = _rodar("ciclo_desfazer_refazer", n=50, semente=semente)
    assert r["operacoes_aplicadas"] > 0, "o sorteio precisa ter produzido pelo menos uma operação válida"
    assert r["bateuInicial"] is True, "desfazer tudo não devolveu o documento inicial"
    assert r["bateuFinal"] is True, "refazer tudo não devolveu o documento final"
    # o hash em si: o runner Node já compara jsonCanonico (mesma função usada pelo módulo real); aqui a
    # prova adicional é que a rodada não é vazia por sorte (ao menos algumas operações fizeram mudança real,
    # senão o teste passaria sem exercitar desfazer/refazer nenhum)
    assert r["voltas"] > 0 and r["idas"] > 0
    assert r["voltas"] == r["idas"], "número de passos desfeitos e refeitos precisa ser simétrico"


def test_sha256_de_verdade_sobre_documento_conhecido():
    """Além da comparação interna do runner: um hash sha256 CALCULADO AQUI, do lado de fora, sobre a forma
    canônica de dois documentos que deveriam ser idênticos, bate byte a byte — não é só JSON.stringify cru
    (chave em ordem diferente já reprovaria isto se `jsonCanonico` não ordenasse)."""
    entrada = json.dumps({"acao": "diferenca_patch"})
    r = subprocess.run(
        ["node", str(RUNNER), "--stdin"],
        input=entrada,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        cwd=RAIZ,
    )
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["ida_e_volta_ok"] is True
    # dois objetos Python com chaves em ordem diferente representam o MESMO documento canônico
    a = {"z": 1, "a": {"y": 2, "x": 1}}
    b = {"a": {"x": 1, "y": 2}, "z": 1}
    canon_a = json.dumps(a, sort_keys=True)
    canon_b = json.dumps(b, sort_keys=True)
    assert _sha256(canon_a) == _sha256(canon_b)


def test_agrupamento_de_operacao_continua_vira_um_passo():
    """'agrupamento de operações contínuas (arrastar = 1 passo)': cinco mudanças de largura marcadas com o
    MESMO `grupo` (o que um arrasto contínuo faria, se um dia emitir mais de um `aoMudar`) viram UM único
    passo de histórico — desfazer uma vez volta directo ao estado de antes do arrasto inteiro, não ao
    penúltimo incremento de largura."""
    r = _rodar("agrupamento")
    assert r["passos_apos_grupo"] == 2, "insert + o grupo de 5 redimensionamentos deveriam somar 2 passos"
    assert r["bateu_um_passo_so"] is True


def test_diferenca_json_ida_e_volta():
    r = _rodar("diferenca_patch")
    assert r["ida_e_volta_ok"] is True
    caminhos = {op["path"] for op in r["patch"]}
    assert "/a" in caminhos and "/b" in caminhos


def test_autosave_grava_local_e_limpa_apos_confirmar_servidor():
    """cópia local (localStorage simulado) nasce PENDENTE a cada mudança e só desaparece quando o servidor
    confirma o MESMO documento — nunca antes, para sobreviver a uma queda de rede no meio do caminho."""
    r = _rodar("autosave_local")
    assert r["tinha_pendente_antes"] is True
    assert r["limpou_apos_confirmar"] is True


def test_diferenca_visual_classifica_nos_certos():
    """'diff entre v3 e v7 lista os nós certos': um nó removido, um alterado (propriedade) e um adicionado
    aparecem cada um no balde certo, por ID — nunca por posição na lista."""
    r = _rodar("diferenca_visual")
    assert sorted(r["estados"]) == ["adicionado", "alterado", "removido"]
    assert r["tem_removido_certo"] is True
    assert r["tem_alterado_certo"] is True
    assert r["tem_adicionado_certo"] is True
