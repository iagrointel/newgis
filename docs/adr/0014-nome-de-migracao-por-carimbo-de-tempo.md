# ADR 0014 — Nome de migração por carimbo de tempo (fim da colisão de numeração)

Estado: aceito (turno T3, setembro de 2026). Substitui a regra de numeração sequencial descrita no
ADR 0001 seção 5 e o adendo de "reserva fixa de número" do brief de trilhas paralelas, que passa a ser
obsoleto. Nenhuma migração existente foi renomeada.

## 1. Contexto: o número não é etiqueta, é chave

`plat.versao_migracao` é chaveada pelo NOME do arquivo (`nome text PRIMARY KEY`). O aplicador
`db/migrar.sh` decide o que aplicar comparando o nome em disco com o nome na tabela. Logo:

- renomear um arquivo JÁ APLICADO faz o aplicador tratá-lo como novo e aplicá-lo de novo, em qualquer
  base onde a versão antiga já tenha rodado (produção, homologação, as bases por trilha do laço);
- o nome antigo fica órfão na tabela e passa a contar como "aplicada" sem arquivo correspondente.

Com uma sessão só isso nunca aparece. Com N trilhas em paralelo (worktrees `wt/*`), duas trilhas
escolhem o mesmo próximo número no mesmo dia, porque cada uma olha para o `ls` da sua árvore. Em
06/09/2026 isso aconteceu TRÊS vezes com o mesmo arquivo, que foi renumerado 031 → 037 → 044 → 045.
A tentativa anterior de conserto — uma tabela de reserva de números escrita no brief — não resolve:
exige um coordenador acordado no momento em que a trilha cria o arquivo, e a árvore principal continua
avançando enquanto as trilhas trabalham.

O teste `tests/api/test_saude.py` fechava o cerco pelo outro lado: casava `[0-9][0-9][0-9]_*.sql` e
exigia que o ÚLTIMO do glob fosse `ultima_migracao` do `/saude`. Um número maior criado por outra
trilha e ainda não aplicado no schema em uso derrubava o teste.

## 2. Decisão

Migração NOVA nasce com carimbo de tempo UTC no nome:

    db/migracoes/YYYYMMDDTHHMM_<slug>.sql        ex.: 20260906T1742_camada_amc.sql

Quando duas nascem no mesmo minuto em trilhas diferentes, acrescentam-se 3 hexadecimais logo após o
minuto: `20260906T1742a3f_camada_amc.sql`. O carimbo sai de `date -u +%Y%m%dT%H%M`; os 3 hex, de
`openssl rand -hex 2 | cut -c1-3`.

A família legada de três dígitos fica **IMUTÁVEL e FECHADA**. Nenhum arquivo dela é renomeado, e nenhum
arquivo novo usa três dígitos. `app.migracoes.ULTIMO_LEGADO = 48` é o portão disso. O corte ficou em 048,
e não em 047, porque `048_smtp_convites_correcoes.sql` já estava em disco, escrita por uma trilha paralela,
quando esta regra entrou — e a primeira regra deste ADR é que arquivo existente não é renomeado.

## 3. Ordem de aplicação

Chave de ordenação de duas partes, em `app/migracoes.py:chave_migracao`:

    ("0", nome)  para o legado de três dígitos
    ("1", nome)  para o carimbo

Todo o legado vem ANTES de qualquer carimbo, e dentro de cada família vale a ordem lexicográfica —
que, para o carimbo, é a ordem cronológica, porque o formato é `YYYYMMDDTHHMM` de largura fixa. Os
3 hex opcionais empatam-se lexicograficamente entre si; migrações do mesmo minuto são independentes
por construção (se não forem, ver seção 4).

A mesma chave está escrita em bash, idêntica, em três lugares que não podem importar Python da app:
`db/migrar.sh`, `db/migrar_homolog.sh` e `laco/trilha_ambiente.sh` (este último não é do repositório).

## 4. Dependência explícita entre migrações do mesmo minuto

O carimbo resolve a COLISÃO, não a DEPENDÊNCIA: duas trilhas podem escrever no mesmo minuto uma
migração que depende da outra (uma cria a tabela, a outra acrescenta a coluna). Quem depende declara
no cabeçalho do arquivo, uma linha por dependência:

    -- depende: 20260906T1730_camada.sql

`tests/unit/test_migracoes_nome_e_dependencia.py` reprova quando a dependência declarada não existe
ou vem DEPOIS na ordem de aplicação, e prova o próprio portão com um par sintético invertido em
`tmp_path`. O conserto de uma inversão é renomear a SUA migração, ainda não aplicada, para um carimbo
posterior — nunca a outra, que pode já ter rodado em alguma base.

O cabeçalho é OPCIONAL: a maioria das migrações não depende de nada escrito no mesmo minuto.

## 5. O novo significado de "última"

`app.db.migracoes_estado` devolve `ultima` = a migração de AUTORIA mais recente pela `chave_migracao`
(o maior carimbo; na falta de carimbo, o maior número do legado), ordenando em Python e não com
`ORDER BY nome` no SQL — porque `ORDER BY nome` puro poria `001_fundacao` depois de `20260906T1742_x`
apenas quando o legado fosse renumerado, e sobretudo porque a ordenação passa a ser a da chave, não a
da string. `ultima_migracao` do `/saude` NÃO significa "a última que rodou no relógio" nem "a maior
string": significa a última na ordem de aplicação. O teste diz isso por escrito.

## 6. Consequências

- Duas trilhas nunca mais colidem sem falar entre si: o minuto UTC já é diferente, e o mesmo minuto é
  desempatado por 3 hex aleatórios. A reserva de números sai do brief.
- Perde-se a leitura "quantas migrações existem" pelo nome do último arquivo. Quem quiser o número
  usa `len(app.db.migracoes_em_disco())`.
- O `ls db/migracoes` deixa de ser ordenado por família única. `app.migracoes.listar` é a ordem
  verdadeira, e é ela que o aplicador, os testes e o `/saude` usam.
- Migração existente nunca é renomeada. Correção vem em arquivo novo, como já mandava o ADR 0001.
