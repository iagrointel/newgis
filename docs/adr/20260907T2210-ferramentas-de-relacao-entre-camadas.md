# ADR 20260907T2210 — ferramentas de relação entre camadas (item L2-05-c)

Estado: aceito. Contexto: L2-05-a deu o registro e o executor; L2-05-b deu as 19 ferramentas de uma camada só.
Falta o que relaciona DUAS camadas — junção, resumo dentro e perto, agregação em polígono ou grade, vizinho e
tabela de distâncias.

## Decisões

1. **Módulo novo, registro velho.** `app/ferramentas/relacao.py` registra pelo mesmo decorador e roda pelo mesmo
   executor. Nada de caminho paralelo: proveniência, `derivado_de`, custo e limites saem de graça.
2. **Par candidato por índice, medida na geometria original.** Toda ferramenta que cruza duas camadas monta
   primeiro `pares(pfid, ofid)` com o predicado grosseiro sobre a camada de polígonos passada por
   `ST_Subdivide`, com `DISTINCT`; a relação pedida e a medida são reconferidas contra a geometria original.
   Alternativa recusada: subdividir também para medir (contaria a mesma feição em cada parte).
   Medido em base de trilha: 400 polígonos × 4.000 pontos, plano com `Index Scan` no índice GiST dos pontos,
   245 ms de execução da consulta.
3. **Contagem dupla é declarada, não escondida.** O comportamento padrão é o do ArcGIS (a feição entra em cada
   polígono que a contém), mas o número de feições repetidas vai para o texto do método na procedência, e
   `atribuicao='exclusivo'` desfaz. Alternativa recusada: deduplicar por padrão — mudaria o resultado que o
   usuário de ArcGIS espera, sem ele pedir.
4. **Grade desenhada em metros, não em graus.** `agregar_pontos` sem camada de polígonos gera `ST_SquareGrid` /
   `ST_HexagonGrid` no UTM WGS 84 do centro da camada e traz o resultado de volta ao SRID dela. Alternativa
   recusada: converter o lado para graus por uma constante — a célula sairia achatada conforme a latitude.
   Limite: `GRADE_CELULAS_MAX`, conferido antes de desenhar, com erro nomeado.
5. **Junção espacial e junção por atributo são duas ferramentas.** O Map Viewer junta pelos dois critérios na
   mesma; separar deixa o esquema JSON de cada uma pequeno o bastante para o formulário se gerar sozinho.
6. **`resumir_perto` só em linha reta.** O modo por tempo ou distância de rota depende do motor de roteamento
   (L2-11) e não entrou nem como opção do parâmetro: opção que sempre devolve erro é promessa falsa no
   formulário. Quando o L2-11 existir, entra como parâmetro novo e versão 2 da ferramenta.
7. **Campo distribuído sai com prefixo `origem_`.** A camada de destino pode ter campo de mesmo nome; prefixo
   fixo evita a colisão sem regra condicional que o usuário teria de adivinhar.

## Consequências

- Nove ferramentas novas no catálogo, todas com teste contra `geopandas`/`pandas`/`shapely`/`pyproj` na mesma
  entrada (25 testes em `tests/api/ferramentas/test_relacao.py`).
- `app/ferramentas/rotas.py` ganha uma linha de importação; nada mais do caminho comum muda.
- A cláusula de desempenho do portão (1 milhão de pontos em 5.570 municípios em até 60 s) NÃO foi medida na
  escala do enunciado: a máquina da trilha está com disco a 93 % e carga acima de 8, e o brief da corrida
  limita o teste a 5 mil feições. O que ficou medido está em `tests/medidas/L2-05-c-sobreposicao-agregacao.json`
  com a carga ao lado.
