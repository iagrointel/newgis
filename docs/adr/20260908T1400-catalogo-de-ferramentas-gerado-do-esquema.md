# ADR 20260908T1400 — catálogo de ferramentas gerado do esquema de parâmetros (UX-09)

## Contexto

O item UX-09 pede que toda ferramenta e toda tarefa sejam alcançáveis por uma tela com controle e estados. O
backend já publica o registro de tipos de tarefa (`GET /api/jobs/tipos`: nome, descrição, custo, perfil mínimo e o
JSON Schema dos parâmetros gerado do modelo pydantic de cada tipo). A tela `/tarefas` mostra o que já rodou; não
havia lugar para ESCOLHER uma ferramenta e executá-la com parâmetros. As ferramentas de geoprocessamento no
vocabulário Esri (GPServer, L2-05-a) não existem no tronco nem em ramo da fila.

## Decisão

1. `/ferramentas` é o catálogo dos tipos de tarefa que não são `somente_sistema`, em cartões agrupados pelo prefixo
   do nome (catalogo, conexoes, exportacao, ingestao, uploads, jobs, prova), com o custo declarado em texto
   (memória, tempo máximo, pesada, executor, perfil mínimo) e o número de parâmetros. As de diagnóstico
   (`prova.*`, `jobs.*`) só aparecem com o filtro ligado; abrir uma delas pela URL liga o filtro.
2. O formulário nasce do esquema, sem formulário escrito à mão por ferramenta: `integer`/`number` viram campo
   numérico com `min`/`max`/`step`; `enum` vira seleção; `boolean` vira caixa; `array` vira lista (um valor por
   linha); `object` vira área JSON; `format: uuid` e `date-time` ganham validação; `required` e `default` do
   esquema valem. O rótulo é o NOME do parâmetro (o que a API recebe); a descrição e os limites vão na ajuda.
3. Validação em duas camadas: o navegador recusa antes de chamar (limite, inteiro, uuid, JSON, padrão) com o
   motivo no campo; o 422 do serviço (`detalhe: [{campo, mensagem}]`, app/jobs/servico.py) volta ao campo
   nomeado. Nunca 422 cru na tela.
4. Executar = `POST /api/jobs {tipo, parametros}`; a execução aparece no mesmo painel com o canal de eventos da
   tela Tarefas (`web/js/jobs/eventos.js`: SSE com reserva por polling), barra de progresso, log, cancelar
   enquanto roda, ligação para `/tarefas/<id>` e, quando o resultado traz `item_id`, para o item no catálogo.
5. Sem privilégio `jobs.executar` a tela cai na página "sem permissão" de `exigirSessao`, e a entrada some da
   barra lateral. Perfil mínimo acima do do usuário mostra estado "negado" no formulário, sem botão executar.

## Consequências

- Todo tipo de tarefa novo ganha tela no mesmo instante em que declara o modelo de parâmetros; o esquema é o
  contrato de interface. Tipo sem descrição aparece com o nome, o que é feio e serve de lembrete.
- O gerador cobre os tipos do JSON Schema que os modelos de hoje usam; `anyOf` além de "X ou null" e objetos
  aninhados caem na área JSON — funcional, não bonito. Quando um tipo precisar de seletor de item (uuid), a
  entrada é texto validado; um seletor com busca no catálogo fica como evolução.
- As ferramentas GP Esri (L2-05-a) continuam fora: quando entrarem, o manifesto delas cabe no mesmo gerador
  (parâmetros com tipo, limites e padrão), e a tela lista os dois registros lado a lado.
