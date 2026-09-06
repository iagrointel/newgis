# Prova de que uma chave de leitura NÃO escreve: POST /api/itens exige o escopo admin:inquilino
from _apoio import chamar, exigir, exigir_chave

exigir_chave()
status, _cab, corpo = chamar("/api/itens", metodo="POST", corpo={"tipo": "pasta", "titulo": "não deve ser criado"})
exigir(status == 403, f"esperava 403 (escopo insuficiente) e veio {status}: {corpo}")
exigir(corpo.get("erro") == "escopo_insuficiente", f"esperava erro escopo_insuficiente, veio {corpo.get('erro')}")
print(f"recusado como se espera: {corpo['mensagem']}")
print(f"exigido: {corpo['detalhe']['exigido']}; a chave tem: {', '.join(corpo['detalhe']['token_tem'])}")
