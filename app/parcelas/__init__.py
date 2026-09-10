"""Malha de parcelas (item L4-parcelas-01-modelo-de-parcelas).

Modelo orientado a REGISTRO (paridade com o parcel fabric: docs/PARIDADE_PARCELAS.md): o
registro é o documento legal (matrícula, escritura, loteamento, desmembramento,
remembramento, aprovação) que CRIA e RETIRA parcelas, linhas, pontos e conexões; a feição
retirada não se apaga — ganha retirada_por_registro e sai do 'atual' para o 'histórico'.
Regra da casa: parcela ≠ gleba ≠ lote ≠ matrícula; SIGEF/CAR é camada de referência, nunca
parcela oficial; nenhuma matrícula real e nenhum nome.
"""
