# Backup lógico por schema como fase 1, sem recuperação a ponto no tempo

Data: setembro de 2026. Item `L0-06-a-dump-logico`. Estado: aceito.

## Contexto

O Postgres desta instalação é compartilhado com outros serviços da casa e está com `archive_mode`
desligado (medido). Ligar arquivamento de WAL, que é o que permite recuperação a ponto no tempo, exige
reiniciar esse banco. O reinício é decisão de quem opera a máquina, não de quem constrói a plataforma.

Sem WAL arquivado sobram duas opções: parar de fazer backup até a decisão sair, ou fazer o backup que não
depende dela. A primeira deixa a plataforma sem cópia nenhuma por tempo indeterminado.

## Decisão

Fase 1: `pg_dump -Fc` por schema, um arquivo do `plat` e um arquivo por inquilino (`d_<slug>`), diário às
03:00, com sha256 e tamanho registrados em `plat.backup`.

Um arquivo por inquilino, e não um dump do banco inteiro, por três razões medidas no portão do item:
a restauração de um inquilino não toca nos outros; os dumps são paralelizáveis; e o tempo e o tamanho
ficam atribuídos a quem os gastou (`tempo_dump_s` e `bytes` por linha), que é o insumo da conta de custo
por inquilino.

O espaço é conferido antes de escrever qualquer byte. Falha de backup vira job `falhou` mais evento
`backup/falha` mais e-mail ao superadministrador: o modo de falha que não se aceita é o silêncio.

## Consequências

- A janela de perda é de até 24 horas. Isso é uma propriedade da fase 1 e tem de estar escrito em qualquer
  documento de serviço; não se promete ponto no tempo.
- Objeto do Garage não é recopiado, só manifestado (chave, sha256, bytes). A cópia de objeto é do item de
  arquivos e objetos, não deste.
- Cache de tile e dado referenciado ficam fora, como ficam no `webgisdr` da Esri e pela mesma razão.
- A fase 2 (arquivamento de WAL, ou réplica com atraso) continua aberta e depende da decisão sobre o
  reinício do banco compartilhado.

## Alternativas descartadas

- `pg_dumpall` do banco inteiro: mais simples, mas não restaura um inquilino sozinho e não atribui custo.
- `pg_basebackup`: cópia física; exige configuração de replicação no banco compartilhado, ou seja, cai na
  mesma decisão que a fase 1 evita.
- `rclone` para o destino externo: não está instalado na máquina. A cópia usa a mesma API S3 assinada em
  SigV4 que a plataforma já tem para o Garage — dependência zero a mais.
