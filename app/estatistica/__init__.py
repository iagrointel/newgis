"""Classificação numérica calculada no servidor (item L2-02-b-classificacao-servidor, ADR
ver docs/adr/). Nunca no navegador com amostra: todo corte é calculado aqui, sobre a coluna inteira
(ou sobre uma amostra estratificada DECLARADA na resposta quando o volume passa de 1 milhão de
valores não nulos)."""
