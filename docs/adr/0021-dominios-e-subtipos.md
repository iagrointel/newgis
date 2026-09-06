# ADR 0021 — Domínios de atributo e subtipos por camada

Item `L2-10-a-dominios-subtipos`. Estado: aceito. Setembro de 2026.

## Contexto

A camada vetorial da plataforma já tinha campos tipados (ADR 0005), mas nada dizia quais VALORES cada campo
aceita. É o que o ArcGIS chama de domínio de atributo (lista de códigos ou faixa numérica) e de subtipo (um
campo inteiro que divide a camada em classes, cada uma com seus próprios domínios e valores padrão). Sem
isso, a migração de um dado que vem de um geodatabase perde a regra junto com a lista, e o formulário de
edição não tem como oferecer escolha nenhuma.

## Decisões

**1. O domínio é objeto do inquilino, não da camada.** `plat.dominio` tem nome único por inquilino e é
compartilhado por quantas camadas quiserem. A ligação campo -> domínio é que mora por camada
(`plat.dominio_campo`), e admite uma linha por subtipo além da linha padrão. Uma lista de UF escrita uma vez
vale em todas as camadas; corrigir a descrição de um código corrige em todas.

**2. A regra vale no banco, por gatilho, e não por CHECK.** `tg_dominio` roda BEFORE INSERT OR UPDATE em cada
tabela de camada que tenha ligação ou subtipo. Três razões:
- mudar a lista de valores não pode exigir `ALTER TABLE` (com CHECK, exigiria, e travaria a tabela);
- a mensagem de erro precisa dizer o campo e o valor: `campo "uf": o valor 'ZZ' não pertence ao domínio
  "UF"`, com o nome do campo também em `COLUMN` (o `diag.column_name` que a API repassa em `detalhe.campo`);
- quem escreve por fora da API — um `psql`, um script de carga, um `ogr2ogr` — leva exatamente a mesma
  recusa. Regra que só existe na API não é regra, é sugestão.

**3. O gatilho só existe onde é preciso.** `plat.camada_dominios_aplicar(item_id)` instala `tg_dominio` na
tabela quando a camada ganha a primeira ligação ou subtipo, e o REMOVE quando perde a última. Camada sem
domínio não paga nada por linha.

**3b. O gatilho é GERADO por camada, não genérico — e a medida é a razão.** A primeira versão era uma função
única que lia os campos com `to_jsonb(NEW)`, a única forma de um plpgsql genérico acessar campo por nome.
Medido em 10 mil inserções: 1,72 s sem gatilho contra 3,11 s com, **razão 1,80x**, acima do teto de 1,5x do
item. Um gatilho que só faz `to_jsonb(NEW)` e retorna já custa cerca de 129 us por linha, porque converte a
linha inteira — a geometria inclusive. `plat.camada_dominios_aplicar` passou a ESCREVER uma função por camada
(`plat.dominio_v_<item>`) com `NEW.uf` no código. Fica embutido só o que muda por DDL (campo, id do domínio,
lista de subtipos, mínimo e máximo); a lista de códigos continua sendo lida em `plat.dominio_valor` a cada
linha, porque pode ter milhares de itens e muda com frequência.

**3c. Quem mantém a função gerada em dia é o banco, não a API.** Gatilhos AFTER em `plat.dominio_campo`,
`plat.camada_subtipo` e `plat.dominio` chamam o gerador sozinhos. Nenhuma rota instala gatilho; quem alterar
uma ligação por `psql` regenera do mesmo jeito. Regra que só a API mantivesse não seria regra.

**4. `plat.dominio_valor` é índice derivado, não segunda fonte de verdade.** A forma declarada e devolvida
pela API é `plat.dominio.valores` (jsonb). O gatilho `plat.dominio_sincronizar` (AFTER) reescreve a tabela
normalizada a cada gravação. Ela existe por desempenho: a conferência por linha vira uma sondagem de chave
primária em vez de varrer um array jsonb. Ninguém escreve nela por fora.

**5. Duas funções de gatilho em `plat.dominio`, não uma.** A conferência de forma é BEFORE (recusa antes de
gravar, ajusta `atualizado_em`); a sincronia do derivado é AFTER, porque `plat.dominio_valor` tem chave
estrangeira para `plat.dominio` e num BEFORE INSERT a linha do domínio ainda não existe.

**6. Erro do banco sai com o errcode padrão (P0001).** O código curto vai na mensagem primária e o texto
legível no DETAIL, que é o contrato que `app/auth/comum.erro_do_banco` lê. Com `ERRCODE='check_violation'` o
psycopg2 devolveria `CheckViolation`, o tradutor cairia no 422 genérico e se perderiam a contagem do
`valor_em_uso` e o nome do campo.

**7. Remover valor em uso é 409 com a contagem, e quem conta é o banco.**
`plat.dominio_uso_contar(dominio_id, codigo)` percorre as camadas ligadas com SQL dinâmico e conta as
feições. A mesma função responde `GET /api/dominios/{id}/uso` (o que a tela mostra ANTES de deixar remover) e
barra a remoção no gatilho — não existem dois números possíveis para a mesma pergunta.

**8. Teto de 2.000 códigos por domínio.** Domínio codificado é lista de escolha de formulário, não tabela de
dados; acima disso o certo é uma camada de referência com junção. O teto está no banco e na API, com a mesma
constante.

**9. Intervalo só sobre campo numérico.** Intervalo de data existe no ArcGIS Pro; aqui não foi construído nem
medido, e o banco recusa em vez de deixar passar meio funcionando.

**10. Um domínio de um inquilino nunca alcança a camada de outro.** Além da RLS (que já esconde as duas
pontas e faz a rota responder 404), `plat.dominio_campo` tem chave estrangeira COMPOSTA para
`plat.dominio (id, tenant_id)` e para `plat.item (id, tenant_id)`: mesmo com a RLS desligada, o banco recusa
a linha cruzada.

## Fronteiras declaradas (o que NÃO está aqui)

- **FeatureServer completo.** `/rest/services/{item_id}/FeatureServer[/0]` publica só o METADADO da camada,
  com `fields[].domain` e `types[]`. `/query`, `/applyEdits`, versão e anexo são da linha L2-08; quando ela
  chegar, o que se reaproveita é `app/dominios/esri.py`.
- **Edição de feição em lote.** `POST /api/camadas/{id}/feicoes` grava UMA feição e existe para o formulário
  de atributos deste item ter o que provar.
- **Popup do mapa.** `web/js/dominios/valores.js` é a função única que troca código por descrição e já é usada
  no formulário e na tabela desta tela; o popup do mapa passa a usá-la quando o painel de camada do L2-01
  existir.
- **Importação de FGDB por arquivo.** `POST /api/dominios/importar` recebe o objeto `fields`/`types` (o mesmo
  que a Esri publica em `?f=json`). Ler o arquivo `.gdb` e extrair esse objeto é o item L2-08-b.

## Divergência do repositório encontrada no caminho

O slug de inquilino aceito pela API admite hífen (`^[a-z0-9-]{2,39}$`), mas `plat.camada_schema_garantir` e
`plat.camada_preparar` (migração 029) exigem `^[a-z][a-z0-9_]{0,60}$` no slug e `^d_[a-z0-9_]{1,62}$` no
schema. Um inquilino com hífen no slug, portanto, não consegue publicar camada hospedada. Não foi corrigido
neste item (mexeria na ingestão, que é de outra trilha); está anotado no handoff e contornado no teste com um
slug sem hífen.
