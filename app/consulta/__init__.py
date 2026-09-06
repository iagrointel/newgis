"""Consultas de camada seguras contra SQL de usuário (item L2-04-b, dependência de L2-04-servicos-esri-ogc
e de L7-03-d-injecao-consulta). `where_ast` é o único gerador de SQL parametrizado a partir de filtro
digitado por cliente — nenhuma outra rota deve montar `WHERE` por concatenação."""

from app.consulta.where_ast import ConsultaSQL, ErroWhere, analisar, compilar, compilar_where

__all__ = ["ConsultaSQL", "ErroWhere", "analisar", "compilar", "compilar_where"]
