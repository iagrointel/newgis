# 20260907T2243 — Sumário por subrede: tabela calculada, filiação declarada pelo cadastro

Item `L4-04-c-sumarios-por-subrede`. Estado: aceito.

## Contexto

O item L4-04-a criou o registro da subrede (`plat.rede_subrede`) e guarda ali um resumo do TRAÇADO: quantos
elementos foram alcançados e em quanto tempo. Isso responde "a atualização rodou". A pergunta que a operação
faz é outra: quanto tem este alimentador — quilômetro por nível de tensão, transformadores e potência
instalada, clientes por classe, energia faturada no ano, dispositivos por categoria, geração distribuída
ligada e o quanto a rede se estende a partir da fonte.

## Decisão

1. **Tabela própria, `plat.rede_subrede_resumo`, uma linha por subrede.** O registro da subrede é ciclo de
   vida e muda a cada edição; o sumário é dado calculado, refeito inteiro e descartável. Separados, dá para
   apagar e recalcular sem tocar no registro, e o painel lê uma tabela em que quase toda coluna é número.
   As três grandezas cuja CHAVE vem do pacote (nível de tensão, classe da unidade consumidora, categoria do
   dispositivo) ficam em jsonb, com o total correspondente em coluna: chave de pacote em coluna fixa
   obrigaria migração a cada pacote novo.

2. **A filiação de cada elemento à subrede vem do atributo que o arquivo declara, por tier**
   (`resumos.ATRIBUTO_DE_SUBREDE_POR_TIER`): média tensão usa `ctmt`, baixa tensão usa `uni_tr_mt`. É a
   MESMA convenção com que `controladores.marcar_da_importacao` nomeia as subredes vindas da BDGD — lá o
   nome da subrede de média tensão é o código do alimentador e o da subrede de baixa tensão é o código do
   transformador. Tier fora dessa tabela é recusado com `422 tier_sem_atributo_de_subrede` em vez de somar
   coisa nenhuma e devolver zero.

   ⛔ Isto é o que o CADASTRO declara, não o que a topologia alcança, e a escolha é deliberada: o sumário
   serve para comparar com o que a distribuidora declara ao regulador. Um trecho fisicamente ligado ao
   alimentador vizinho, com o código do primeiro escrito no cadastro, entra no sumário do primeiro. Quando
   `plat.rede_subrede_elemento` (item L4-04-b, o traçado que alcança) existir na mesma árvore, a divergência
   entre as duas leituras é o achado — e nenhuma das duas substitui a outra.

3. **Comprimento declarado e comprimento pela geometria, os dois guardados.** Cada trecho traz o comprimento
   que o cadastro declara (`comp`) e tem a linha carregada. `km_declarado`, `km_geometria` e a diferença em
   porcento ficam lado a lado, porque a diferença é medida de qualidade de cadastro. Medido na cooperativa
   de teste: a diferença por alimentador vai de +0,03 % a −8,49 % (mediana perto de −0,5 %).

4. **Tronco medido pela topologia, ou nulo com a razão escrita.** `tronco_max_m` é a maior distância, andando
   pela rede, de um controlador da subrede até um nó alcançável dela (Dijkstra sobre as arestas cujo trecho é
   filiado à subrede, mais as arestas virtuais de dispositivo declaradas no terminal do pacote — sem elas o
   caminho pararia no primeiro disjuntor, porque cada terminal é um nó próprio). Sem topologia ou sem
   controlador com nó, a coluna fica NULA e `tronco_origem` diz qual dos dois faltou. Gravar zero seria
   apresentar ausência de medida como medida.

5. **Uma rota de leitura que se descreve.** `GET .../subredes/resumos` devolve `colunas` (código, nome, tipo,
   unidade) ao lado de `itens`: é o que um elemento de painel precisa para se ligar à fonte sem que ninguém
   escreva rótulo à mão. `formato=csv` devolve a mesma tabela como arquivo (mesmo padrão do log de acesso do
   L0-02), com as colunas de mapa em JSON dentro da célula.

## Consequências

- O sumário não exige topologia nem controlador: uma rede recém-importada já pode ser somada, e só a coluna
  do tronco fica de fora.
- Pacote novo (água, gás) precisa acrescentar a linha dele em `ATRIBUTO_DE_SUBREDE_POR_TIER`, senão o tier é
  recusado dizendo isso. É uma linha por tier, e o erro é explícito.
- Nome da subrede repetido em dois tiers não confunde o sumário: a linha é endereçada pelo identificador da
  subrede, e o tier vai junto na leitura.

## Unidades: medidas, não assumidas

O dicionário do pacote `eletrica-br` declara `COMP` em km e `ENE_SUM` em MWh. No extrato da cooperativa de
teste os dois estão em outra escala: a soma de `COMP` por alimentador bate com o comprimento geodésico do
próprio traçado em METROS, e a média de `ENE_SUM` por unidade consumidora é 2.950 por ano, coerente com kWh.
O cálculo soma o valor como está no arquivo e converte comprimento de metro para quilômetro; a conferência do
teste compara com o MESMO valor do arquivo, de modo que vale qualquer que seja a unidade. Corrigir o
dicionário do pacote é item de outra frente e está anotado aqui para não se perder.
