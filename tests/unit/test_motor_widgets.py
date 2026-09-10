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
    assert {"mapa", "legenda", "tabela", "texto", "botao", "filtro"} <= {item["nome"] for item in resultado}
    # plat-w-: não colide com os componentes do sistema de design (plat-tabela, plat-tema, plat-idioma)
    assert all(item["elemento"] == f"plat-w-{item['nome']}" for item in resultado)
    assert all(isinstance(item["eventos"], list) and isinstance(item["acoes"], list) for item in resultado)


def test_configuracao_fora_do_esquema_nomeia_widget_e_campo():
    resultado = executar_js("""
      import { obterManifesto, validarEsquema } from './web/js/widgets/registro.js';
      try {
        validarEsquema({texto: 'certo', html: '<script>'}, obterManifesto('texto').esquema_config,
                       'widget.texto.configuracao');
      } catch (erro) { console.log(JSON.stringify({mensagem: erro.message})); }
    """)
    assert resultado["mensagem"] == "widget.texto.configuracao.html: campo desconhecido"


def test_inteiro_aceita_numero_inteiro_e_recusa_fracao():
    resultado = executar_js("""
      import { obterManifesto, validarEsquema } from './web/js/widgets/registro.js';
      const esquema = obterManifesto('texto').esquema_config;
      const casos = {um: 1, seis: 6, fracao: 1.5, sete: 7, texto: '1'};
      const saida = {};
      for (const [nome, nivel] of Object.entries(casos)) {
        try { validarEsquema({texto: 'x', nivel}, esquema, 'c'); saida[nome] = null; }
        catch (erro) { saida[nome] = erro.message; }
      }
      console.log(JSON.stringify(saida));
    """)
    assert resultado == {
        "um": None, "seis": None,
        "fracao": "c.nivel: esperado inteiro",
        "sete": "c.nivel: máximo 6",
        "texto": "c.nivel: esperado integer, recebido string",
    }


def test_modulos_de_widget_ficam_abaixo_de_60_kb():
    for arquivo in (ROOT / "web/js/widgets").glob("*.js"):
        if arquivo.name in {"registro.js", "motor.js", "base.js", "aplicativo.js"}:
            continue
        assert arquivo.stat().st_size <= 60 * 1024, arquivo


def test_manifesto_invalido_e_recusado_com_o_campo_nomeado():
    resultado = executar_js("""
      import { validarManifesto, obterManifesto } from './web/js/widgets/registro.js';
      const base = obterManifesto('botao');
      const casos = {
        sem_esquema: (() => { const m = {...base}; delete m.esquema_config; return m; })(),
        elemento_sem_prefixo: {...base, elemento: 'botao'},
        api_incompativel: {...base, api_widget: 2},
        fontes_invertidas: {...base, fontes: {min: 2, max: 1, tipos: []}},
        modulo_absoluto: {...base, modulo: 'https://exemplo.invalido/x.js'},
      };
      const saida = {};
      for (const [nome, m] of Object.entries(casos)) {
        try { validarManifesto(m); saida[nome] = null; } catch (erro) { saida[nome] = erro.message; }
      }
      console.log(JSON.stringify(saida));
    """)
    assert resultado == {
        "sem_esquema": "manifesto.esquema_config: campo obrigatório",
        "elemento_sem_prefixo": "manifesto.elemento: Custom Element inválido",
        "api_incompativel": "manifesto.api_widget: versão de API incompatível",
        "fontes_invertidas": "manifesto.fontes: limites inválidos",
        "modulo_absoluto": "manifesto.modulo: módulo relativo inválido",
    }
