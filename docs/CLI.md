# Linha de comando `plat`

Gerado por `plat docs` a partir de `app/cli/principal.py` (não editar à mão).

`plat` administra a plataforma pelo terminal: inquilino, usuário, token, camada, job, evento, segredo e
saúde. Todo comando fala com a mesma API que o navegador usa, com a mesma sessão e os mesmos privilégios,
e por isso grava os mesmos eventos de auditoria que a tela gravaria.

- Ponto de entrada: `scripts/plat` no repositório; `venv/bin/plat` depois do `install.sh`.
- Credenciais: arquivo modo 600 com linhas `inquilino login senha` (`--credenciais`, padrão
  `tests/credenciais.txt`; variável `PLAT_CREDENCIAIS_ARQUIVO`).
- Segundo fator: arquivo modo 600 com `inquilino login segredo` (`--totp-arquivo`).
- **Senha nunca entra por argumento** — `--senha` e parentes são recusados de propósito, porque
  argumento aparece em `ps` e no journal do `sudo`. Use `--senha-stdin` ou `--senha-arquivo`.
- `--json` imprime a resposta da API como ela é, para uso em script.
- Saída: 0 sucesso, 2 falha prevista (mensagem em uma linha, sem rastro de pilha), 130 interrupção.

## `plat`

```
uso: plat [-h] [--base-url BASE_URL] [--credenciais CREDENCIAIS]
            [--totp-arquivo TOTP_ARQUIVO] [--inquilino INQUILINO] [--json]
            [--configurar-2fa] [--tempo-limite TEMPO_LIMITE]
            GRUPO ...

Administração da plataforma pela linha de comando: inquilino, usuário, token,
camada, job, evento, segredo e saúde. Todo comando fala com a mesma API que o
navegador usa, com a mesma sessão e os mesmos privilégios — nada aqui escreve
no banco por fora.

argumentos posicionais:
  GRUPO
    inquilino           inquilinos da plataforma (exige o operador da
                        plataforma)
    usuario             usuários de um inquilino
    token               tokens de serviço do inquilino
    camada              importação de camada vetorial
    job                 fila de trabalhos do inquilino
    evento              registro de eventos do inquilino
    saude               consulta /saude da API
    segredo             rotação de segredo e certificado (repassa ao script do
                        item L7-19)
    docs                regenera docs/CLI.md a partir desta descrição de
                        comandos

opções:
  -h, --ajuda, --help   mostra esta ajuda e sai
  --base-url BASE_URL   endereço da API; sem ele vale PLAT_CLI_URL,
                        PLAT_URL_PUBLICA ou http://127.0.0.1:8150
  --credenciais CREDENCIAIS
                        arquivo modo 600 com 'inquilino login senha'; sem ele
                        vale PLAT_CREDENCIAIS_ARQUIVO ou tests/credenciais.txt
  --totp-arquivo TOTP_ARQUIVO
                        arquivo modo 600 com o segredo do segundo fator; sem
                        ele vale PLAT_CREDENCIAIS_TOTP_ARQUIVO ou
                        tests/credenciais_totp.txt
  --inquilino INQUILINO
                        identificador do inquilino em que o comando age
  --json                imprime a resposta da API em JSON
  --configurar-2fa      quando a conta ainda precisa configurar o segundo
                        fator, configura agora e guarda o segredo no arquivo
                        de --totp-arquivo (modo 600)
  --tempo-limite TEMPO_LIMITE
                        segundos de espera por chamada (padrão: 60)

As credenciais saem de um arquivo modo 600 no formato 'inquilino login senha'
(--credenciais). Senha NUNCA entra por argumento: use --senha-stdin ou
--senha-arquivo.
```

## `plat inquilino`

```
uso: plat inquilino [-h] AÇÃO ...

argumentos posicionais:
  AÇÃO
    listar    lista os inquilinos
    criar     cria um inquilino com o seu primeiro administrador
    suspender
              suspende o inquilino (ninguém entra até reativar)
    reativar  reativa um inquilino suspenso
    cota      mostra ou muda a cota de armazenamento e de usuários

opções:
  -h, --help  mostra esta ajuda e sai
```

### `plat inquilino listar`

```
uso: plat inquilino listar [-h]

opções:
  -h, --help  mostra esta ajuda e sai
```

### `plat inquilino criar`

