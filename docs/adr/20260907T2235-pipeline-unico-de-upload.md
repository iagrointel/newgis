# ADR 20260907T2235 — pipeline único de upload (item L7-03-a-antivirus-upload)

Estado: aceita (07/09/2026). Linha L7, decisão C8 do L7_CONCEITO ("Upload: um pipeline para tudo").

## Contexto

Havia três defesas soltas: assinatura por bytes mágicos em `POST /api/arquivos` (L7-03-b), prova de tipo no
upload retomável (`app/uploads/tipos.py`) e zip-bomba na ingestão (`conferir_zip`). Faltavam lista de tipos por
rota, teto por classe decidido antes do corpo, SVG sanitizado, antivírus, trilha da recusa e entrega segura.

## Decisões

1. **A política é por CLASSE de `POST /api/arquivos`** (`varredura_conteudo.POLITICAS`: objeto, anexo, foto_campo,
   imagem, csv), não por rota nova: a rota de arquivo cru já é a porta única de byte de cliente (as rotas de
   imagem por JSON/base64 reencodam por Pillow e não recebem byte cru). Classe desconhecida = `objeto`. Paridade
   com `uploadFileExtensionAllowedList` da Esri, mas por Content-Type provado pelos bytes, não por extensão.
2. **Teto por classe antes do corpo**: `Content-Length` acima = 413 sem consumir mensagem de corpo (medido: 0);
   cliente que mente cai no contador em streaming ao passar do teto (medido: 17 de 18 pedaços de 64 KiB lidos
   para um teto de 1 MiB — para no primeiro pedaço que excede).
3. **ClamAV opcional, por protocolo, sem dependência**: `MotorClamd` fala INSTREAM por socket unix ou TCP com a
   biblioteca padrão; entra na cadeia só com `PLAT_CLAMD`. Configurado e fora do ar = recusa (nunca "passa sem
   varrer"). O daemon real não cabe na RAM desta máquina (D21: ~1,3 GiB de assinaturas); a prova do portão usa
   um clamd de teste que fala o mesmo protocolo e devolve `FOUND` para o EICAR.
4. **Quarentena = registro, não armazenamento**: recusa pelo antivírus vira `arquivos/quarentena` em
   `plat.evento` (sha256, assinatura, classe, tipo, quem, de onde); o conteúdo é descartado. As demais recusas
   viram `arquivos/conteudo_recusado`. Guardar malware "em quarentena" custaria disco e criaria um objeto a
   proteger; o sha256 basta para reconhecer reenvio.
5. **SVG por lista branca** (`app/svg_seguro.py`, defusedxml): elementos e atributos fora da lista somem;
   `href` só `#id` ou `data:image/(png|jpeg|gif|webp)`; `style` com `url()` some. O que se grava é o SVG
   reconstruído, não o recebido (o sha256 muda — de propósito).
6. **Entrega**: `attachment` para tudo que não é imagem, `nosniff` e CSP `sandbox` sempre (o anexo `.html` abre
   como download; o polyglot GIF+HTML sai como `image/gif` sem contexto para executar).
7. **Zip acima do buffer único**: inspeção do diretório central por leitura em intervalo (`zip_remoto`, já
   existente) depois do `parte_concluir`; suspeito é apagado do Garage e recusado.

## Consequências

- `text/plain` aceita binário genérico por dentro (texto nunca é executado; testes do L0-11 mandam bytes
  aleatórios como texto) — quem olha por dentro é o antivírus, quando ligado.
- Não coberto: varredura dentro de arquivos compostos (entradas do KMZ), `.dbf` malformado que estoura o GDAL
  (é da ingestão, que roda em subprocesso do worker com RLIMIT — a refutação do item aponta para lá, não para
  o upload), instalação do ClamAV real (D21).
