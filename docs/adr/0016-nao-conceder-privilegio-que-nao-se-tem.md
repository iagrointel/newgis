# ADR 0016 — Ninguém concede privilégio que não tem

Data: setembro de 2026. Estado: aceito. Item: `L0-02-g-checagem-privilegio-papel-id`.

## Contexto

O papel personalizado (`plat.papel_personalizado`) é uma RESTRIÇÃO, não uma extensão. `plat.privilegios_de`
(migração 003, seção 12.10) devolve a interseção entre o teto do perfil e os privilégios do papel. Por isso um
administrador com papel personalizado tem MENOS privilégios que um administrador sem papel nenhum.

As rotas de papel já cuidavam da criação: `_validar_papel` recusa com 403 `privilegio_proprio_insuficiente`
quem tenta criar ou editar um papel com privilégio que não possui. Faltava a outra metade. `POST /api/usuarios`
e `PUT /api/usuarios/{id}` conferiam apenas se o papel CABIA no perfil do alvo (`_papel_compativel`), nunca se
o ATOR tinha o que estava concedendo. Um administrador restrito por papel podia então:

1. atribuir a outro usuário um papel personalizado mais amplo que o seu;
2. atribuir `papel_id` nulo a alguém — inclusive a si mesmo — o que devolve o teto inteiro do perfil;
3. promover um editor a administrador sem papel, o que concede o mesmo conjunto pelo caminho do perfil;
4. fazer qualquer um dos três em massa por `POST /api/usuarios/lote`.

## Decisão

`_nao_conceder_alem_do_proprio` roda em toda escrita que fixa (perfil, papel_id) de um usuário: calcula os
privilégios efetivos que o alvo passaria a ter, com a MESMA consulta de `plat.privilegios_de`, e recusa com 403
`privilegio_proprio_insuficiente` se sobrar qualquer privilégio fora do conjunto do ator. A lista do que sobrou
vai no `detalhe`.

A regra vale para perfil e papel juntos, não só para `papel_id`, porque promover de editor a administrador com
papel nulo concede exatamente o mesmo conjunto que atribuir o papel mais amplo. O lote passa pelo mesmo
`_editar`, então herda a conferência e devolve o item recusado sem alterar nada.

O conjunto do ator é lido do banco a cada chamada (`plat.perfil_privilegio` × `plat.papel_privilegio`), não da
lista em Python de `app/auth/privilegios.py`: essa lista serve a documentação e ao cálculo de perfil mínimo, e
manter duas verdades sobre o teto de cada perfil seria criar a próxima brecha.

## Consequências

- Delegar segue permitido: conceder papel contido no próprio conjunto passa normalmente (201/200).
- Administrador pleno (sem papel) não é afetado: o teto de qualquer perfil está contido no conjunto dele.
- Administrador restrito não consegue mais se auto-promover nem promover terceiros acima de si.
- Quem quiser conceder um privilégio que não tem precisa que um administrador com aquele privilégio o faça —
  não existe caminho de escalonamento pela tela de usuários.

## O que isto NÃO resolve

- A redação do portão do item fala em "editor". Um editor não chega a esta conferência: `membros.gerir` e
  `membros.papel` só existem no teto do perfil admin, então o editor toma 403 `sem_privilegio` antes. O ator
  real do achado é o administrador restrito por papel.
- O provisionamento por LDAP (migração 025) insere usuário sem papel (`papel_id` nulo), mas define o PERFIL a
  partir do mapeamento de grupo, dentro do banco, sem passar por estas rotas. Quem edita esse mapeamento precisa
  de `org.integracoes`; a conferência não é chamada lá, e essa é a superfície que sobra. Se um dia o
  provisionamento externo atribuir papel, a conferência tem de ser chamada lá também.
