"""Item F2-widgets-3 (varredura completa 15/09): o mesmo bug do `texto`/`botao` (elemento inventado no
manifesto, que `document.createElement` criaria como elemento MORTO porque `web/js/widgets/base.js::definir`
nunca registrou aquele nome) apareceu em MAIS TRÊS manifestos mais antigos — `mapa` ('plat-mapa' em vez de
'plat-w-mapa'), `legenda` ('plat-legenda' em vez de 'plat-w-legenda') e `filtro` ('plat-filtro' em vez de
'plat-w-filtro'). `test_widgets_pagina.py::test_widgets_do_item_usam_o_elemento_que_o_modulo_registra_de_verdade`
só cobria os 12 widgets de um item específico; este teste cobre TODA ENTRADA de `REGISTRO`, para sempre —
lê o `definir('<elemento>', ...)` de verdade no arquivo do módulo (estático, sem precisar de DOM/customElements
em node) e reprova qualquer manifesto cujo `elemento` declarado divirja dele."""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIDGETS_DIR = ROOT / "web/js/widgets"

DEFINIR_RE = re.compile(r"""definir\(\s*['"]([a-z][a-z0-9-]*)['"]""")


def executar_js(codigo: str):
    processo = subprocess.run(["node", "--input-type=module", "-e", codigo], cwd=ROOT, text=True,
                              capture_output=True, check=True)
    return json.loads(processo.stdout)


def _obter_registro():
    return executar_js("""
      const { REGISTRO } = await import('./web/js/widgets/registro.js');
      const saida = [...REGISTRO.values()].map((m) => ({nome: m.nome, elemento: m.elemento, modulo: m.modulo}));
      console.log(JSON.stringify(saida));
    """)


def test_todo_elemento_do_registro_bate_com_o_definir_real_do_modulo():
    manifestos = _obter_registro()
    assert manifestos, "REGISTRO veio vazio"
    divergentes = []
    for manifesto in manifestos:
        modulo = manifesto["modulo"]
        # widget externo (caminho same-origin /api/..., L5-36): o arquivo não existe no repo, nada a
        # conferir aqui — a checagem dele é em tempo de execução (sha256 + mesma origem).
        if not modulo.startswith("./"):
            continue
        caminho = WIDGETS_DIR / modulo[2:]
        assert caminho.is_file(), f"{manifesto['nome']}: módulo {modulo} não existe em {WIDGETS_DIR}"
        texto = caminho.read_text()
        achados = DEFINIR_RE.findall(texto)
        assert achados, f"{manifesto['nome']}: nenhum definir(...) encontrado em {caminho.name}"
        # o módulo deve chamar definir() com o MESMO nome que o manifesto declara; guardamos todos os
        # elementos definidos no arquivo (alguns módulos de fábrica definem só um) para a mensagem de erro.
        if manifesto["elemento"] not in achados:
            divergentes.append({"nome": manifesto["nome"], "declarado": manifesto["elemento"],
                                 "modulo": caminho.name, "definidos_no_modulo": achados})
    assert divergentes == [], divergentes


def test_nenhum_definir_de_widgets_js_fica_de_fora_do_registro_sem_motivo():
    """espelho do teste acima: todo `definir('plat-...', ...)` de `web/js/widgets/*.js` que NÃO é
    `plat-widget-sandboxe` (wrapper de widget externo em iframe, item à parte de REGISTRO — ver
    `sandboxe.js`) tem de aparecer como `elemento` de alguma entrada do registro; evita o erro oposto
    (módulo renomeado e o manifesto ficou para trás apontando para o nome velho, sem sobrar rastro)."""
    manifestos = _obter_registro()
    elementos_no_registro = {m["elemento"] for m in manifestos}
    elementos_definidos = set()
    for caminho in WIDGETS_DIR.glob("*.js"):
        elementos_definidos.update(DEFINIR_RE.findall(caminho.read_text()))
    ignorados = {"plat-widget-sandboxe"}
    orfaos = elementos_definidos - elementos_no_registro - ignorados
    assert orfaos == set(), orfaos
