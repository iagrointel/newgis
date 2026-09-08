# Configuração de traçado: documento salvo, nunca segundo motor

Item `L4-02-e-configuracoes-de-tracado`. Setembro de 2026.

## Contexto

Os traçados já construídos (conectado e subrede em `tracado.py`; montante e jusante em `direcao.py`; laços,
caminho curto e isolados em `lacos.py`) atendem um pedido por vez, escrito no corpo da chamada. Quem opera
uma rede repete os mesmos pedidos todo dia — "quantos clientes a jusante", "quanto kVA a jusante", "o que a
próxima chave fusível isola" — e hoje precisa reescrever o pedido a cada vez, sem nome e sem como
compartilhar com a equipe. É o que a Esri resolve com a *trace configuration*
(`about-trace-configurations.htm`).

## Decisão

**A configuração é um documento salvo que preenche o pedido; o motor continua sendo o mesmo.**

1. `plat.rede_config_tracado` guarda código, nome, tipo de traçado, o documento `config` e o dono, por
   inquilino, com RLS igual ao resto das tabelas de rede.
2. O uso é um campo novo — `config_id` — no `POST /api/rede/{id}/tracar` que já existia. Não existe rota
   paralela de traçado configurado. Do corpo continuam valendo só os pontos de partida e as barreiras
   pontuais daquele traçado; todo o resto vem da configuração.
3. As barreiras de condição são traduzidas para o que o motor já sabe recusar: a feição de PONTO que casa
   perde os terminais dela (mesma lista de barreiras que o chamador já podia passar) e a feição de LINHA que
   casa perde a aresta dela (`arestas_excluidas`, único parâmetro novo em `_montar_sql_arestas`). Nenhum
   caminho de execução novo, nenhuma segunda travessia do grafo.
4. As barreiras de FILTRO fazem o traçado correr uma segunda vez com as duas listas somadas, e o resultado
   publicado é a interseção. É o que distingue *filter barrier* de *condition barrier* na Esri: a primeira
   estreita o que sai, a segunda muda o que é percorrido. `passagens` sai na resposta para que nunca seja
   preciso adivinhar qual das duas valeu.
5. Filtro de saída, funções e tipo de resultado são calculados DEPOIS, sobre o conjunto de feições que
   sobrou — em SQL sobre `rede_feicao_ponto`/`rede_feicao_linha`, as mesmas tabelas que o sumário por
   subrede já consulta.

## Alternativas descartadas

**Guardar as configurações prontas dentro do arquivo do pacote.** O esquema JSON do pacote é fechado
(`additionalProperties: false`, `esquema_versao 1`); uma seção nova obrigaria a subir a versão do esquema e a
reimportar todo pacote já instalado, e o `sha256` do arquivo é o `ETag` da rota do pacote. As seis
configurações do pacote elétrica-BR ficam em `config_tracado.CONFIGS_PADRAO` e são semeadas na importação
(`deposito.importar`); a partir daí são linhas comuns da tabela, editáveis e apagáveis.

**Aceitar SQL na barreira.** A gramática é fechada: atributo mais operador de uma lista de dez, ou fase, ou
categoria, ou grupo, ou tipo. Atributo que a rede não tem é recusado com 422 dizendo o nome; operador fora da
lista, idem. Uma configuração é dado de inquilino, e dado de inquilino não vira consulta.

**Tornar todo tipo de traçado configurável.** `lacos`, `isolados` e `caminho_curto` não partem de um ponto e
não têm barreira de condição no mesmo sentido; a coluna `tipo` só aceita `conectado`, `subrede`, `montante` e
`jusante`, e um pedido com outro tipo é recusado na criação, em vez de aceito e silenciosamente ignorado.

## Consequências e limites honestos

* **Ponto de partida nunca é removido pela própria configuração.** Uma barreira de condição que casasse com o
  ponto de partida devolveria vazio sem explicação; os nós de partida são excluídos da lista de barreiras
  derivadas, e isso está escrito na docstring do módulo.
* **`incluir_estrutura` funciona por coincidência de posição, não por associação registrada.** A associação
  de contenção/fixação (`plat.rede_associacao`) é do modelo importado da BDGD (`rede_no`/`rede_aresta`), não
  do modelo de feições que o traçado percorre. Enquanto os dois modelos não se encontrarem, a estrutura entra
  no resultado por coincidir, dentro da tolerância da rede, com um nó alcançado. É o que a implementação faz
  e é o que a docstring diz.
* **O nome do caminho é `/api/rede/...`, não `/api/v1/rede/...`.** O portão do item pedia `/api/v1`; o
  produto inteiro responde sem versão na URL e `tests/api/test_versionamento.py` reprova o contrário
  (`docs/CONTRATO_API.md`). Mesma decisão dos ADR 0019 §6 e 0020 §6.
* **A função soma o que o traçado ALCANÇOU.** O sumário por subrede (L4-04-c) soma o que o CADASTRO filia ao
  alimentador. Os dois números podem diferir, e a diferença é achado — não erro de nenhum dos dois. A medição
  em dado real grava os dois lados (`tests/medidas/L4-02-e-configuracoes-de-tracado.json`).
