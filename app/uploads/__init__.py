"""Upload retomável pelo navegador (item L0-04-a-upload-arquivo; ADR 0005 seção 3): `POST /api/uploads` reserva
cota e abre um multipart no Garage (contrato de `app.objetos.parte_*`, L0-11); `PUT /api/uploads/{id}/partes/{n}`
recebe partes fora de ordem e reenviadas; `POST /api/uploads/{id}/concluir` fecha o multipart, confere sha256/
tamanho/tipo×conteúdo e registra o item `arquivo` no catálogo; `DELETE /api/uploads/{id}` aborta. Periódico
`uploads.expirar` limpa uploads sem atividade há 24 h (app.uploads.periodicos)."""
