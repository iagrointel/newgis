# Escala do motor multicritério: onde a conta roda, de quanto em quanto, e o que se recusa antes de começar

Estado: aceito · Item: `L3-16-desempenho-escala` · Linha: L3 (motor AMC)

## Contexto

O motor multicritério já sabia combinar (item L3-01-e) e extrair fator de raster e de vetor (L3-01-c),
mas ninguém tinha escrito quanto ele aguenta. Sem esse número declarado, três coisas acontecem: a tela
manda uma grade de meio milhão de células para o navegador e a aba trava; o job carrega o conjunto
inteiro em memória e o worker morre por `RLIMIT_DATA`; e um trabalho de três horas é enfileirado num job
com prazo de trinta minutos, para ser morto pelo relógio no fim, depois de gastar a máquina.

## Decisão

1. **Uma fronteira só entre navegador e servidor**, em `AMC_COMBINAR_NAVEGADOR_MAX` (50.000 unidades),
   escrita nos dois lados e comparada por teste. O navegador RECUSA acima dela
   (`unidades_demais_para_o_navegador`) em vez de combinar pela metade. Recusa explícita é melhor que
   degradação silenciosa: o usuário fica sabendo que a conta passou ao servidor.
2. **O servidor trabalha em blocos** de `AMC_BLOCO_UNIDADES` (50.000) unidades, lidos por FAIXA de
   `unidade_id` — não por `OFFSET`, que relê o que já passou. A propriedade que interessa é que o pico de
   memória é o de UM bloco: multiplicar o conjunto por dez multiplica o número de blocos, nunca o pico.
   É isso que permite afirmar um teto de RAM para 1 milhão de células sem medir 1 milhão.
3. **O orçamento de RAM é o MENOR** entre o teto declarado do produto (`AMC_EXTRACAO_MEMORIA_MB`, 4 GB) e
   o teto da máquina (`PLAT_WORKER_MEMORIA_MB`). Numa instalação de 1 GB por job, o motor pede 1 GB e diz
   1 GB — nunca promete os 4 GB do papel. Quem aplica o teto continua sendo o `RLIMIT_DATA` do processo
   filho da fila (item L0-05-e); este ADR só decide o número.
4. **O plano é recusado antes de enfileirar** quando não cabe: unidades demais, fatores demais, bloco
   maior que o orçamento, e — para extração — tempo projetado maior que o prazo do job. A projeção usa a
   taxa MEDIDA (`AMC_EXTRACAO_US_POR_UNIDADE_FATOR`, que sai de `tests/medidas/`), não uma estimativa.
5. **O modelo de memória é conferido contra medida.** `pico_estimado_mb` é uma conta com constantes; o
   teste aloca um bloco cheio e compara com o pico real, e reprova se o modelo ficar ABAIXO do medido.
   Subestimar o pico é o único erro que não se pode cometer aqui.
6. **`amc.recombinar` é job pesado.** Duas execuções simultâneas rodam em série, pela regra que a fila já
   tinha (ADR 0003). O item não inventou fila nova; herdou a existente e conferiu que vale para o motor.

## O que isto CUSTA, e por que se aceita

A leitura por faixa de `unidade_id` exige que os identificadores de unidade sejam ordenáveis e estáveis
dentro de uma execução — são: `plat.amc_fator_bruto` tem chave primária `(execucao_id, unidade_id, fator)`.

A combinação no servidor NÃO foi reimplementada em SQL, embora a hipótese do item admitisse isso. Motivo:
uma segunda implementação da mesma conta é uma segunda coisa a manter equivalente, e o repositório já paga
esse preço duas vezes (Python × JavaScript no combinador, Python × PL/pgSQL nas transformações). A leitura
em blocos com `numpy` cumpre o mesmo papel de memória sem criar um terceiro combinador. Se um dia a rede
entre a aplicação e o banco virar o gargalo, a decisão se revisita com número na mão.

## Consequência medida que muda o produto

À taxa medida da estatística zonal (701 µs por unidade e por fator), extrair 1 milhão de células por 15
fatores leva quase 3 horas — seis vezes o prazo do portão. **A cláusula de extração do portão do item está
refutada no tamanho cheio.** O limite honesto de hoje, com 15 fatores, é uma grade de 166.898 unidades, e o
motor recusa acima disso com o número na mensagem. Isso é um limite do extrator unidade a unidade, não do
desenho: a extração em lote é o item `L3-01-c2-extracao-em-lote`, e é ele quem move este número.
