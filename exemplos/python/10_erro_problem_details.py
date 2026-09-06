# Formato de erro da API: RFC 9457 (application/problem+json) com os campos da casa junto
from _apoio import chamar, exigir

status, cabecalhos, corpo = chamar("/api/eu", chave="plat_" + "z" * 43)
exigir(status == 401, f"esperava 401 com chave inválida, veio {status}: {corpo}")
tipo = cabecalhos.get("Content-Type", cabecalhos.get("content-type", ""))
exigir("application/problem+json" in tipo, f"esperava application/problem+json, veio {tipo!r}")
for campo in ("type", "title", "status", "detail", "instance", "erro", "mensagem", "req_id"):
    exigir(campo in corpo, f"Problem Details sem o campo {campo}: {sorted(corpo)}")
exigir(corpo["status"] == 401, f"campo status divergente do HTTP: {corpo['status']} != 401")
print(f"{corpo['type']} -> {corpo['detail']} (req_id {corpo['req_id']})")
