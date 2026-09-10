# Importação de metadado ISO 19139: o XSD é parecer, não porteiro

Item `L0-09-c-xml-iso-validacao`. Decisão de arquitetura tomada ao ler metadado REAL, não a norma.

## Contexto

A exportação (`GET /api/itens/{id}/metadado.xml`, item L0-09-metadado-catalogo) já gerava ISO 19139/GMD e
validava contra o XSD oficial do ISO/TC 211 em cache local. Faltava o caminho de volta: receber um XML ISO de
fora — de um catálogo brasileiro, de um ArcGIS, de um GeoNetwork — e transformar isso em item da plataforma.

## Decisão 1: validar contra o XSD e mesmo assim aceitar

O primeiro registro que se leu do catálogo aberto da INDE (produtor IBGE, obtido do CSW de
metadados.inde.gov.br e guardado em `tests/dados/inde_iso19139_carta_imagem.xml`) **não valida** contra o XSD
oficial: 20 erros, entre ordem de elementos trocada e elementos que não existem na norma (`elipsoide`,
`parametros`, `sistemaDeProjecao`, `UF_TypeCode`, `nameFormat`), que são extensões do Perfil MGB. O documento
foi produzido por ArcGIS 10.3 (o próprio metadado diz isso em `environmentDescription`).

Recusar esse documento seria recusar o metadado que o catálogo nacional publica. Então:

- XML malformado, maior que `limites.METADADO_XML_BYTES_MAX` ou com raiz diferente de `gmd:MD_Metadata`
  responde **422 com linha e coluna**;
- XML bem formado que não valida no XSD **entra**, e os erros saem em `avisos_xsd`, cada um com linha e coluna;
- `?estrito=1` transforma esses mesmos avisos em 422, para quem quer o rigor da norma.

## Decisão 2: o que não tem onde ser guardado vira relatório, não armazém novo

Do registro da INDE, 22 campos têm destino na plataforma (colunas do item, `dados.procedencia` e
`plat.item.metadado_iso`) e 69 caminhos distintos não têm — telefone, endereço postal, catálogo de feições,
representação espacial. Esses saem em `nao_coube`, com caminho, linha, quantas vezes apareceram e um exemplo.
Inventar uma gaveta para cada um seria criar metadado que nada lê e ninguém mantém (D17: procedência errada é
pior que procedência nenhuma).

## Decisão 3: uma coluna de metadado, não duas

O que a ISO traz e não tem coluna própria (contato, sistema de referência, formato de distribuição, extensão
declarada) vai para `plat.item.metadado_iso`, a MESMA coluna, com as MESMAS chaves, que o item irmão
`L0-09-b-editor-iso-mgb` desenhou para o editor do Perfil MGB. A migração desta trilha é idêntica à dele e
idempotente: quem entrar primeiro cria a coluna, o segundo não faz nada. As listas de código da ISO usadas na
leitura (`CI_RoleCode`, `MD_MaintenanceFrequencyCode`) ficam em `app/catalogo/metadado.py`; quando o ramo do
L0-09-b entrar, o módulo dele importa daqui em vez de repetir a lista.

## Decisão 4: o corpo é JSON, não `application/xml`

A defesa de CSRF sob cookie (ADR 0002 seção 5.3) só aceita corpo `application/json` em escrita. O XML vai
inteiro no campo `xml` do corpo JSON. Afrouxar a defesa de toda a API para poupar um `JSON.stringify` nesta
rota seria trocar segurança por comodidade.

## Decisão 5: a leitura não é um segundo módulo

`analisar` mora em `app/catalogo/metadado.py`, junto da exportação, e reusa dela três coisas: o XSD em cache,
a tabela de rótulos de procedência e o mapa de `MD_ProgressCode`. É essa reutilização que faz a ida e volta
fechar sem perda — `metadado.diferencas(perfil_do_item(row), analisar(gerar_xml(row)))` é vazia porque as duas
pontas leem a mesma tabela, não porque alguém acertou duas listas separadas.

## O que fica de fora, dito por nome

- **ISO 19115-3 (mdb)**: nem exportação nem importação. O Perfil MGB e o GeoNetwork da INDE consomem 19139.
- **Botão de importar na tela do item**: a rota existe e o download já existia; a tela é do item de interface.
- **Sincronização de volta**: importar não cria item novo, só preenche um item existente.
