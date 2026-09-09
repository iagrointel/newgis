#!/usr/bin/env python3
"""Empacota uma pasta de widget externo (L5-36) no envelope JSON do POST /api/widgets/externos.

Pasta do widget (web/ext/<inquilino>/<widget>/):
  manifesto.json   — o manifesto (mesmo esquema validado por app/widgets/modelos.py e registro.js)
  <modulo>.js      — o código, apontado por manifesto.modulo na forma ./<arquivo>.js
  i18n.json        — opcional; chaves todas sob o prefixo manifesto.i18n

Uso: python3 scripts/widget_empacotar.py web/ext/exemplo/semaforo > pacote.json
Depois: curl -b cookies.txt -H 'Content-Type: application/json' --data @pacote.json \\
        https://<host>/api/widgets/externos
Só biblioteca padrão. O sha256 do módulo é calculado pelo servidor na instalação e volta na listagem —
o navegador reconfere antes de o código correr.
"""

import json
import sys
from pathlib import Path


def empacotar(pasta: str) -> dict:
    pasta = Path(pasta)
    manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    caminho_modulo = manifesto.get("modulo", "")
    if not caminho_modulo.startswith("./"):
        raise SystemExit(f"manifesto.modulo precisa ser ./<arquivo>.js (é {caminho_modulo!r})")
    modulo = (pasta / Path(caminho_modulo).name).read_text(encoding="utf-8")
    arquivo_i18n = pasta / "i18n.json"
    i18n = json.loads(arquivo_i18n.read_text(encoding="utf-8")) if arquivo_i18n.exists() else {}
    pacote = {"manifesto": manifesto, "modulo": modulo, "sandbox": bool(manifesto.get("sandbox", False))}
    if i18n:
        pacote["i18n"] = i18n
    return pacote


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("uso: widget_empacotar.py <pasta-do-widget>  (imprime o envelope JSON)")
    json.dump(empacotar(sys.argv[1]), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
