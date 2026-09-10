"""Assinatura viva no navegador (item L2-06-d): `web/js/vivo/assinatura.js`.

Duas coisas que só se provam rodando o módulo, e que o portão e a refutação cobram:
1. COALESCÊNCIA — mil eventos numa rajada não podem virar mil consultas; a janela de 1 s tem de agrupar
   tudo numa chamada só, já com o conjunto de camadas que mudaram.
2. FALLBACK — quando o fluxo não abre (proxy sem SSE, `PLAT_SSE_LIGADO=false` → 503), a assinatura avisa
   UMA vez e quem chamou volta ao intervalo; nada de tela parada.

Roda em Node, como `tests/unit/test_expressao_equivalencia.py` já faz com o avaliador de expressão."""

import json
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
MODULO = RAIZ / "web" / "js" / "vivo" / "assinatura.js"

ROTEIRO = """
import {{ assinarCamadas, horaCurta }} from '{modulo}';

class FonteFalsa {{
  constructor(url) {{ this.url = url; this.ouvintes = {{}}; FonteFalsa.ultima = this; }}
  addEventListener(nome, fn) {{ (this.ouvintes[nome] = this.ouvintes[nome] || []).push(fn); }}
  emitir(nome, dados) {{
    for (const fn of this.ouvintes[nome] || []) fn(dados === undefined ? {{}} : {{ data: JSON.stringify(dados) }});
  }}
  close() {{ this.fechada = true; }}
}}
globalThis.EventSource = FonteFalsa;

const saida = {{}};

// 1. rajada de 1.000 eventos em duas camadas -> UMA chamada com as duas camadas
const chamadas = [];
const viva = assinarCamadas(['c1', 'c2'], (lote) => chamadas.push([...lote].sort()), {{ atrasoMs: 40 }});
const fonte = FonteFalsa.ultima;
saida.url = fonte.url;
fonte.emitir('pronto', {{ camadas: ['c1', 'c2'] }});
for (let i = 0; i < 1000; i++) fonte.emitir('camada', {{ camada: i % 2 ? 'c1' : 'c2', versao: i }});
saida.chamadas_imediatas = chamadas.length;

// 2. fluxo que nunca abre -> aoIndisponivel UMA vez
let indisponivel = 0;
assinarCamadas(['c3'], () => {{}}, {{ atrasoMs: 40, aoIndisponivel: () => {{ indisponivel += 1; }} }});
const morta = FonteFalsa.ultima;
morta.emitir('error');
morta.emitir('error');
saida.indisponivel = indisponivel;

// 3. sem camada nenhuma -> indisponível na hora, sem abrir conexão
let semCamada = 0;
const vazia = assinarCamadas([], () => {{}}, {{ aoIndisponivel: () => {{ semCamada += 1; }} }});
saida.sem_camada = semCamada;
saida.sem_camada_disponivel = vazia.disponivel();

saida.hora = horaCurta(new Date(2026, 8, 8, 7, 5, 9));

setTimeout(() => {{
  saida.chamadas = chamadas;
  saida.viva_disponivel = viva.disponivel();
  viva.fechar();
  saida.fechada = fonte.fechada === true;
  process.stdout.write(JSON.stringify(saida));
}}, 250);
"""


@pytest.fixture(scope="module")
def resultado(tmp_path_factory):
    if not MODULO.exists():
        pytest.skip("web/js/vivo/assinatura.js ausente")
    arq = tmp_path_factory.mktemp("vivo") / "roteiro.mjs"
    arq.write_text(ROTEIRO.format(modulo=MODULO), encoding="utf-8")
    try:
        r = subprocess.run(["node", str(arq)], capture_output=True, text=True, timeout=30, check=True)
    except FileNotFoundError:
        pytest.skip("node não instalado nesta máquina")
    return json.loads(r.stdout)


def test_rajada_de_mil_eventos_vira_uma_chamada_so(resultado):
    assert resultado["chamadas_imediatas"] == 0, "chamou antes de fechar a janela de coalescência"
    assert resultado["chamadas"] == [["c1", "c2"]], resultado["chamadas"]


def test_url_assinada_traz_as_camadas_pedidas(resultado):
    assert resultado["url"] == "/api/eventos/camadas?camadas=c1,c2"


def test_fluxo_que_nao_abre_avisa_uma_vez_so(resultado):
    assert resultado["indisponivel"] == 1, resultado["indisponivel"]


def test_sem_camada_nao_abre_conexao(resultado):
    assert resultado["sem_camada"] == 1 and resultado["sem_camada_disponivel"] is False


def test_assinatura_viva_e_fechavel(resultado):
    assert resultado["viva_disponivel"] is True
    assert resultado["fechada"] is True


def test_hora_curta_tem_hora_minuto_e_segundo(resultado):
    assert resultado["hora"] == "07:05:09", resultado["hora"]
