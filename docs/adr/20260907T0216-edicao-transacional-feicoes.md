# ADR — Edição transacional de feições (item L2-03-a-api-edicao-transacional)

## Contexto

`POST /api/camadas/{id}/edicoes` é o equivalente do `applyEdits` da Esri e, a partir deste item, a
ÚNICA porta de escrita de feição para navegador, PWA, FeatureServer (L2-04-d) e OGC (L2-04-g). Roda
direto contra a tabela `d_<slug>.c_<uuid16>` que `app/ingestao/carregar.py`/`plat.camada_preparar`
(029_ingestao_vetor.sql) já cria: FORCE RLS por `tenant_id`, coluna `versao` para concorrência
otimista, `criado_por`/`atualizado_por`/`criado_em`/`atualizado_em` de rastreio. Nenhuma tabela nova.

## Decisões

1. **Transação por padrão, savepoint por feição no modo `parcial`.** `modo=transacao` (padrão) deixa
   a exceção propagar — o `with db.db(...)` do chamador desfaz tudo. `modo=parcial` abre um
   `SAVEPOINT` por feição (como o `applyEdits` com `rollbackOnFailure=false`): um erro desfaz só
   aquela feição e o lote segue, devolvendo resultado feição a feição.

2. **Isolamento entre inquilinos: 404, nunca 403.** Uma feição de outro inquilino já não aparece
   (RLS FORCE por `tenant_id` na própria tabela de camada, e `plat.pode_ler`/RLS de `plat.item` no
   item de catálogo) — o inquilino B recebe `item_inexistente`/`feicao_inexistente` (404) tanto ao
   tentar ler quanto ao tentar editar ou apagar. 403 ficou reservado para quando a EXISTÊNCIA da
   camada/feição já é conhecida do ator (ele está DENTRO do próprio inquilino) mas falta um
   privilégio específico — `edicao_desabilitada`, `feicao_de_outro_usuario` (ownership),
   `geometria_travada`. Confirmar com 403 a existência de algo que o ator não pode nem ver vazaria
   informação entre inquilinos (o mesmo raciocínio de `plat.pode_ler`, já em uso no catálogo).

3. **Domínio de atributo é DUAS fontes, não uma.** `dados.regras_campo` (este item, escopado à
   própria camada: `obrigatorio`, `somente_leitura`, `dominio_valores`, `dominio_min`/`dominio_max`)
   é o mecanismo introduzido aqui. O item L2-10-a-dominios-subtipos (entregue, ainda não integrado a
   esta árvore) traz `plat.dominio`/`plat.dominio_campo` COMPARTILHADO entre camadas, com subtipo.
   Quando as duas trilhas se juntarem, a validação de domínio ganha uma segunda fonte além de
   `regras_campo` — não é retrabalho, é adição (documentado também no topo de `app/edicao/servico.py`
   e no cabeçalho da migração).

4. **Sanidade de CRS não declarado.** O corpo aceita geometria já no SRID da camada (padrão) ou com
   `crs.srid` declarado (aí `ST_Transform` converte). Quando NÃO declarado e o SRID da camada é
   geográfico (grau — `spatial_ref_sys.proj4text ~ '+proj=longlat'`), uma coordenada fora de
   `[-180,180]`/`[-90,90]` é rejeitada com `422 geometria_fora_do_crs`: não é heurística de "parece
   errado", é o próprio domínio matemático do grau. Cobre o cenário do adversário (coordenada em
   metros — UTM/Web Mercator — mandada sem declarar `crs` para dentro de uma camada em graus), que
   de outra forma gravaria em silêncio uma geometria fisicamente absurda. Não tenta detectar CRS
   errado quando a camada já está projetada (metros): não há limite matemático equivalente ali, e
   inventar um seria uma heurística nova sem base — fica como fronteira honesta.

5. **`EDICAO_LOTE_MAX = 2.000`** (`app/limites.py`): 2× o tamanho medido no portão (1.000 feições em
   ≤ 3 s), com folga operacional. O lote de 100 mil da refutação do item cai primeiro no `413` do
   limite de corpo HTTP quando o corpo é grande, e sempre no `422` deste teto por lista mesmo com
   corpo pequeno e feições minúsculas (medido no roteiro do adversário).

## Fora desta passagem (fronteira honesta)

- Permissão por PERFIL/GRUPO por operação (adicionar/atualizar/apagar separadamente) fica só como
  `edicao.habilitada`/`somente_proprias`/`geometria_travada` + privilégio `feicoes.editar` /
  `feicoes.editar_total`; uma matriz fina por operação × grupo não foi construída nesta passagem.
- `plat.dominio`/subtipo do L2-10-a-dominios-subtipos (ver decisão 3).
- Bump de `tiles_versao` já é gravado em `plat.item.dados`, mas o consumidor (invalidação de cache
  do Martin, L2-01-b) ainda não existe — não é retrabalho, é ponto de integração já deixado pronto.
- Histórico/restauração de versão de feição (L2-03-d-historico-restauracao) não é gravado por esta
  rota; a coluna `versao` cobre só a concorrência otimista, não um log de mudanças.
