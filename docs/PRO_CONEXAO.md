# Conexão de armazenamento em nuvem no ArcGIS Pro e no QGIS/GDAL

Este documento é o passo a passo do arquivo `.acs` que o item L1-02-e ("Porta 2") exige. Ele descreve
como abrir, num cliente de mesa, os COG que a plataforma guarda para o seu inquilino, usando uma
credencial só-leitura do seu próprio balde.

Há duas portas para o mesmo dado, e elas servem a coisas diferentes.

| porta | o que é | quando usar |
|---|---|---|
| Porta 1 | COG por HTTPS, com token de serviço no caminho (`/svc/<token>/cog/<item>/<asset>.tif`) | QGIS, navegador, qualquer cliente que aceite URL; dá acesso a UM item |
| Porta 2 | endpoint S3 com credencial própria do inquilino | ArcGIS Pro, `gdalinfo`, `/vsis3/`; dá acesso a TODO o balde do inquilino |

A Porta 2 existe porque o ArcGIS Pro não abre um COG por URL direta. O que ele abre é um armazenamento
em nuvem descrito num arquivo `.acs`, criado pela ferramenta `Create Cloud Storage Connection File`.

## Aviso antes de pedir a credencial

A credencial da Porta 2 abre **todo objeto do balde do inquilino**, em leitura. Ela não distingue item.
Para dar a alguém acesso a um item só, use a Porta 1 com token de serviço de escopo por lista
(item L1-02-b), não esta.

A credencial é somente-leitura: com ela não se escreve nem se apaga nada. A chave de escrita do balde
não sai deste servidor por rota nenhuma.

## Passo 1 — obter a credencial

Entre na plataforma com a sua sessão (não com token de serviço) e chame:

    GET /api/imagens/conexao-s3

Três travas deliberadas nessa rota: ela exige sessão, exige o privilégio `conteudo.publicar_camada` e
devolve sempre a chave de leitura, nunca a de escrita. A resposta não é guardada em cache
(`Cache-Control: no-store`) e o segredo não entra no registro de eventos: o evento grava o balde e o
modo, nada mais.

A resposta traz os campos que os dois clientes pedem:

| campo | serve para |
|---|---|
| `endpoint` | endereço do serviço S3, com esquema |
| `endpoint_sem_esquema` | o mesmo endereço sem `https://`, que é a forma que o GDAL espera em `AWS_S3_ENDPOINT` |
| `regiao` | região S3 a declarar |
| `balde` | nome do balde do seu inquilino |
| `access_key_id` e `secret_access_key` | a credencial só-leitura |
| `estilo_endereco` | sempre `path`: o balde vai no caminho, nunca no subdomínio |
| `exemplo_gdal` | um caminho `/vsis3/` já montado |

## Passo 2 — ArcGIS Pro, arquivo `.acs`

Na caixa de ferramentas, abra `Data Management Tools > Storage > Create Cloud Storage Connection File`
e preencha:

| campo da ferramenta | valor |
|---|---|
| Connection File Location | a pasta onde o `.acs` vai ficar |
| Connection File Name | um nome à sua escolha, por exemplo `plataforma` |
| Service Provider | `AMAZON` |
| Bucket (Container) Name | o `balde` da resposta |
| Access Key ID | o `access_key_id` da resposta |
| Secret Access Key | o `secret_access_key` da resposta |
| Region | a `regiao` da resposta |
| Service End Point | o `endpoint_sem_esquema` da resposta |
| Provider Options | `AWS_VIRTUAL_HOSTING` = `FALSE`, e `AWS_HTTPS` = `YES` se o endpoint for `https://`, `NO` se for `http://` |

`AWS_VIRTUAL_HOSTING = FALSE` não é opcional. O armazenamento desta plataforma fala S3 com o balde no
caminho; sem essa opção o Pro monta o endereço com o balde como subdomínio e a conexão não resolve.

Feito o `.acs`, o COG aparece em `Add Data`, dentro da conexão, como um raster comum.

## Passo 3 — QGIS, `gdalinfo` e qualquer coisa que use GDAL

Aqui não há arquivo: são quatro variáveis de ambiente e um caminho.

    export AWS_ACCESS_KEY_ID=<access_key_id da resposta>
    export AWS_SECRET_ACCESS_KEY=<secret_access_key da resposta>
    export AWS_S3_ENDPOINT=<endpoint_sem_esquema da resposta>
    export AWS_VIRTUAL_HOSTING=FALSE
    export AWS_HTTPS=YES        # NO, se o endpoint for http://
    gdalinfo /vsis3/<balde>/<chave-do-objeto>

O campo `exemplo_gdal` da resposta já traz o `/vsis3/<balde>/` montado; falta só a chave do objeto, que
é o `href` do asset no catálogo STAC do item.

## O que foi medido, e o que não foi

Medido em 18/09/2026, contra o armazenamento de verdade, em
`tests/api/imagens/test_l102e_conexao_s3.py` (6 testes passando):

- a credencial entregue lê o próprio balde: `HEAD` e `GET` devolvem os bytes gravados;
- a mesma credencial não escreve: `PUT` no próprio balde é recusado;
- a credencial do inquilino A não abre o balde do inquilino B: `GET` é recusado com 403;
- um token de serviço não obtém a credencial: a rota exige sessão;
- o segredo não aparece no registro de eventos;
- a resposta vem com `Cache-Control: no-store`.

A leitura é medida por `GET` e `HEAD`, não por listagem de balde, porque é isso que o `/vsis3/` faz: o
GDAL abre um COG com um `HEAD` para o tamanho e uma sequência de `GET` com intervalo de bytes. Listar o
balde não é necessário para abrir um objeto cujo caminho já se conhece.

Não foi medido: o ArcGIS Pro em si. Esta máquina não tem o programa, que exige licença nominal e
credencial de organização (a mesma razão registrada em `docs/TESTE_PARCEIRO_PRO_AGOL.md`). Os passos da
seção 2 vêm da documentação da ferramenta `Create Cloud Storage Connection File` e do comportamento do
mesmo driver S3 do GDAL que a seção 3 usa e que foi medido. Enquanto ninguém executar o protocolo de
`docs/TESTE_PARCEIRO_PRO_AGOL.md` e devolver a evidência, a linha do ArcGIS Pro na matriz de
conformidade fica **não medida**, nunca "suportado".
