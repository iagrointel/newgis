"""Acrescenta uma medida de remedicao a tests/medidas/<id>.json sem apagar as que ja existem."""
import json, subprocess, sys, datetime, pathlib
item, chave, valor, unidade, comando = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
p = pathlib.Path("tests/medidas") / f"{item}.json"
d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"item": item, "medidas": {}}
d.setdefault("medidas", {})
try:
    v = int(valor)
except ValueError:
    try:
        v = float(valor)
    except ValueError:
        v = valor
d["medidas"][chave] = {"valor": v, "unidade": unidade, "comando": comando}
d["gerado_em"] = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
d["git_sha"] = subprocess.check_output(["git", "rev-parse", "--short=12", "HEAD"], text=True).strip()
p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(p)
