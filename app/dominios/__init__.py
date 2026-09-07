"""Domínios de atributo e subtipos por camada (item L2-10-a-dominios-subtipos).

O domínio é objeto do inquilino (`plat.dominio`), compartilhado por quantas camadas quiserem; a ligação
campo -> domínio vive por camada e por subtipo (`plat.dominio_campo`); o subtipo é um campo inteiro
designado da camada com uma lista de códigos (`plat.camada_subtipo`). A regra vale no banco, por gatilho
genérico (`plat.feicao_validar_dominio`), e na API — quem escrever direto na tabela como `plat_app` leva o
mesmo erro que a API devolveria.
"""
