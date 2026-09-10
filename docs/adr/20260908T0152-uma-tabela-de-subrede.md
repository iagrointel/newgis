# ADR 20260908T0152 — uma tabela de subrede, com a origem declarada ao lado da derivada

Substitui o ADR 20260907T2200 (que decidiu apenas o desempate de NOME entre as duas tabelas e deixou a
unificação escrita como pendência).

## Contexto

Dois itens da linha L4 criaram, em ramos separados, tabelas com o mesmo conceito e colunas incompatíveis:

- `plat.rede_subrede` (item L4-04-a): a subrede no sentido do *subnetwork controller* — `tier_id`, `nome`,
  `estado` limpa/suja, `resumo`, linha agregada. Nasce do CONTROLADOR marcado num terminal e é o que o
  traçado calcula a partir da rede que está no chão.
- `plat.rede_subrede_bdgd` (item L4-01-c): a hierarquia que o ARQUIVO da BDGD declara — `nivel` 1 a 4,
  `codigo_externo` (COD_ID da SUB/CTMT/UNTRMT), `pai_id` com nível estrito.

Enquanto foram duas tabelas, nada ligava uma linha à outra: não havia como responder "o que o arquivo diz
e o que a plataforma calculou batem?", que é a pergunta que um operador de rede faz primeiro.

## Decisão

Uma tabela só, `plat.rede_subrede`, com a coluna `origem`:

- `origem='controlador'` é a CANÔNICA. Tem tier, ciclo de vida (limpa/suja), elementos, linha agregada e
  resumo. Nada mudou para ela: as colunas, as rotas e os testes do item L4-04-a e do L4-04-b continuam.
- `origem='bdgd'` é a ORIGEM DECLARADA. Tem `nivel`, `codigo_externo`, `pai_id`, `controlador_no_id` e
  `atributos`; não tem tier nem ciclo de vida, e o `estado` dela é o valor fixo `declarada`.
- `equivalente_id` liga a linha declarada à derivada correspondente quando a reconciliação encontra o par.

Um `CHECK` por origem (`rede_subrede_forma_da_origem`) impede a mistura: linha derivada com nível, ou
declarada com tier, é recusada pelo banco. O gatilho de nível estrito do item L4-01-c passou para a tabela
unificada com os MESMOS nomes de exceção (`subrede_nivel_invertido`, `subrede_sem_pai`).

A migração `20260908T0152` copia as linhas da tabela antiga PRESERVANDO O `id` e repõe as chaves
estrangeiras de `plat.rede_no.subrede_id` e `plat.rede_aresta.subrede_id` na tabela unificada — nenhuma
referência é reescrita. Depois disso a tabela antiga é removida.

## Por que a derivada é a canônica

A hierarquia do arquivo é uma DECLARAÇÃO do cadastro da distribuidora: ela diz a que alimentador cada
elemento pertence segundo o cadastro, não segundo a eletricidade. A derivada sai do traçado sobre a
topologia real: chave aberta, trecho faltando e ligação errada aparecem nela. Quando as duas discordam, é
a discordância que interessa — e ela só é visível se as duas estiverem gravadas, na mesma tabela, com
origem marcada.

## Reconciliação

`app/rede_utilidades/reconciliacao.py`:

- `declarar` lê a hierarquia dos atributos que as feições carregam do arquivo (`sub`, `ctmt`, `cod_id` do
  transformador) e grava as linhas declaradas. Campo ausente no arquivo vira contagem
  (`alimentadores_sem_subestacao`, `transformadores_sem_alimentador`), nunca código fabricado. O
  importador de FileGDB (`bdgd.py`) grava as mesmas linhas direto durante a carga.
- `reconciliar` liga cada declarada à derivada de mesmo nome dentro do tier daquele nível, e devolve, por
  nível, o universo declarado, quantas casaram e a razão sobre esse universo.

As duas rodam no fim de `controladores.marcar_da_importacao`, que é a passagem que a importação já
chamava: nenhuma rota nova.

## Fronteira honesta

A reconciliação mede CONCORDÂNCIA entre duas leituras da mesma rede. Ela não prova que o traçado está
certo nem que o cadastro está errado: divergência é candidata a erro de cadastro ou a limite do traçado,
e sai como número, nunca como acusação.

Nível 4 existe na coluna (`nivel BETWEEN 1 AND 4`) porque a tabela antiga o admitia; nenhum caminho de
carga o produz hoje, e a reconciliação cobre os níveis 2 (alimentador) e 3 (transformador), que são os que
têm tier correspondente no pacote elétrico.
