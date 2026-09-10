"""Roteiros das tarefas filmadas (item L7-04-d-videos-por-tarefa).

Cada tarefa é uma lista de passos executados contra a instalação real pelo gerador
(scripts/videos/gerar.py) com o navegador gravando a sessão. O texto do passo vira legenda
(WebVTT em pt-BR, en e es) e narração sintética em pt-BR (voz livre piper; sem voz clonada).
A legenda só é registrada DEPOIS que a ação do passo aconteceu de verdade: um passo que não
existe na versão instalada derruba a geração, nunca entra no vídeo.

O campo `manual` é o começo do título de uma seção de MANUAL.md; o gerador confere que a
seção existe antes de gerar. Regras para o texto (regra de escrita de 03/09): uma ideia por
frase, sem metáfora, sem exclamação, sem nome de cliente, sem superlativo.
"""

# Ações disponíveis em `acoes`:
#   ir        -> {"ir": "/caminho"}                       abre a página e espera body[data-pronto=1]
#   clique    -> {"clique": "seletor css"}                clica e espera o navegador assentar
#   preencher -> {"preencher": ["seletor", "texto"]}      limpa e digita
#   selecionar-> {"selecionar": ["seletor", "valor"]}     escolhe opção de <select>
#   esperar   -> {"esperar": "seletor css"}               espera o seletor aparecer
#   esperar_js-> {"esperar_js": "função js"}              espera a função devolver verdadeiro (recebe variáveis)
#   teclar    -> {"teclar": ["seletor", "Enter"]}         tecla no elemento
#   pausa     -> {"pausa": 2.0}                           segundos de tela parada (respiro da narração)
#   api       -> {"api": ["POST", "/api/jobs", {...}]}    chamada com o cookie da sessão; guarda o JSON
#                                                          da resposta em variáveis da tarefa
#   detalhe   -> {"detalhe": "caminho-da-pagina"}         espera o corpo pronto sem medir tempo
# Texto de resposta pode ser interpolado no seletor com {nome}: o gerador resolve pelo último `api`.

