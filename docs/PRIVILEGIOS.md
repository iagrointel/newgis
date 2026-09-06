# Privilégios da plataforma

Gerado de `plat.privilegio` + `plat.perfil_privilegio` (o banco vivo) por `docs/gerar_privilegios.py` (`make privilegios`) — item L0-07-b-papeis-privilegios; não editar à mão. O vocabulário é fechado: toda rota autenticada declara um destes nomes (ou uma composição `a|b`) em `x-privilegio` no OpenAPI, e `plat.tem(privilegio)`/`plat.privilegios_de(usuario_id)` são a única forma de perguntar, em rota e em RLS (ADR 0002 seções 3, 12.1). `app/auth/privilegios.py` espelha esta mesma lista em Python (para cálculo de `perfil_minimo` sem consulta); `tests/api/test_privilegios_declarados.py` prova que os dois batem, nome a nome, teto a teto.

**47 privilégios** em 12 grupos, **20 administrativos** (só entram em papel personalizado com `perfil_minimo = admin`, ou no perfil `admin` inteiro — ADR 0002 seção 3.3).

## Papéis padrão fixos (teto de cada perfil)

Os quatro perfis abaixo são fixos, não são linhas de `plat.papel_personalizado` e não se apagam nem se editam (ADR 0002 seção 2.3). Um papel personalizado é sempre um SUBCONJUNTO do teto do `perfil_minimo` calculado a partir dos privilégios escolhidos — nunca um acréscimo.

| perfil | privilégios no teto |
|---|---|
| `visualizador` | 8 |
| `campo` | 12 |
| `editor` | 27 |
| `admin` | 47 |

## Vocabulário completo

V = visualizador · C = campo · E = editor · A = admin · **adm** = privilégio administrativo

