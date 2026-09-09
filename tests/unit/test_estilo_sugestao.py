"""Sugestões do editor de simbologia (item L2-02-c), função pura em web/js/mapa/estilo_sugestao.js executada no
node: categorias com mais de 200 valores distintos viram 200 categorias + `outros`; classes nascem dos cortes do
servidor (L2-02-b) sem inventar limite; rampas ColorBrewer interpolam fora dos passos publicados e invertem."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def executar_js(codigo: str):
    processo = subprocess.run(["node", "--input-type=module", "-e", codigo], cwd=ROOT, text=True,
                              capture_output=True, check=True)
    return json.loads(processo.stdout)


CABECALHO = """
  import { createRequire } from 'node:module';
  const require = createRequire(import.meta.url);
  const cb = require('./web/vendor/colorbrewer-1.7.0.js');
  const s = await import('./web/js/mapa/estilo_sugestao.js');
"""


def test_mais_de_200_valores_viram_200_categorias_e_outros():
    r = executar_js(CABECALHO + """
      const valores = Array.from({length: 350}, (_, i) => `v${i}`);
      const paleta = s.cores(cb, 'Set3', 12);
      const r = s.sugerirCategorias({valores, total_distintos: 350, truncado: true}, paleta);
      console.log(JSON.stringify({n: r.categorias.length, outros: r.outros, ultimo: r.categorias[199].valor,
        primeira_cor: r.categorias[0].cor, agrupados: r.agrupados_em_outros}));
    """)
    assert r["n"] == 200 and r["ultimo"] == "v199" and r["agrupados"] == 150
    assert r["outros"] == {"cor": "#9a9a9a", "rotulo": "outros (150 valores)", "visivel": True}
    assert r["primeira_cor"].startswith("#")


def test_ate_200_valores_nao_tem_outros():
    r = executar_js(CABECALHO + """
      const r = s.sugerirCategorias({valores: ['a', 'b'], total_distintos: 2}, s.cores(cb, 'Set1', 3));
      console.log(JSON.stringify(r));
    """)
    assert r["outros"] is None and [c["valor"] for c in r["categorias"]] == ["a", "b"]


def test_classes_saem_dos_cortes_do_servidor_com_tamanho_opcional():
    r = executar_js(CABECALHO + """
      const paleta = s.cores(cb, 'YlGn', 4);
      console.log(JSON.stringify({cor: s.sugerirClasses([0, 10, 20, 50, 100], paleta),
        tam: s.sugerirClasses([0, 10, 20], paleta, [2, 10]), vazio: s.sugerirClasses([5], paleta)}));
    """)
    assert [(c["min"], c["max"]) for c in r["cor"]] == [(0, 10), (10, 20), (20, 50), (50, 100)]
    assert all("tamanho" not in c for c in r["cor"])
    assert [c["tamanho"] for c in r["tam"]] == [2, 10] and r["vazio"] == []


def test_rampa_colorbrewer_interpola_e_inverte():
    r = executar_js(CABECALHO + """
      console.log(JSON.stringify({cinco: s.cores(cb, 'Blues', 5), doze: s.cores(cb, 'Blues', 12).length,
        dois: s.cores(cb, 'Blues', 2), inv: s.cores(cb, 'Blues', 3, true), ref: cb.Blues[3]}));
    """)
    referencia = executar_js(CABECALHO + "console.log(JSON.stringify(cb.Blues[5]));")
    assert r["cinco"] == referencia
    assert r["doze"] == 12 and len(r["dois"]) == 2 and r["inv"] == list(reversed(r["ref"]))


def test_normalizar_tira_as_chaves_do_editor_e_garante_campos():
    r = executar_js(CABECALHO + """
      console.log(JSON.stringify(s.normalizar({tipo: 'classes', n_classes: 5, classes_de_tamanho: true, campo: 'v',
        classes: [], rampa: null, escala_min: undefined}, ['v', 'w'])));
    """)
    assert r == {"tipo": "classes", "campo": "v", "classes": [], "campos": ["v", "w"]}
