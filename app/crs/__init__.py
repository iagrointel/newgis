"""Sistema de referência (CRS) como serviço transversal (item L2-17-crs-transformacoes; ADR 0018-crs).

Nenhuma tabela `plat.*` própria (mesmo padrão de `app/rede`, L2-11-c): o registro de CRS vem do banco
EPSG embutido no PROJ da máquina (`pyproj`, PROJ 9.4.0) mais uma lista curada brasileira; a transformação
de datum legado usa as grades NTv2 do IBGE vendorizadas em `grades_ibge/`. Ver `app/crs/registro.py`
(lista), `app/crs/grades.py` (grades e escolha por área) e `app/crs/servico.py` (transformação)."""
