"""Grades aninhadas do motor multicritério (item L3-19-multiescala).

Triagem regional numa grade MACRO, estudo fino numa grade MICRO gerada só dentro das regiões aprovadas no
macro. O módulo `crs` resolve o CRS de trabalho (UTM SIRGAS 2000 da zona do centróide, decisão A7 de
laco/decomposicao/L3L6_CONCEITO.md), o `motor` gera as grades e executa, e `rotas` publica /api/multiescala.
"""
