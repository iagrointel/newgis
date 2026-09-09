"""Verificação do SDK de widget externo que roda no `make check` (item L5-36).

* o pacote de exemplo da casa (web/ext/exemplo/semaforo) passa no validarManifesto do NAVEGADOR
  (registro.js) com node — as regras são as mesmas da instalação (app/widgets/modelos.py), e os dois
  lados precisam continuar falando a mesma língua;
* api_widget diferente de 1 é RECUSADO nomeando o widget — a acusação de API antiga (o parceiro que
  empacota contra outra versão descobre na instalação, não num console em branco);
* o empacotador (scripts/widget_empacotar.py) devolve exatamente os arquivos da pasta.
"""

import json
import subprocess
from pathlib import Path

import pytest

from scripts.widget_empacotar import empacotar

ROOT = Path(__file__).resolve().parents[2]
EXEMPLO = ROOT / "web" / "ext" / "exemplo" / "semaforo"


def _js_disponivel() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):  # pragma: não coberto (node presente na bancada)
        return False


@pytest.mark.skipif(not _js_disponivel(), reason="node ausente nesta máquina")
def test_pacote_exemplo_passa_no_validar_manifesto_do_navegador():
    script = f"""
    import {{ validarManifesto, REGISTRO }} from 'file://{ROOT}/web/js/widgets/registro.js';
    const pacote = JSON.parse({json.dumps((EXEMPLO / "manifesto.json").read_text(encoding="utf-8"))});
    validarManifesto(pacote);
    if (pacote.api_widget !== 1) throw new Error('exemplo deveria declarar api_widget 1');
    if (!REGISTRO.has('mapa')) throw new Error('registro da casa sumiu');
    console.log('ok');
    """
    r = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (EXEMPLO / "semaforo.js").exists()
    assert (EXEMPLO / "i18n.json").exists()
    i18n = json.loads((EXEMPLO / "i18n.json").read_text(encoding="utf-8"))
    assert all(chave.startswith("widget.semaforo.") for chave in i18n), "chave fora do namespace do widget"


@pytest.mark.skipif(not _js_disponivel(), reason="node ausente nesta máquina")
def test_api_widget_antiga_e_acusada_nomeando_o_widget():
    antigo = {
        "nome": "quadro-antigo", "versao": "0.9.0", "api_widget": 2, "modulo": "./quadro.js",
        "elemento": "plat-quadro-antigo", "esquema_config": {"type": "object"},
        "eventos": [], "acoes": [], "fontes": {"min": 0, "max": 0, "tipos": []},
        "i18n": "widget.quadro-antigo",
    }
    script = f"""
    import {{ validarManifesto }} from 'file://{ROOT}/web/js/widgets/registro.js';
    const manifesto = JSON.parse({json.dumps(json.dumps(antigo))});
    try {{ validarManifesto(manifesto); }}
    catch (erro) {{
      if (!/api_widget/.test(erro.message)) throw new Error('acusação não nomeia a API: ' + erro.message);
      console.log('recusado');
      process.exit(0);
    }}
    throw new Error('manifesto com api_widget=2 passou no validarManifesto — recusa sumiu');
    """
    r = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "recusado" in r.stdout


def test_empacotador_devolve_os_arquivos_da_pasta():
    pacote = empacotar(EXEMPLO)
    manifesto = json.loads((EXEMPLO / "manifesto.json").read_text(encoding="utf-8"))
    assert pacote["manifesto"] == manifesto
    assert pacote["modulo"] == (EXEMPLO / "semaforo.js").read_text(encoding="utf-8")
    assert pacote["i18n"] == json.loads((EXEMPLO / "i18n.json").read_text(encoding="utf-8"))
    assert pacote["sandbox"] is True  # manifesto do exemplo declara sandbox


def test_empacotador_recusa_modulo_fora_da_forma_relativa(tmp_path):
    (tmp_path / "manifesto.json").write_text(json.dumps({
        "nome": "ruim", "versao": "1.0.0", "api_widget": 1, "modulo": "https://outro.host/x.js",
        "elemento": "plat-ruim", "esquema_config": {}, "eventos": [], "acoes": [],
        "fontes": {"min": 0, "max": 0, "tipos": []}, "i18n": "widget.ruim",
    }), encoding="utf-8")
    with pytest.raises(SystemExit, match="\\./<arquivo>\\.js"):
        empacotar(tmp_path)
