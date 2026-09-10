# Quem é o dono da chave e que escopos ela tem (GET /api/eu, escopo token:qualquer)
from _apoio import chamar, exigir, exigir_chave

exigir_chave()
status, _cab, corpo = chamar("/api/eu")
exigir(status == 200, f"esperava 200 em /api/eu, veio {status}: {corpo}")
exigir(corpo.get("token"), "a resposta não traz o bloco token: a credencial usada foi sessão, não chave")
escopos = corpo["token"]["escopos"]
print(f"chave {corpo['token']['nome']!r} do usuário {corpo['login']} no inquilino {corpo['inquilino']['slug']}")
print(f"escopos: {', '.join(escopos)}")
print(f"expira em: {corpo['token']['expira_em']}")
