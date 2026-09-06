# ADR 0019 — O esquema da rede de utilidades é dado, não código

Data: 2026-09-06 · Item: `L4-01-a-pacote-de-ativos` · Estado: aceito · Papéis: redes, arquiteto, dados, backend

Este é o primeiro item da linha L4 (rede de utilidades). As decisões abaixo valem para os itens seguintes da
linha (topologia, traçado, edição de rede, subrede) e não devem ser refeitas item a item.

## 1. Problema

Uma rede de utilidades é sempre a mesma máquina — domínios, níveis, classes de ativo, subtipos, categorias,
terminais, regras de conexão — com vocabulário diferente por disciplina. Escrever esse vocabulário em código
significa uma versão da plataforma por distribuidora e nenhuma forma de levar o esquema de um cliente para
outro. O ArcGIS resolve isso com *domain networks*, *tiers*, *asset groups*, *asset types*, *network
categories* e *terminal configurations* dentro do geodatabase, e com um "foundation" pronto por disciplina
(elétrica, água, gás).

## 2. Decisão

O esquema da rede é um **pacote de ativos**: um documento JSON versionado, importado para as tabelas
`plat.rede_*` do inquilino e exportado de volta a partir delas. Duas rotas:

    POST /api/rede/{rede_id}/pacote     importa (substitui o catálogo inteiro da rede, numa transação)
    GET  /api/rede/{rede_id}/pacote     exporta, na forma canônica, reconstruído das tabelas

O pacote tem oito seções planas — `dominios`, `tiers`, `categorias`, `terminais`, `grupos`, `tipos`,
`atributos`, `regras` — e cada elemento aponta o pai pelo CÓDIGO, não por aninhamento.

**Por que plano e não aninhado.** Aninhar tipos dentro de grupos tornaria "tipo sem grupo" impossível de
escrever, e a cláusula do portão que manda recusar esse caso viraria letra morta. Pior: um pacote aninhado só
se compara inteiro. Com seções planas, dois pacotes se comparam seção a seção, um erro aponta uma linha, e o
formato aceita referência cruzada (um tipo do domínio elétrico preso a um tier, um atributo preso a um tipo)
sem duplicar o objeto.

## 3. Forma canônica e ida e volta byte a byte

A exportação é serializada em **forma canônica**: JSON UTF-8, chaves em ordem alfabética, recuo de um espaço,
listas ordenadas por chave declarada (`app/rede_utilidades/pacote.py`, `ORDEM`) e uma quebra de linha no fim.

A alternativa — guardar os bytes recebidos e devolvê-los — faria o mesmo teste de ida e volta passar
escondendo justamente o que interessa provar: que as tabelas carregam o pacote inteiro. Por isso **nada do
arquivo recebido é guardado** (só o sha256, para conferência), e existe um teste que altera uma linha no banco
e exige que a exportação mude junto (`test_a_exportacao_vem_das_tabelas_e_nao_do_arquivo_recebido`).

Consequência aceita: um pacote enviado fora da forma canônica volta canonizado, e não idêntico ao arquivo
enviado. O contrato é "o mesmo pacote", não "os mesmos bytes de entrada"; os pacotes entregues com a
instalação já estão na forma canônica, e há teste que reprova se algum sair dela.

## 4. Validação em duas camadas, com a linha do arquivo

1. **Esquema JSON** (rascunho 2020-12, `app/rede_utilidades/esquema.py`): forma, vocabulário fechado
   (disciplina, tipo de domínio, tipo de tier, geometria, tipo de dado, tipo de regra), obrigatoriedade.
2. **Conferência de referência** (`app/rede_utilidades/pacote.py`): código repetido e referência para algo que
   não existe no pacote — o que nenhum esquema JSON alcança sem `$dynamicRef` ilegível.

Todo problema sai com o caminho (`tipos[41].grupo`), o **número da linha do arquivo enviado** e um código
curto; a resposta traz a lista inteira, nunca só o primeiro erro. A linha vem de
`app/rede_utilidades/localizador.py`, que percorre o texto bruto com o próprio decodificador do Python
(`raw_decode` pula um valor inteiro sem interpretá-lo). Sem isso, "o tipo 41 aponta um grupo que não existe"
obriga quem enviou a contar elementos à mão num arquivo de 96 KB.

## 5. Tabelas e isolamento

Dez tabelas (`plat.rede`, `rede_dominio`, `rede_tier`, `rede_categoria`, `rede_terminal_config`, `rede_grupo`,
`rede_tipo`, `rede_tipo_categoria`, `rede_atributo`, `rede_regra`), todas com `tenant_id` e RLS `FOR
SELECT/INSERT/UPDATE/DELETE` na role `plat_app`, no mesmo padrão de `plat.conexao` (migração 030). Chaves
estrangeiras internas em cascata a partir de `plat.rede`: apagar a rede leva o catálogo junto, e
`plat.tenant_apagar_interno` (migração 009) alcança as tabelas novas sem alteração, porque varre toda tabela do
schema que tenha `tenant_id`.

Identificadores internos são `uuid` e os códigos do pacote são únicos por rede — é o que permite importar o
mesmo pacote em dois inquilinos sem colisão. A escrita exige o privilégio `rede.editar`, já semeado na migração
003; nenhum privilégio novo foi criado.

## 6. Caminho da rota: `/api/rede/...`, sem `v1`

O portão do item dizia `/api/v1/rede/{rede_id}/pacote`. As 74 rotas do produto respondem em `/api/` sem prefixo
de versão, e a versão do formato já está DENTRO do documento (`esquema_versao`, hoje 1). Manter `v1` só nesta
linha criaria duas convenções de URL na mesma API e um versionamento que ninguém mais usa. Decisão: a linha L4
inteira responde em `/api/rede/...`; a compatibilidade futura é resolvida por `esquema_versao`, que é
reescrito por migração de pacote quando mudar.

## 7. Pacotes entregues com a instalação

`app/rede_utilidades/pacotes/*.json` é DADO entregue com o produto, não código: dois pacotes na primeira
entrega — `eletrica-br` (as 13 camadas de rede da BDGD, Módulo 10 do PRODIST) e `agua-epanet` (o vocabulário do
EPANET 2.2). São servidos por `GET /api/rede/pacotes` e `GET /api/rede/pacotes/{codigo}` e conferidos na subida
do processo (um pacote fora da forma canônica quebra ali, não no primeiro cliente que tentar importar).

Cada atributo carrega a origem (`esquema`, `camada`, `coluna`) e a marca `conferida`: verdadeira só quando a
coluna foi lida numa extração real. Na primeira entrega, 11 camadas do pacote elétrico têm origem conferida e
5 (`SUB`, `UNSEMT`, `UNCRMT`, `UNREMT`, `UGMT_tab`) são declaradas do documento da fonte, sem conferência; o
pacote de água inteiro é declarado. O mapeamento sai em `docs/PACOTE_REDE.md`, gerado do próprio dado por
`docs/gerar_pacote_rede.py --check`, para que o documento não possa divergir do pacote.

## 8. O que este ADR NÃO decide

Topologia, traçado, subrede, validação de rede ligada, edição de feição de rede e desenho da camada de rede no
mapa são itens seguintes da linha L4. O pacote descreve o esquema; nenhuma feição de rede é criada aqui.
