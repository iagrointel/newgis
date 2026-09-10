# Regras de provisionamento por provedor de login externo (item L0-08-e-mapeamento-provisionamento)

Data: 08/09/2026. Estado: aceito. Par: ADR 0008 (LDAP), `20260907T0147-oidc-authlib.md`,
`20260907T2110-saml-python3-saml.md`; `laco/decomposicao/L0_CONCEITO.md`.

## Contexto

LDAP, OIDC e SAML já autenticavam e provisionavam com `perfil_padrao` + `mapa_grupo_perfil` (grupo do IdP ->
perfil), cada um com o seu laço copiado. Faltava o que a Esri chama de *New member defaults* e *group
membership*: criar automaticamente ou só por convite, padrões para membro novo (papel, grupos, pasta), grupo
do IdP -> papel e grupos internos por valor exato, atualização a cada login, desligamento quando o IdP deixa
de mandar o grupo, rótulo/ordem dos botões numa tela só e "desregistrar" conta federada.

## Decisões

1. **Um laço só para os três provedores** (`app/auth/provisionamento.py::aplicar`), chamado por
   `oidc.py`, `saml.py` e `ldap.py` depois que o IdP confirmou a identidade: decide (regras + perfil), provisiona
   (`plat.usuario_externo_provisionar`, já existente), aplica papel/grupos/pasta (`plat.usuario_federado_regras`)
   e devolve a linha de `plat.auth_login`. Os três módulos só cuidam do protocolo.
2. **Regras numa coluna jsonb `provisionamento` por tabela de provedor**, lida por `plat.provisionamento_de`
   (as funções de leitura dos provedores devolvem tipos fixos; acrescentar coluna nelas exigiria DROP). O perfil
   continua em `mapa_grupo_perfil`/`perfil_padrao`; a rota `PUT /api/org/logins/{tipo}/{id}` copia o `perfil`
   de cada regra para `mapa_grupo_perfil` — uma fonte só, editada num lugar só.
3. **Mapeamento é por regra explícita e valor exato.** Um grupo do IdP chamado `administrador` sem regra não
   vira nada (`perfil_por_grupos` nunca compara com nome de perfil; testes de unidade e de integração cobrem).
   Até 1000 valores do IdP são lidos por login; o resto é ignorado (adversário com 500 grupos custa nada).
4. **"Só por convite" usa o convite por e-mail que já existe (L0-07-d)**: membro desconhecido cujo e-mail tem
   convite pendente entra com o perfil/papel do convite (o convite é consumido); sem convite, 403
   `convite_necessario` ("peça convite"). Conta desregistrada volta a ser desconhecida.
5. **Grupos regidos**: todo grupo citado nas regras do provedor é sincronizado a cada login (entra e sai);
   grupos que o provedor não cita nunca são tocados; dono e grupo administrativo/protegido nunca são removidos.
   `atualizar_a_cada_login=false` congela perfil/papel/grupos depois da criação (nome/e-mail ainda atualizam).
6. **`desligar_sem_grupo`** (extra, sem par na Esri): conta existente sem grupo mapeado e sem perfil padrão é
   desativada, as sessões caem, o login responde 403 `conta_desligada`. Conta desligada NO IdP com sessão local
   viva continua até a política de sessão expirar (o IdP não é consultado a cada pedido); o próximo login é
   recusado pelo IdP.
7. **Desregistrar** (`POST /api/usuarios/{id}/desregistrar`, `membros.gerir`): `sujeito_externo = NULL`,
   `ativo = false`, sessões encerradas; a conta no IdP continua. Conta local e a própria conta = 409.
8. **Tela `/admin/logins`** (`org.integracoes`): lista LDAP/OIDC/SAML com rótulo, ordem, habilitação, criação e
   número de regras; editor de regras por linha; tabela de paridade com a Esri 11.4 na própria tela.

## Paridade com a Esri 11.4 (New member defaults · SAML/OIDC group membership)

| Esri | aqui |
|---|---|
| Automatically × Upon invitation from an administrator | `criacao`: automatica × convite |
| user type / role padrão | `perfil_padrao` + `padrao.papel_id` |
| groups padrão | `padrao.grupos` |
| Update profile on sign in | `atualizar_a_cada_login` |
| IdP group (nome exato) vinculado a grupo do portal, sincronizado no login | `mapa[valor].grupos`, grupos regidos |
| Remove member (a conta no IdP continua) | desregistrar |
| (sem par) | `desligar_sem_grupo`, `pasta` inicial |

## Consequências

- `tests/api/oidc/test_provisionamento.py` cria grupos/usuários no Keycloak pela API de administração dentro do
  teste (o `realm.json` versionado não muda) e roda como `lento` (contêiner Docker).
- O ramo depende de `wt/cx008` (OIDC + SAML), ainda na fila de junção: este ramo o contém por merge.
