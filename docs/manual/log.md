---
id: log
titulo: Log de acesso
titulo_en: Access log
titulo_es: Registro de acceso
resumo: "eventos do inquilino: entradas, mudanças de configuração e chamadas da API por membro"
resumo_en: "tenant events: sign-ins, configuration changes and API calls per member"
resumo_es: "eventos del inquilino: inicios de sesión, cambios de configuración y llamadas a la API por miembro"
classe: tela
pagina: admin/log.html
caminho: /admin/log
e2e: tests/e2e/test_log_acesso.py
captura: L0-02-tenant-auth_log.png
e2e_captura: capturar("log")
palavras: [log, acesso, eventos, auditoria, quem fez, admin]
palavras_en: [log, access, events, audit, who did, admin]
palavras_es: [registro, acceso, eventos, auditoria, quien hizo, admin]
---

## Log de acesso

A tela Log mostra os eventos do inquilino em ordem do mais recente para o mais antigo: entradas e
saídas, criação e mudança de membros, papéis, tokens, configuração da organização e chamadas
relevantes da API. Exige o privilégio `org.log_ver`.

1. Filtre por membro, tipo de evento ou faixa de tempo pelos campos do topo.
2. Cada linha mostra instante, membro (ou token), evento e detalhe.

O log é de leitura: nenhum evento se apaga pela tela. A retenção segue a configuração da
organização.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_log_acesso.py`) contra a versão atual.
