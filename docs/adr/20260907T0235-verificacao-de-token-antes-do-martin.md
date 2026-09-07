# Verificação de token antes do Martin (item L2-01-b-martin-tiles-vetoriais)

Nomeado por carimbo de tempo (ADR 0014): o número sequencial 0021+ pode colidir com outra trilha que
ainda não foi juntada nesta árvore.

## Contexto

O portão do item exige "pedido sem token = 401". A função de tile publicada pelo Martin
(`plat.camada_tile_garantir`, item L2-04-a) já recusa sem token — levanta `token_ausente` com
`RAISE EXCEPTION ... USING ERRCODE = '28000'`. O problema é o que o Martin faz com isso.

## Decisão

Conferido no código-fonte do Martin (tag `martin-v1.15.0`, `martin-core/src/tiles/postgres/errors.rs`):
`GetTileWithQueryError` — o erro que embrulha QUALQUER falha do Postgres dentro de uma função de tile —
classifica como `ErrorKind::Internal` incondicionalmente, sem olhar SQLSTATE nem mensagem. Não existe
opção de configuração que mude isso. Ou seja: **o Martin nunca devolve 401/403, mesmo quando a causa é
"sem token" — sempre 500.**

Por isso a validação de token acontece ANTES do Martin, no nginx, via `auth_request` apontando para
`GET /internal/tiles/verificar` (`app/tiles/rotas.py`), que chama a MESMA `plat.contexto_por_token` com o
MESMO papel de leitura (`plat_leitor`, nunca `plat_app`) que a função de tile chamaria, e traduz o
resultado em 204 (nginx deixa passar) ou 401/403 com o motivo em `X-Motivo-Recusa`.

## Dois achados do próprio adversário nesta rodada (corrigidos, não escondidos)

1. **Item vindo de query param do cliente.** A primeira versão da rota recebia `?item=<uuid>` do
   cliente e passava para `contexto_por_token`. Um token AMPLO ("camada:ler", sem uuid — formato de
   token de serviço/admin) de QUALQUER inquilino cobre `escopo_cobre('camada:ler', <qualquer uuid>)`
   porque essa função só compara o TEXTO do token, nunca verifica se o item pertence ao MESMO inquilino.
   Medido: token largo do inquilino B + item do inquilino A autenticava com 204. **Corrigido**: o item
   nunca vem do cliente — vem da TABELA que está no CAMINHO da própria URL (nginx repassa
   `$request_uri` original via `X-Original-Uri`), resolvida por `plat.item_da_tabela` (migração
   `20260907T0213_item_da_tabela.sql`, SECURITY DEFINER). Depois de resolver o item, a rota compara o
   inquilino que `contexto_por_token` devolveu contra o inquilino DONO do item — espelho exato do
   `IF ctx IS DISTINCT FROM tid` já hardcoded dentro da função de tile (defesa em duas camadas
   independentes, não uma só).
2. **Exaustão de piscina virando "token inválido".** Sob 200 pedidos em paralelo (refutação do
   adversário, camada de 472,8 mil feições, z0), a piscina de 1-2 conexões (`app/db_leitor.py`)
   esgotava e `pool.getconn()` levantava `PoolError` — uma exceção SEM `.diag`, que caía no
   `except Exception` genérico e virava "token_invalido" (401). Era SEGURO (nunca deixava passar), mas
   pelo motivo ERRADO, e reprovava pedidos legítimos sob carga normal. Corrigido: piscina 1-10 (ainda
   modesta sobre o `max_connections=100` compartilhado) e uma exceção específica antes da genérica, que
   só reclassifica como recusa de autenticação quando a exceção tem `.diag` (é erro do BANCO, não do
   cliente psycopg2) — senão é 503 (infraestrutura), nunca 401.

## O que fica de fora

A fonte "pmtiles" do Martin (camada estática/PMTiles, tippecanoe) NÃO passa por este mesmo
`auth_request`: o controle de acesso dela, no desenho deste item, é o do arquivo/bucket (L0-11), não
por-pedido-de-tile. Se um dia essa camada precisar do mesmo RLS por token, esta rota precisa aprender a
resolver "fonte pmtiles → item do catálogo" (hoje só resolve `t_<16 hex>` → `c_<16 hex>`).
