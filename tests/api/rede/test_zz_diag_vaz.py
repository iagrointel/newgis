import json as J
import uuid as U

from tests.api.rede.test_isolamento_por_inquilino import rede_b_com_topologia
from app.rede_utilidades import instalados


def _esquemas():
    from app.main import app
    return app.openapi()


def _min_do_esquema(esq, comps, prof=0):
    if prof > 6 or not isinstance(esq, dict):
        return None
    if "$ref" in esq:
        nome = esq["$ref"].rsplit("/", 1)[-1]
        return _min_do_esquema(comps.get(nome, {}), comps, prof + 1)
    for chave in ("anyOf", "oneOf", "allOf"):
        if chave in esq:
            for alt in esq[chave]:
                if not (isinstance(alt, dict) and alt.get("type") == "null"):
                    return _min_do_esquema(alt, comps, prof + 1)
    if "default" in esq:
        return esq["default"]
    if "enum" in esq and esq["enum"]:
        return esq["enum"][0]
    t = esq.get("type")
    if t == "object" or ("properties" in esq):
        obj = {}
        props = esq.get("properties", {})
        for nome in esq.get("required", []):
            obj[nome] = _min_do_esquema(props.get(nome, {}), comps, prof + 1)
        return obj
    if t == "array":
        mn = esq.get("minItems", 0)
        if mn:
            return [_min_do_esquema(esq.get("items", {}), comps, prof + 1) for _ in range(mn)]
        return []
    if t == "integer":
        return max(int(esq.get("minimum", 1)), 1)
    if t == "number":
        return float(max(esq.get("minimum", 1), 1))
    if t == "boolean":
        return False
    if t == "string":
        if esq.get("format") == "uuid":
            return str(U.uuid4())
        return "x" * max(int(esq.get("minLength", 1)), 1)
    return None


def test_diag(sessao_a, rede_b_com_topologia):
    alvo = rede_b_com_topologia
    esq = _esquemas()
    comps = esq.get("components", {}).get("schemas", {})
    linhas = []
    for caminho, ops in sorted(esq["paths"].items()):
        if not caminho.startswith("/api/rede"):
            continue
        for metodo, op in sorted(ops.items()):
            metodo = metodo.upper()
            url = caminho.replace("{rede_id}", alvo["rede_id"])
            # qualquer outro marcador vira uuid aleatorio (nunca dado de A)
            while "{" in url:
                ini = url.index("{"); fim = url.index("}", ini)
                url = url[:ini] + str(U.uuid4()) + url[fim + 1:]
            # parametros de consulta obrigatorios
            q = {}
            for p in op.get("parameters", []):
                if p.get("in") == "query" and p.get("required"):
                    v = _min_do_esquema(p.get("schema", {}), comps)
                    q[p["name"]] = alvo["no_id"] if p["name"] == "no" else v
            corpo = None
            rb = op.get("requestBody")
            if rb:
                ct = rb.get("content", {})
                if "application/json" in ct:
                    corpo = _min_do_esquema(ct["application/json"].get("schema", {}), comps)
            if caminho.endswith("/pacote") and metodo == "POST":
                r = sessao_a.request(metodo, url, params=q, content=instalados.bruto("eletrica-br"),
                                     headers={"Content-Type": "application/json"})
            else:
                r = sessao_a.request(metodo, url, params=q, json=corpo)
            alvo_na_url = "{rede_id}" in caminho
            try:
                d = J.loads(r.text); inst = d.pop("instance", None); resto = J.dumps(d)
            except Exception:
                inst = None; resto = r.text
            marcas = [m for m, v in (("REDEID", alvo["rede_id"]), ("NOID", alvo["no_id"]), ("NOME_B", "l423-alvo-b")) if v in resto]
            ok = (r.status_code in (403, 404)) if alvo_na_url else True
            linhas.append(f"{'OK ' if ok and not marcas else 'RUIM'} {r.status_code:>3} {metodo:<6} {caminho:<58} alvoB={alvo_na_url!s:<5} vaz={','.join(marcas) or '-'}")
    print("\n===DIAG===")
    print("\n".join(l for l in linhas if l.startswith("RUIM")) or "(nenhuma RUIM)")
    print(f"--- total {len(linhas)}, ruins {sum(1 for l in linhas if l.startswith('RUIM'))}")
    print("===FIM===")