| grupo | privilégio | descrição | adm | V | C | E | A |
|---|---|---|---|---|---|---|---|
| analise | `analise.amc` | criar e executar modelo multicritério | não |  |  | x | x |
| analise | `analise.executar` | geoprocessamento sobre dado próprio | não |  |  | x | x |
| analise | `analise.geocodificar` | geocodificar e buscar lugar | não | x | x | x | x |
| analise | `analise.raster` | análise de imagem | não |  |  | x | x |
| analise | `analise.rotas` | rotas e isócronas | não | x | x | x | x |
| campo | `campo.coletar` | usar formulários e a PWA de campo | não |  | x | x | x |
| campo | `campo.localizacao` | compartilhar localização/trilhas | não |  | x | x | x |
| compartilhar | `compartilhar.grupo` | compartilhar item com grupo em que pode contribuir | não |  |  | x | x |
| compartilhar | `compartilhar.inquilino` | compartilhar item com todo o inquilino | não |  |  | x | x |
| compartilhar | `compartilhar.link` | criar link por token | não |  |  | x | x |
| compartilhar | `compartilhar.publico` | tornar item público (só com config.compartilhar_publico) | **sim** |  |  |  | x |
| conteudo | `conteudo.apagar_tudo` | apagar/restaurar qualquer item | **sim** |  |  |  | x |
| conteudo | `conteudo.categorias` | gerir categorias do inquilino | **sim** |  |  |  | x |
| conteudo | `conteudo.criar` | criar, editar e apagar os próprios itens (mapa, app, pasta) | não |  |  | x | x |
| conteudo | `conteudo.editar_tudo` | editar metadado e dado de qualquer item | **sim** |  |  |  | x |
| conteudo | `conteudo.publicar_camada` | publicar camada vetorial hospedada | não |  |  | x | x |
| conteudo | `conteudo.publicar_raster` | publicar imagem/raster | não |  |  | x | x |
| conteudo | `conteudo.publicar_tiles` | publicar tiles vetoriais | não |  |  | x | x |
| conteudo | `conteudo.registrar_fonte` | registrar fonte de dado externa | não |  |  | x | x |
| conteudo | `conteudo.transferir` | mudar dono de item | **sim** |  |  |  | x |
| conteudo | `conteudo.ver_inquilino` | ver itens compartilhados com o inquilino | não | x | x | x | x |
| conteudo | `conteudo.ver_tudo` | ver qualquer item do inquilino, inclusive privado | **sim** |  |  |  | x |
| feicoes | `feicoes.editar` | editar feições de camada compartilhada com edição habilitada | não |  | x | x | x |
| feicoes | `feicoes.editar_total` | editar qualquer camada, mesmo sem edição habilitada | **sim** |  |  |  | x |
| grupos | `grupos.administrativo` | criar grupo administrativo (membro não sai) | **sim** |  |  |  | x |
| grupos | `grupos.atualizacao_compartilhada` | criar grupo com atualização compartilhada | não |  |  | x | x |
| grupos | `grupos.criar` | criar, editar e apagar os próprios grupos | não |  |  | x | x |
| grupos | `grupos.entrar` | pedir entrada ou entrar em grupo de entrada livre | não | x | x | x | x |
| grupos | `grupos.gerir_todos` | editar, apagar, transferir dono e gerir membros de qualquer grupo | **sim** |  |  |  | x |
| grupos | `grupos.ver_inquilino` | ver grupos com visibilidade inquilino | não | x | x | x | x |
| jobs | `jobs.executar` | criar, cancelar e repetir os próprios jobs, e gerir agendas | não |  | x | x | x |
| jobs | `jobs.gerir_todos` | ver e cancelar jobs de qualquer membro | **sim** |  |  |  | x |
| jobs | `jobs.ver` | ver a lista, o detalhe, o log e os tipos de job do inquilino (leitura) | não | x | x | x | x |
| membros | `membros.apagar` | apagar membro (só sem conteúdo e sem grupo) | **sim** |  |  |  | x |
| membros | `membros.gerir` | criar, editar nome/e-mail, desabilitar/reabilitar, redefinir senha, desligar 2FA, desbloquear | **sim** |  |  |  | x |
| membros | `membros.papel` | mudar perfil e papel (para/de admin só quem é admin) | **sim** |  |  |  | x |
| membros | `membros.ver` | ver nome, login, perfil e último acesso dos membros do inquilino | não | x | x | x | x |
| membros | `membros.ver_tudo` | ver e-mail, IP, sessões, tokens e 2FA de qualquer membro | **sim** |  |  |  | x |
| org | `org.configurar` | editar tenant.config, política de senha, exigir 2FA, domínios de e-mail | **sim** |  |  |  | x |
| org | `org.exportar` | exportar o inquilino, relatórios | **sim** |  |  |  | x |
| org | `org.integracoes` | SSO, SMTP, webhooks, CORS | **sim** |  |  |  | x |
| org | `org.log_ver` | ler log_acesso e evento do inquilino, exportar CSV | **sim** |  |  |  | x |
| papeis | `papeis.gerir` | criar, editar, apagar papel personalizado | **sim** |  |  |  | x |
| rede | `rede.editar` | editar rede de utilidades | não |  |  | x | x |
| rede | `rede.tracar` | traçado e subrede | não |  |  | x | x |
| tokens | `tokens.gerar` | criar e revogar os próprios tokens de serviço | não | x | x | x | x |
| tokens | `tokens.gerir_todos` | ver e revogar tokens de qualquer membro | **sim** |  |  |  | x |

## Papéis personalizados por inquilino
Nome até 128 caracteres, descrição até 250, criados "a partir de" um conjunto de privilégios escolhido pelo administrador (nunca um privilégio que o próprio administrador não tenha — `403 privilegio_proprio_insuficiente`). O backend calcula `perfil_minimo` = o menor perfil cujo teto contém todos os privilégios pedidos; atribuir esse papel a um usuário de perfil menor é `422 papel_incompativel`. Ver `docs/adr/0002-identidade-e-acesso.md` seção 3.3 e `docs/PARIDADE.md` para a paridade linha a linha com a Esri.

