import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def executar_js(codigo: str):
    processo = subprocess.run(
        ["node", "--experimental-default-type=module", "--input-type=module", "-e", codigo],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(processo.stdout)


def test_registro_declara_seis_widgets_com_contrato_valido():
    resultado = executar_js("""
      import { REGISTRO, validarManifesto } from './web/js/widgets/registro.js';
      const nomes = [...REGISTRO.values()].map((m) => {
        validarManifesto(m);
        return {nome: m.nome, elemento: m.elemento, eventos: m.eventos, acoes: m.acoes};
      });
      console.log(JSON.stringify(nomes));
    """)
    assert {item["nome"] for item in resultado} == {"mapa", "legenda", "tabela", "texto", "botao", "filtro"}
    assert all(item["elemento"] == f"plat-{item['nome']}" for item in resultado)
    assert all(isinstance(item["eventos"], list) and isinstance(item["acoes"], list) for item in resultado)


def test_configuracao_fora_do_esquema_nomeia_widget_e_campo():
    resultado = executar_js("""
      import { obterManifesto, validarEsquema } from './web/js/widgets/registro.js';
      try {
        validarEsquema({texto: 'certo', html: '<script>'}, obterManifesto('texto').esquema_config, 'widget.texto.configuracao');
      } catch (erro) { console.log(JSON.stringify({mensagem: erro.message})); }
    """)
    assert resultado["mensagem"] == "widget.texto.configuracao.html: campo desconhecido"


def test_modulos_de_widget_ficam_abaixo_de_60_kb():
    for arquivo in (ROOT / "web/js/widgets").glob("*.js"):
        if arquivo.name in {"registro.js", "motor.js", "base.js", "aplicativo.js"}:
            continue
        assert arquivo.stat().st_size <= 60 * 1024, arquivo