```
uso: plat inquilino criar [-h] --slug SLUG --nome NOME --admin-login
                            ADMIN_LOGIN --admin-nome ADMIN_NOME
                            [--config CONFIG] [--se-nao-existir]
                            [--senha-stdin | --senha-arquivo ARQUIVO]

opções:
  -h, --help            mostra esta ajuda e sai
  --slug SLUG           identificador curto (minúsculas, dígitos e hífen)
  --nome NOME           nome de exibição
  --admin-login ADMIN_LOGIN
                        login do primeiro administrador
  --admin-nome ADMIN_NOME
                        nome do primeiro administrador
  --config CONFIG       configuração inicial em JSON (centro, zoom, cotas)
  --se-nao-existir      não falha quando o inquilino já existe (é o que o
                        install.sh usa)
  --senha-stdin         lê a senha da entrada padrão (uma linha)
  --senha-arquivo ARQUIVO
                        lê a senha da primeira linha deste arquivo, que
                        precisa estar em modo 600
```

### `plat inquilino suspender`

```
uso: plat inquilino suspender [-h] alvo

argumentos posicionais:
  alvo        id ou identificador do inquilino

opções:
  -h, --help  mostra esta ajuda e sai
```

### `plat inquilino reativar`

```
uso: plat inquilino reativar [-h] alvo

argumentos posicionais:
  alvo        id ou identificador do inquilino

opções:
  -h, --help  mostra esta ajuda e sai
```

### `plat inquilino cota`

```
uso: plat inquilino cota [-h] [--bytes BYTES] [--usuarios USUARIOS]

opções:
  -h, --help           mostra esta ajuda e sai
  --bytes BYTES        nova cota de armazenamento, em bytes
  --usuarios USUARIOS  nova cota de usuários
```

## `plat usuario`

```
uso: plat usuario [-h] AÇÃO ...

argumentos posicionais:
  AÇÃO
    listar         lista os usuários do inquilino
    criar          cria usuário
    redefinir-senha
                   gera nova senha temporária e encerra as sessões do usuário
    desabilitar    desativa a conta sem apagá-la
    reabilitar     reativa uma conta desativada

opções:
  -h, --help       mostra esta ajuda e sai
```

### `plat usuario listar`

```
uso: plat usuario listar [-h] [--limite LIMITE]

opções:
  -h, --help       mostra esta ajuda e sai
  --limite LIMITE  quantos por página (padrão: 50)
```

### `plat usuario criar`

```
uso: plat usuario criar [-h] --login LOGIN --nome NOME
                          [--perfil {admin,editor,visualizador,campo}]
                          [--email EMAIL]
                          [--senha-stdin | --senha-arquivo ARQUIVO]

opções:
  -h, --help            mostra esta ajuda e sai
  --login LOGIN
  --nome NOME
  --perfil {admin,editor,visualizador,campo}
                        padrão: visualizador
  --email EMAIL
  --senha-stdin         lê a senha da entrada padrão (uma linha)
  --senha-arquivo ARQUIVO
                        lê a senha da primeira linha deste arquivo, que
                        precisa estar em modo 600
```

### `plat usuario redefinir-senha`

```
uso: plat usuario redefinir-senha [-h] alvo

argumentos posicionais:
  alvo        id ou login

opções:
  -h, --help  mostra esta ajuda e sai
```

### `plat usuario desabilitar`

```
uso: plat usuario desabilitar [-h] alvo

argumentos posicionais:
  alvo        id ou login

opções:
  -h, --help  mostra esta ajuda e sai
```

### `plat usuario reabilitar`

```
uso: plat usuario reabilitar [-h] alvo

argumentos posicionais:
  alvo        id ou login

opções:
  -h, --help  mostra esta ajuda e sai
```

## `plat token`

```
uso: plat token [-h] AÇÃO ...

argumentos posicionais:
  AÇÃO
    listar    lista os tokens
    criar     cria token (o valor só aparece nesta saída)
    revogar   revoga o token

opções:
  -h, --help  mostra esta ajuda e sai
```

### `plat token listar`

```
uso: plat token listar [-h] [--todos]

opções:
  -h, --help  mostra esta ajuda e sai
  --todos     todos os tokens do inquilino, não só os seus
```

### `plat token criar`

```
uso: plat token criar [-h] --nome NOME --escopo ESCOPO
                        [--validade-dias VALIDADE_DIAS]

opções:
  -h, --help            mostra esta ajuda e sai
  --nome NOME
  --escopo ESCOPO       pode repetir; ex.: --escopo catalogo:ler
  --validade-dias VALIDADE_DIAS
```

