# 20260907T2245 — Exportação completa do inquilino: formato aberto, e o que ela NÃO leva

Item `L0-06-d-exportar-inquilino`. Aceito.

## Contexto

A seção 17.4 da especificação promete "escrow prático": o cliente tem de conseguir sair da instalação com o
que é dele, em formato que se abra sem a nossa plataforma. O backup lógico do item L0-06-a resolve outro
problema — é `pg_dump` por schema, para a CASA restaurar; ele não serve ao cliente (traz estrutura interna,
não abre em nenhum SIG, e no caso dos schemas compartilhados nem separa inquilino).

## Decisão

Um pacote zip com quatro componentes, montado por um job (`inquilino.exportar`), pedido em
`POST /api/inquilino/exportar` e limitado a uma execução por dia por inquilino:

- `dados.gpkg` — um GeoPackage com uma camada por item `camada_vetorial` hospedado, escrito pelo `ogr2ogr`
  com a mesma disciplina de segurança da exportação de camada (o inquilino entra na conexão, a RLS filtra;
  nenhum `WHERE` de inquilino escrito à mão). O metadado do item e o estilo MapLibre ligado a ele vão DENTRO
  do arquivo, nas tabelas `gpkg_metadata`/`gpkg_metadata_reference` da norma, registradas em
  `gpkg_extensions`. Assim o GeoPackage sozinho já se explica em qualquer leitor conforme.
- `catalogo.json` — itens, pastas, grupos (com membros), compartilhamentos, relações e usuários, validado por
  um JSON Schema publicado em `docs/esquemas/exportacao_inquilino.schema.json`. O esquema tem
  `additionalProperties: false` no usuário, o que faz um `senha_hash` que vazasse para o documento REPROVAR o
  teste: a garantia de não exportar segredo de autenticação é checável, não uma promessa no comentário.
- `arquivos.zip` — os objetos do bucket, um por item, lidos em blocos.
- `manifesto.json` — sha256 e tamanho de cada componente.

## Alternativas descartadas

- **`pg_dump` do schema do inquilino no lugar do GeoPackage.** Sai mais rápido e é fiel, mas só reabre em
  PostgreSQL/PostGIS da mesma versão maior — é o oposto de "sem depender de nós". O dump lógico continua
  existindo, para a casa; este item é para o cliente.
- **Um formato só (só GeoPackage, com o catálogo em tabela de atributo).** Caberia, mas transformaria o
  catálogo num anexo obscuro. JSON com esquema publicado é o que um terceiro consegue ler e conferir.
- **Exportar também o conteúdo das camadas de volta para o PostgreSQL na importação.** Fora do escopo: quem
  lê GeoPackage e escreve tabela é a ingestão (L0-04-a). O importador deste item recria o CATÁLOGO com os
  mesmos uuids, que é o que prova a portabilidade; compor os dois é trabalho de quem for montar a migração
  entre instalações.

## Limites honestos

- O importador não repõe os arquivos no bucket de destino: o item importado continua apontando para a chave
  do objeto de origem, que pode não existir lá.
- Usuário e dono: o catálogo carrega os usuários da origem, mas na importação tudo nasce com um dono único do
  destino. Mapear usuário a usuário é decisão de produto, não de formato.
- A estimativa de tamanho usa `pg_total_relation_size` (inclui índice e TOAST) e ignora a compressão do zip:
  ela superestima de propósito, porque o erro que enche disco é estimar para menos.
