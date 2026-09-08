# Atualizar e exportar subrede (item L4-04-b-atualizar-e-exportar-subrede)

Data: 2026-09-07. Estado: aceito. Depende do ADR `20260907T2031` (controlador de subrede e tiers).

## Contexto

O item irmão criou o controlador, o tier e o registro da subrede com estado limpa/suja. A atualização parava
no traçado: contava elementos e gravava um resumo. Faltava tudo o que faz a subrede existir para fora —
onde mora o nome da subrede de cada elemento, o que é propagado do controlador, a linha agregada que a Esri
chama de SubnetLine, e o formato em que um sistema de operação consome a subrede.

## Decisões

1. **O nome da subrede vai para uma tabela derivada, não para a feição.** A Esri escreve `subnetworkname` na
   própria feição. Aqui o par (elemento, subrede) vive em `plat.rede_subrede_elemento`, e
   `plat.rede_feicao_*.atributos` continua sendo o dado como veio do arquivo. O motivo é a conferência: a
   cláusula do portão compara o nome CALCULADO com o `CTMT` DO ARQUIVO no mesmo trecho. Se o cálculo
   escrevesse no mesmo jsonb, não haveria mais duas coisas para comparar.

2. **Propagador é do tier.** `plat.rede_tier.propagadores` é a lista de códigos de atributo do pacote que o
   tier propaga; o valor é lido nos atributos do DISPOSITIVO controlador e gravado em cada elemento
   (`rede_subrede_elemento.propagados`). Dois controladores com valores diferentes para o mesmo atributo não
   são fundidos: o atributo fica de fora e aparece em `resumo.propagadores_divergentes`. Substituição bit a
   bit e função de propagação (a Esri tem as duas) ficam fora desta passagem.

3. **A SubnetLine é coluna, não tabela.** É uma linha por subrede, 1 para 1 com `plat.rede_subrede`; virou
   `linha geometry(MultiLineString, 4326)` mais `comprimento_m`. Costurada com `ST_LineMerge` sobre os
   trechos membros; comprimento em `geography` (metros de verdade).

4. **A subrede é marcada suja NO INSTANTE DA EDIÇÃO.** `feicoes.marcar_area_suja` grava o polígono da área
   suja e, na mesma chamada, marca `suja` a subrede cujos elementos aquele polígono toca. Não dava para
   calcular o estado só a partir das áreas abertas: `topologia.habilitar()` APAGA as áreas sujas ao
   reconstruir o índice, e subrede obsoleta viraria subrede limpa em silêncio. O cruzamento é por subrede —
   a versão anterior dava a rede inteira por suja diante de qualquer edição, o que numa cooperativa com 20
   alimentadores significa refazer 20 subredes por causa de um poste.

5. **O lote é um job; uma subrede só é síncrona.** `redes.subredes_atualizar` transporta a chamada para a
   fila (progresso por subrede, cancelamento, filtro por tier); a tela continua atualizando uma subrede na
   hora, porque a resposta é rápida e é o que a pessoa está olhando. O job não tem lógica própria.

6. **O esquema da exportação é contrato.** `app/rede_utilidades/esquema_exportacao.py` (rascunho 2020-12,
   `additionalProperties: false` em todo objeto) valida a saída ANTES de ela sair; saída fora do esquema é
   erro 500 nomeado, não um JSON diferente entregue em silêncio. A exportação lê o que a última atualização
   gravou, não um traçado novo — é o que permite comparar exportação e traçado elemento a elemento.

7. **Recusa dentro do lote não derruba o lote.** Subrede sem controlador, ou com controlador sem nó na
   topologia atual, sai nomeada com o código do erro e continua suja. O lote fecha a conta:
   atualizadas + recusadas = candidatas.

## Defeito corrigido no caminho (medido, não suposto)

`controladores.marcar_da_importacao` escolhia, para o tier de média tensão, qualquer ativo com a categoria
`controlador` naquele tier. Num arquivo BDGD sem a camada de chaves, o escolhido era o TRANSFORMADOR, e o
controlador nascia no terminal de jusante dele — do lado de lá da fronteira de subrede. Medido nos três
maiores alimentadores da cooperativa de teste: 13.646 trechos no arquivo, **4 elementos alcançados**. A
correção é uma regra do próprio modelo: ativo de TRANSFORMAÇÃO separa dois tiers, logo nunca é o controlador
do tier de cima. Com ela, os mesmos três alimentadores dão 14.878 elementos e concordância 1,0 com o `CTMT`.

## O que ficou de fora

* tier de baixa tensão em escala: uma subrede por transformador (5.481 no arquivo inteiro), cada atualização
  custando uma passada de componentes conexas — não foi medido, e prometer o número sem medir seria invenção;
* exportação em lote e assíncrona (a ferramenta da Esri exporta várias subredes de uma vez);
* substituição e função de propagação;
* grupo de tier (*tier group*), lacuna já nomeada pelo item L4-04-a.