### `plat token revogar`

```
uso: plat token revogar [-h] id

argumentos posicionais:
  id

opções:
  -h, --help  mostra esta ajuda e sai
```

## `plat camada`

```
uso: plat camada [-h] AÇÃO ...

argumentos posicionais:
  AÇÃO
    importar  sobe o arquivo, inspeciona e publica a camada

opções:
  -h, --help  mostra esta ajuda e sai
```

### `plat camada importar`

```
uso: plat camada importar [-h] [--crs SRID] --formato FORMATO
                            [--titulo TITULO] [--codificacao CODIFICACAO]
                            [--sem-esperar] [--espera ESPERA]
                            arquivo

argumentos posicionais:
  arquivo               caminho do arquivo local (GeoPackage, GeoJSON,
                        shapefile em zip, CSV)

opções:
  -h, --help            mostra esta ajuda e sai
  --crs SRID            sistema de coordenadas a confirmar quando a inspeção
                        perguntar
  --formato FORMATO     formato do arquivo: gpkg, geojson, csv ou
                        shapefile.zip (a API recusa o que não souber ler, com
                        a lista dos aceitos na mensagem)
  --titulo TITULO       título do item de arquivo (padrão: nome do arquivo)
  --codificacao CODIFICACAO
                        codificação do texto quando a inspeção perguntar
  --sem-esperar         devolve assim que a inspeção é enfileirada
  --espera ESPERA       segundos de espera por job (padrão: 180)
```

## `plat job`

```
uso: plat job [-h] AÇÃO ...

argumentos posicionais:
  AÇÃO
    listar    lista os jobs
    cancelar  cancela um job
    repetir   cria um job novo com a mesma entrada

opções:
  -h, --help  mostra esta ajuda e sai
```

### `plat job listar`

```
uso: plat job listar [-h] [--estado ESTADO] [--limite LIMITE]

opções:
  -h, --help       mostra esta ajuda e sai
  --estado ESTADO  filtra por estado (pendente, rodando, concluido, ...)
  --limite LIMITE
```

### `plat job cancelar`

```
uso: plat job cancelar [-h] id

argumentos posicionais:
  id

opções:
  -h, --help  mostra esta ajuda e sai
```

### `plat job repetir`

```
uso: plat job repetir [-h] id

argumentos posicionais:
  id

opções:
  -h, --help  mostra esta ajuda e sai
```

## `plat evento`

```
uso: plat evento [-h] AÇÃO ...

argumentos posicionais:
  AÇÃO
    exportar  exporta os eventos em JSON ou CSV

opções:
  -h, --help  mostra esta ajuda e sai
```

### `plat evento exportar`

```
uso: plat evento exportar [-h] [--desde DESDE] [--ate ATE] [--tipo TIPO]
                            [--formato {json,csv}] [--saida SAIDA]
                            [--pagina PAGINA] [--maximo MAXIMO]

opções:
  -h, --help            mostra esta ajuda e sai
  --desde DESDE         início da janela (ISO 8601)
  --ate ATE             fim da janela (ISO 8601)
  --tipo TIPO           filtra por tipo de evento
  --formato {json,csv}
  --saida SAIDA         arquivo de destino (padrão: saída padrão)
  --pagina PAGINA       tamanho da página pedida à API
  --maximo MAXIMO       teto de eventos exportados
```

## `plat saude`

```
uso: plat saude [-h]

opções:
  -h, --help  mostra esta ajuda e sai
```

## `plat segredo`

```
uso: plat segredo [-h] AÇÃO ...

argumentos posicionais:
  AÇÃO
    rotacionar
              rotaciona um segredo; veja docs/RUNBOOKS/segredos.md

opções:
  -h, --help  mostra esta ajuda e sai
```

### `plat segredo rotacionar`

```
uso: plat segredo rotacionar [-h] ...

argumentos posicionais:
  resto       nome do segredo e opções repassados a
              scripts/segredo_rotacionar.py

opções:
  -h, --help  mostra esta ajuda e sai
```

## `plat docs`

```
uso: plat docs [-h] [--destino DESTINO]

opções:
  -h, --help         mostra esta ajuda e sai
  --destino DESTINO  caminho do arquivo gerado (padrão: docs/CLI.md)
```