TAREFAS = [
    {
        "id": "saude",
        "titulo": "Saúde do serviço",
        "manual": "1. Acesso e saúde do serviço",
        "passos": [
            {
                "acoes": [{"ir": "/"}, {"esperar": "#versao-numero"}],
                "texto": (
                    "A página inicial mostra a versão, o commit e o ambiente do serviço.",
                    "The home page shows the version, the commit and the environment of the service.",
                    "La página inicial muestra la versión, el commit y el ambiente del servicio.",
                ),
            },
            {
                "acoes": [{"esperar": "#saude-json"}, {"pausa": 2.5}],
                "texto": (
                    "O painel de saúde mostra o estado do banco de dados e da fila.",
                    "The health panel shows the state of the database and of the queue.",
                    "El panel de salud muestra el estado de la base de datos y de la fila.",
                ),
            },
            {
                "acoes": [{"pausa": 2.5}],
                "texto": (
                    "A página é pública para quem tem o endereço e não mostra dado de inquilino.",
                    "The page is public for whoever has the address and shows no tenant data.",
                    "La página es pública para quien tiene la dirección y no muestra dato de inquilino.",
                ),
            },
        ],
    },
    {
        "id": "entrar",
        "titulo": "Entrar",
        "manual": "2. Entrar",
        "passos": [
            {
                "acoes": [{"ir": "/entrar"}, {"esperar": "#login"}, {"pausa": 1.5}],
                "texto": (
                    "A tela de entrada pede o inquilino, o usuário e a senha.",
                    "The sign-in screen asks for the tenant, the user and the password.",
                    "La pantalla de entrada pide el inquilino, el usuario y la contraseña.",
                ),
            },
            {
                "acoes": [
                    {"preencher": ["#login", "{usuario}"]},
                    {"preencher": ["#senha", "senha-errada-de-propósito"]},
                    {"clique": "#entrar"},
                    {"esperar": "#aviso:not([hidden])"},
                    {"pausa": 2.5},
                ],
                "texto": (
                    "Uma senha errada é recusada com um aviso na tela.",
                    "A wrong password is refused with a message on the screen.",
                    "Una contraseña errada es rechazada con un aviso en la pantalla.",
                ),
            },
            {
                "acoes": [
                    {"preencher": ["#senha", "{senha}"]},
                    {"clique": "#entrar"},
                    {"esperar": "body[data-pronto='1']"},
                    {"pausa": 2.5},
                ],
                "texto": (
                    "Com a senha correta, o usuário entra e vê a barra lateral das telas.",
                    "With the correct password, the user signs in and sees the screen sidebar.",
                    "Con la contraseña correcta, el usuario entra y ve la barra lateral de las pantallas.",
                ),
            },
        ],
    },
    {
        "id": "conta",
        "titulo": "Minha conta",
        "manual": "3. Minha conta",
        "passos": [
            {
                "acoes": [{"ir": "/conta"}, {"esperar": "#form-senha"}],
                "texto": (
                    "A tela Minha conta reúne os dados, a senha e o segundo fator do usuário.",
                    "The My account screen gathers the user's data, password and second factor.",
                    "La pantalla Mi cuenta reúne los datos, la contraseña y el segundo factor del usuario.",
                ),
            },
            {
                "acoes": [{"esperar": "#tabela-sessoes"}, {"pausa": 2.5}],
                "texto": (
                    "A lista de sessões mostra onde a conta está aberta agora.",
                    "The session list shows where the account is open right now.",
                    "La lista de sesiones muestra dónde la cuenta está aberta ahora.",
                ),
            },
            {
                "acoes": [{"pausa": 2.5}],
                "texto": (
                    "Encerrar as outras sessões é uma ação de segurança da própria tela.",
                    "Closing the other sessions is a security action on the screen itself.",
                    "Cerrar las otras sesiones es una acción de seguridad de la propia pantalla.",
                ),
            },
        ],
    },
    {
        "id": "usuarios",
        "titulo": "Usuários",
        "manual": "4. Usuários",
        "passos": [
            {
                "acoes": [{"ir": "/admin/usuarios"}, {"esperar": "#tabela tbody"}],
                "texto": (
                    "A tela de usuários lista as contas do inquilino.",
                    "The users screen lists the accounts of the tenant.",
                    "La pantalla de usuarios lista las cuentas del inquilino.",
                ),
            },
            {
                "acoes": [
                    {"clique": "#novo"},
                    {"esperar": "#painel dialog[open]"},
                    {"preencher": ["#painel dialog[open] input[name='login']", "{novo_login}"]},
                    {"preencher": ["#painel dialog[open] input[name='nome']", "Usuário de demonstração"]},
                    {"selecionar": ["#painel dialog[open] select[name='perfil']", "visualizador"]},
                    {"clique": "#painel dialog[open] button[type='submit']"},
                    {"esperar": "#senha-temporaria"},
                    {"pausa": 3.0},
                ],
                "texto": (
                    "O usuário novo nasce com um perfil e recebe uma senha temporária, mostrada uma única vez.",
                    "The new user starts with a profile and receives a one-time temporary password.",
                    "El usuario nuevo nace con un perfil y recibe una contraseña temporal mostrada una única vez.",
                ),
            },
            {
                "acoes": [
                    {"clique": "#painel dialog[open] button:has-text('Fechar')"},
                    {"preencher": ["plat-busca input", "{novo_login}"]},
                    {"teclar": ["plat-busca input", "Enter"]},
                    {"esperar": "#tabela tbody tr:has-text('{novo_login}')"},
                    {"pausa": 2.5},
                ],
                "texto": (
                    "A busca da tela filtra a tabela pelo login.",
                    "The screen search filters the table by login.",
                    "La búsqueda de la pantalla filtra la tabla por el login.",
                ),
            },
        ],
    },
    {
        "id": "grupos",
        "titulo": "Grupos",
        "manual": "5. Grupos",
        "passos": [
            {
                "acoes": [{"ir": "/admin/grupos"}, {"esperar": "#tabela tbody"}],
                "texto": (
                    "Grupos organizam quem vê o conteúdo compartilhado.",
                    "Groups organize who sees the shared content.",
                    "Los grupos organizan quién ve el contenido compartido.",
                ),
            },
            {
                "acoes": [
                    {"clique": "#novo"},
                    {"esperar": "#painel dialog[open]"},
                    {"preencher": ["#painel dialog[open] input[name='nome']", "{grupo}"]},
                    {"preencher": ["#painel dialog[open] textarea[name='resumo']", "grupo do vídeo de demonstração"]},
                    {"selecionar": ["#painel dialog[open] select[name='visibilidade']", "inquilino"]},
                    {"clique": "#painel dialog[open] button[type='submit']"},
                    {"esperar": "#aviso[data-tipo='ok']"},
                    {"pausa": 2.5},
                ],
                "texto": (
                    "Um grupo novo nasce com a visibilidade escolhida na criação.",
                    "A new group starts with the visibility chosen at creation.",
                    "Un grupo nuevo nace con la visibilidad elegida en la creación.",
                ),
            },
            {
                "acoes": [
                    {"clique": "#tabela tbody tr:has-text('{grupo}') button:has-text('Abrir')"},
                    {"esperar": "#painel dialog[open]"},
                    {"clique": "#painel dialog[open] [role='tab']:has-text('Membros')"},
                    {"pausa": 3.0},
                ],
                "texto": (
                    "A aba de membros convida usuários do inquilino pela busca.",
                    "The members tab invites tenant users through the search.",
                    "La pestaña de miembros invita a usuarios del inquilino por la búsqueda.",
                ),
            },
        ],
    },
    {
        "id": "papeis",
        "titulo": "Papéis e privilégios",
        "manual": "6. Papéis e privilégios",
        "passos": [
            {
                "acoes": [{"ir": "/admin/papeis"}, {"esperar": "#tabela-perfis tbody tr"}],
                "texto": (
                    "A tela mostra os perfis padrão do inquilino e os privilégios de cada um.",
                    "The screen shows the tenant default profiles and the privileges of each one.",
                    "La pantalla muestra los perfiles predeterminados del inquilino y sus privilegios.",
                ),
            },
            {
                "acoes": [
                    {"clique": "#novo"},
                    {"esperar": "#painel dialog[open]"},
                    {"pausa": 3.0},
                ],
                "texto": (
                    "Um perfil novo reúne privilégios marcados na própria tela.",
                    "A new profile gathers privileges marked on the screen itself.",
                    "Un perfil nuevo reúne privilegios marcados en la propia pantalla.",
                ),
            },
            {
                "acoes": [
                    {"clique": "#painel dialog[open] button:has-text('cancelar')"},
                    {"pausa": 2.0},
                ],
                "texto": (
                    "A criação só acontece com o envio do formulário.",
                    "Creation only happens when the form is submitted.",
                    "La creación solo ocurre cuando el formulario se envía.",
                ),
            },
        ],
    },
    {
        "id": "tokens",
        "titulo": "Tokens de serviço",
        "manual": "7. Tokens de serviço",
        "passos": [
            {
                "acoes": [
                    {"ir": "/admin/tokens"},
                    {"clique": "#novo"},
                    {"esperar": "#painel dialog[open]"},
                    {"preencher": ["#painel dialog[open] input[name='nome']", "{token}"]},
                    # sem clique na caixa de escopo: catalogo:ler já vem marcada por padrão,
                    # e clicar nela desmarcaria, e o envio sem escopo é barrado pela tela
                    {"clique": "#painel dialog[open] button[type='submit']"},
                    {"esperar": "#token-valor"},
                    {"pausa": 3.0},
                ],
                "texto": (
                    "O token novo aparece uma única vez e começa pelo prefixo plat.",
                    "The new token appears once and starts with the prefix plat.",
                    "El token nuevo aparece una única vez y empieza con el prefijo plat.",
                ),
            },
            {
                "acoes": [
                    {"clique": "#painel dialog[open] button:has-text('Fechar')"},
                    {"clique": "#tabela tbody tr:has-text('{token}') button:has-text('Acessos')"},
                    {"esperar": "#painel dialog[open]"},
                    {"pausa": 2.5},
                ],
                "texto": (
                    "O registro do token guarda quando ele foi usado.",
                    "The token record keeps when it was used.",
                    "El registro del token guarda cuándo fue usado.",
                ),
            },
            {
                "acoes": [
                    {"clique": "#painel dialog[open] button:has-text('Fechar')"},
                    {"clique": "#tabela tbody tr:has-text('{token}') button:has-text('Revogar')"},
                    {"esperar": "plat-dialogo dialog[open]"},
                    {"clique": "plat-dialogo dialog[open] button:has-text('Revogar')"},
                    {"esperar": "#tabela tbody tr:has-text('{token}')"},
                    {"pausa": 2.5},
                ],
                "texto": (
                    "Revogado, o token deixa de funcionar na hora.",
                    "Once revoked, the token stops working at once.",
                    "Revocado, el token deja de funcionar de inmediato.",
                ),
            },
        ],
    },
    {
        "id": "log",
        "titulo": "Log de acesso",
        "manual": "8. Log de acesso",
        "passos": [
            {
                "acoes": [{"ir": "/admin/log"}, {"esperar": "#tabela tbody tr"}],
                "texto": (
                    "O log de acesso registra cada chamada feita pela sessão.",
                    "The access log records every call made by the session.",
                    "El registro de acceso anota cada llamada hecha por la sesión.",
                ),
            },
            {
                "acoes": [
                    {"selecionar": ["#filtros select[name='status']", "2xx"]},
                    {"clique": "#filtrar"},
                    {"pausa": 2.5},
                ],
                "texto": (
                    "O filtro por status isola as chamadas com resposta de sucesso.",
                    "The status filter isolates the calls with a success response.",
                    "El filtro por estado aísla las llamadas con respuesta de éxito.",
                ),
            },
            {
                "acoes": [{"clique": "#aba-eventos"}, {"esperar": "#tabela-eventos tbody tr"}, {"pausa": 2.5}],
                "texto": (
                    "A aba de eventos mostra as ações de administração do inquilino.",
                    "The events tab shows the tenant administration actions.",
                    "La pestaña de eventos muestra las acciones de administración del inquilino.",
                ),
            },
        ],
    },
    {
        "id": "tarefas",
        "titulo": "Tarefas",
        "manual": "9. Tarefas",
        "passos": [
            {
                "acoes": [
                    {"ir": "/tarefas"},
                    {"api": ["POST", "/api/jobs", {"tipo": "prova.progresso",
                                               "parametros": {"duracao_s": 12, "passos": 4}}],
                     "guardar_como": "job"},
                ],
                "texto": (
                    "Uma tarefa de prova entra na fila pelo painel de tarefas.",
                    "A proof task enters the queue on the tasks screen.",
                    "Una tarea de prueba entra en la fila por el panel de tareas.",
                ),
            },
            {
                "acoes": [{"esperar": "#lista-corpo tr[data-id='{job}']"}, {"pausa": 2.5}],
                "texto": (
                    "A linha aparece na lista sem recarregar a página.",
                    "The row appears in the list without reloading the page.",
                    "La línea aparece en la lista sin recargar la página.",
                ),
            },
            {
                "acoes": [
                    {"esperar": "#lista-corpo tr[data-id='{job}'][data-estado='concluido']"},
                    {"clique": "#lista-corpo tr[data-id='{job}']"},
                    {"esperar": "#detalhe[data-carregado='1']"},
                    {"pausa": 3.0},
                ],
                "texto": (
                    "Ao concluir, o detalhe guarda o resultado e o log da execução.",
                    "When it finishes, the detail keeps the result and the log of the run.",
                    "Al concluir, el detalle guarda el resultado y el registro de la ejecución.",
                ),
            },
        ],
    },
    {
        "id": "mapa",
        "titulo": "Mapa",
        "manual": "13. Mapa",
        "passos": [
            {
                "acoes": [{"ir": "/mapa"}, {"esperar": ".maplibregl-ctrl-zoom-in"}, {"pausa": 3.0}],
                "texto": (
                    "O mapa abre com a base cartográfica servida localmente.",
                    "The map opens with the basemap served locally.",
                    "El mapa abre con la base cartográfica servida localmente.",
                ),
            },
            {
                "acoes": [
                    {"clique": ".maplibregl-ctrl-zoom-in"},
                    {"pausa": 2.0},
                    {"clique": ".maplibregl-ctrl-zoom-in"},
                    {"pausa": 2.5},
                ],
                "texto": (
                    "O controle de zoom aproxima a vista e a escala acompanha.",
                    "The zoom control brings the view closer and the scale follows.",
                    "El control de zoom acerca la vista y la escala acompaña.",
                ),
            },
            {
                "acoes": [{"pausa": 2.5}],
                "texto": (
                    "O controle de escala mostra a proporção da vista atual.",
                    "The scale control shows the proportion of the current view.",
                    "El control de escala muestra la proporción de la vista actual.",
                ),
            },
        ],
    },
    {
        "id": "conexoes",
        "titulo": "Conexões externas",
        "manual": "18. Registro de camadas do acervo e modelo de conexão externa",
        "passos": [
            {
                "acoes": [
                    {"ir": "/conexoes"},
                    {"api": ["POST", "/api/conexoes",
                             {"tipo": "http", "nome": "{conexao_nome}",
                              "url": "https://api.github.com/repos/inexistente-demo/conexao/tambem-inexistente"}],
                     "guardar_como": "conexao"},
                    # a lista só lê ao abrir a página: recarrega para a linha nova aparecer
                    {"ir": "/conexoes"},
                ],
                "texto": (
                    "Uma conexão externa nasce com o estado nunca testada.",
                    "An external connection starts with the state never tested.",
                    "Una conexión externa nace con el estado nunca probada.",
                ),
            },
            {
                "acoes": [{"esperar": "tr[data-id='{conexao}']"}, {"pausa": 2.5}],
                "texto": (
                    "A lista mostra o nome, o tipo e o estado de cada conexão.",
                    "The list shows the name, the type and the state of each connection.",
                    "La lista muestra el nombre, el tipo y el estado de cada conexión.",
                ),
            },
            {
                "acoes": [
                    {"clique": "tr[data-id='{conexao}'] button:has-text('testar agora')"},
                    {
                        "esperar_js": "document.querySelector(\"tr[data-id='{conexao}'] .marcador\")"
                                      "?.textContent?.trim() === 'fora'",
                    },
                    {"pausa": 2.5},
                ],
                "texto": (
                    "Testar agora consulta o endereço e marca a conexão como fora.",
                    "Test now checks the address and marks the connection as down.",
                    "Probar ahora consulta la dirección y marca la conexión como fuera.",
                ),
            },
            {
                "acoes": [
                    {"clique": "tr[data-id='{conexao}'] button:has-text('histórico')"},
                    {"esperar": "plat-dialogo dialog[open]"},
                    {"pausa": 3.0},
                    {"clique": "plat-dialogo dialog[open] .dialogo-botoes button:has-text('fechar')"},
                ],
                "texto": (
                    "O histórico guarda cada teste com data e resultado.",
                    "The history keeps each test with date and result.",
                    "El histórico guarda cada prueba con fecha y resultado.",
                ),
            },
        ],
    },
]

# limpeza: o que a demonstração criou é apagado por API depois de a câmera parar
# (implementação em scripts/videos/gerar.py, função limpar).

# verbetes da regra de escrita (03/09) que o texto narrado nunca usa
PALAVRAS_PROIBIDAS = (
    "maquiagem", "acolchoado", "diamante", "viaja", "esquenta", "acender",
    "impressionante", "incrível", "robusto", "simplesmente", "apenas mágica",
)
FRASE_PROIBIDA = "você recebe"
