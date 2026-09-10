# Versão da plataforma sem chave nenhuma (GET /api/versao, escopo publico)
from _apoio import chamar, exigir

status, _cab, corpo = chamar("/api/versao", chave="")
exigir(status == 200, f"esperava 200 em /api/versao, veio {status}")
exigir("versao" in corpo, f"resposta sem o campo versao: {corpo}")
print(f"plat versao {corpo['versao']}")
