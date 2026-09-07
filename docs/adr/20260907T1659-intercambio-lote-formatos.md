# ADR (carimbo 20260907T1659): importação e exportação em lote nos formatos do GDAL (L6-02-o)

## Contexto

O item pede LOTE — importar/exportar vários arquivos ou camadas numa chamada — nos formatos que o GDAL desta
máquina lê e escreve (medido em `ogrinfo --formats`, GDAL 3.8.4), com o mapeamento de campos/CRS e a
exportação do inquilino inteiro (escrow, L0-06). Duas peças já existiam/estavam em curso quando este item
começou: `L0-04-ingest-vetor` (funil de 1 arquivo: upload → inspeção → proposta → confirmação → carga) e
`L0-04-h-exportar` (exportação de 1 camada em 11 formatos), esta última pronta mas ainda não integrada à
`master` (ramo próprio `wt/l004h-exportar-limpo`). Um agente Kimi K3 já havia escrito, sem integrar,
`app/intercambio/` (exportação por camada em formatos ADICIONAIS — geojsonseq, filegdb.zip, mbtiles,
pmtiles — e o escrow do inquilino), preservado por `RESGATE` (commit `9746760`).

## Decisão

1. **Trazer L0-04-h para este ramo por `git merge`** (não reescrever o motor de exportação): o merge foi
   limpo (sem conflito), e o item reusa o módulo inteiro (`app/exportacao/*`) como está. A parte NOVA que
   este item acrescenta é só o que L0-04-h não cobre: formatos extra e o escrow multi-camada.
2. **Manter `app/intercambio/` do Kimi como o módulo do que L0-04-h não oferece**, em vez de reescrever: o
   código já calcula avisos de fidelidade ANTES de rodar (`app/intercambio/avisos.py`, o Warning do GDAL
   nunca fica escondido), isola por RLS-na-string-de-conexão (mesmo padrão de `app/exportacao/motor.py`) e
   já tinha o escrow do inquilino pronto. Achados corrigidos nesta integração: falta de
   `apagado_em IS NULL` nas 3 consultas de camada (uma camada na lixeira ainda podia ser exportada) e
   colisão de nome de constante (`EXPORTACAO_MEMORIA_MB`/`TIMEOUT_S` definidos duas vezes com o mesmo
   valor — renomeado para `INTERCAMBIO_MEMORIA_MB`/`TIMEOUT_S`).
3. **Importação em lote é AGRUPAMENTO, não outro funil**: `plat.intercambio_lote_importacao` só guarda o
   total pedido; a coluna `lote_id` em `plat.importacao` agrupa. `app/intercambio/lote_importar.py` chama
   em loop as funções extraídas de `app/ingestao/rotas.py` (`preparar_importacao`, `preparar_confirmacao`,
   `carregar_importacao`) — a prova de conteúdo, a inspeção e a carga continuam sendo exatamente as de
   `L0-04-ingest-vetor`. A criação do lote é UMA transação (item malformado no meio derruba o lote inteiro,
   antes de qualquer job na fila).
4. **FileGDB "abre no QGIS" é prova estrutural, não abertura real**: esta máquina não tem QGIS (nem
   ambiente gráfico — mesma limitação já registrada para o Chrome headless). QGIS delega a leitura de
   FileGDB ao driver `OpenFileGDB` do GDAL (não traz SDK Esri próprio); a prova é reabrir o pacote com esse
   MESMO driver e bater a contagem de feições. Registrado como limitação honesta, não como "feito" pleno.
5. **Paridade é "temos/não temos" contra a extensão Data Interoperability** (leitura/escrita ampla via FME),
   não contra "Export Item" (isso já é a seção de L0-04-h em `docs/PARIDADE.md`). GeoParquet nativo, Oracle
   (OCI) e MSSQLSpatial ficam de fora com o motivo declarado (driver ausente ou sem servidor para provar).

## Consequências

- O ramo carrega a HISTÓRIA de `wt/l004h-exportar-limpo` (merge, não cherry-pick): quando o gerente juntar
  os dois na `master`, a base comum evita reconciliação manual de `app/exportacao/*`.
- Entrada (importação) continua limitada aos 4 formatos de `L0-04-ingest-vetor` (shapefile.zip, gpkg,
  geojson, csv); ampliar para KML/DXF/XLSX/FileGDB na ENTRADA é escopo do item-irmão
  `L0-04-e-formatos-cad` e sucessores — citado como "fora" na tabela de paridade, não fingido feito.
- `plat.intercambio_exportacao` (Kimi) e `plat.exportacao` (L0-04-h) coexistem: são registros de DUAS
  operações diferentes (exportação avulsa de 1 camada em 11 formatos vs. exportação em formatos extra +
  escrow do inquilino). Um `item_id` de camada pode aparecer nas duas tabelas; isso é esperado, não
  duplicação de dado.
