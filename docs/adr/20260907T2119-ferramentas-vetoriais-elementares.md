# ADR — ferramentas vetoriais elementares em SQL/PostGIS (item L2-05-b)

Data: setembro de 2026. Situação: aceita.

## Contexto

O item L2-05-a deixou pronta a infraestrutura de ferramenta: registro por decorador com manifesto no
vocabulário GP da Esri, validação de parâmetro, execução em processo abaixo do custo declarado ou como job,
publicação do resultado como item de camada com proveniência e `derivado_de`, e a fachada GPServer. Faltava
o conteúdo: as operações vetoriais que o usuário do Map Viewer espera encontrar em "Manage data" e
"Use proximity".

## Decisão

1. **Tudo em SQL, nada em Python.** Cada ferramenta monta um `SELECT` e o executor faz `CREATE TABLE AS`.
   Nenhuma geometria trafega pelo processo da aplicação: o custo de memória de uma camada de 2 milhões de
   feições fica no banco, que é onde há índice espacial. É também o que torna o teto de feições uma decisão
   de admissão (conferida antes de operar) e não uma corrida contra o coletor de lixo do Python.
2. **Geodésico por padrão.** Distância de buffer, área, perímetro, comprimento e intervalo de densificação
   saem de `geography` (elipsoide WGS 84). Grau quadrado não é área. `buffer` aceita `metodo=plano`, e nesse
   caso recusa camada geográfica em vez de devolver um número sem unidade.
3. **48 segmentos por quarto de círculo no buffer.** O padrão do PostGIS (8) inscreve um polígono de 32 lados
   cuja área fica 0,64 % abaixo do círculo — mais do que os 0,05 % que o portão do item aceita. Com 48 o
   desvio medido contra a referência `pyproj.Geod` é 5,0e-5 (`tests/medidas/L2-05-b-vetor-basico.json`).
4. **Regra da casa aplicada dentro da expressão, não numa etapa de limpeza.** Toda operação booleana em massa
   (recorte, interseção, união, diferença, diferença simétrica, dissolver e o anel do buffer) recebe
   `ST_ReducePrecision(ST_MakeValid(geom), grade)`. A grade é 1e-11 grau (≈ 1 µm) ou 1e-6 m: serve contra a
   exceção topológica do GEOS, não para generalizar. Não existe passo separado de "consertar a camada", que
   deixaria a camada de entrada alterada.
5. **Relatório de inválidas na procedência.** A contagem de geometrias inválidas de cada entrada vai para o
   log da execução e para o texto do método gravado no item de saída. Quem abrir a ficha da camada derivada
   lê que houve conserto e em qual entrada.
6. **Sem ferramenta nova fora do registro.** As 19 são declaradas com o mesmo decorador `@ferramenta`; quem
   quiser a lista, o esquema JSON do formulário, o descritor GPServer ou o custo estimado usa o mesmo caminho
   do item-pai. Não há segundo mecanismo.
7. **Entrada de camadas em lista.** `mesclar` recebe `GPMultiValue:GPFeatureRecordSetLayer`. Para isso o
   executor passou a resolver lista de camadas e a achatar (`entradas_planas`) na hora de escrever
   proveniência e `derivado_de`: a camada mesclada aponta para TODAS as suas origens.

## Consequências

- Área e contagem batem com shapely/geopandas na mesma entrada, e as medidas geodésicas com `pyproj.Geod`
  (é assim que os testes conferem — nenhum número esperado é escrito à mão).
- Quem precisar de uma ferramenta que o PostGIS não tenha (interpolação, rede, raster) não vai encaixá-la
  aqui: este módulo é explicitamente o que sai de uma expressão SQL.
- O teto de 2 milhões de feições por entrada e o de 30 minutos por execução são limites declarados no
  manifesto, visíveis na API. Acima disso a ferramenta recusa, nomeando o campo.
