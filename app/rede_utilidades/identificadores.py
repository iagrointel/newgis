"""Identidade e numeração de ativos da rede de utilidades (item L4-28-identificadores-e-numeracao).

Regras do desenho (ADR docs/adr/20260906T2121-rede-identificadores.md):
  - `global_id` (uuid) é a identidade interna estável do ativo: nasce na criação e nunca muda, nem na
    renomeação do código externo;
  - `codigo_externo` (o código do cliente, ex.: COD_ID da BDGD) é único por REDE — índice único parcial
    no banco; duplicado = 409;
  - `numero` é a numeração automática por TIPO de ativo: um contador por tipo (plat.rede_numeracao) que
    só anda para a frente. Criação conectada recebe o próximo número; quem vai a campo DESconectado
    reserva antes uma faixa de N números (plat.rede_faixa) e consome offline — reservar faz o contador
    pular N, então conectado e desconectado nunca colidem, e duas reservas simultâneas recebem blocos
    disjuntos (a alocação é INSERT ... ON CONFLICT ... DO UPDATE ... RETURNING, que trava a linha do
    contador até o commit);
  - número informado na criação (= sincronização do que foi criado offline) só é aceito dentro de uma
    faixa ABERTA do PRÓPRIO usuário; fora dela = 422. Número já usado = 409 (índice único por tipo);
  - renomear = trocar o `codigo_externo`: o global_id fica e cada troca grava uma linha em
    plat.rede_ativo_renomeacao.
"""

import uuid as uuid_mod

import psycopg2.errors

from app.erros import ErroAPI

QUANTIDADE_MAX_FAIXA = 100_000  # teto de uma reserva (uma turma de campo inteira não passa disso)


def alocar(cur, tenant_id: int, tipo_id: str, quantidade: int) -> int:
    """Reserva `quantidade` números do contador do tipo e devolve o PRIMEIRO do bloco. Atômico: a linha do
    contador fica travada até o commit da transação do chamador, então duas alocações concorrentes do mesmo
    tipo recebem blocos disjuntos — é isto que a refutação do item ataca (dois clientes reservando a mesma
    faixa ao mesmo tempo)."""
    cur.execute(
        "INSERT INTO plat.rede_numeracao(tenant_id, tipo_id, proximo) VALUES (%s, %s::uuid, 1 + %s) "
        "ON CONFLICT (tenant_id, tipo_id) "
        "DO UPDATE SET proximo = plat.rede_numeracao.proximo + %s "
        "RETURNING proximo - %s AS inicio",
        (tenant_id, tipo_id, quantidade, quantidade, quantidade),
    )
    return cur.fetchone()["inicio"]


def tipo_da_rede(cur, rede_id: str, tipo_id: str) -> dict:
    """O tipo de ativo, conferindo que pertence à rede da URL (tipo de outra rede = 422, nunca 404: a rota
    é da rede)."""
    cur.execute(
        "SELECT t.id, t.chave, t.nome, t.codigo FROM plat.rede_tipo t "
        "WHERE t.id = %s::uuid AND t.rede_id = %s::uuid",
        (tipo_id, rede_id),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(422, "tipo_de_outra_rede", "o tipo de ativo informado não pertence a esta rede")
    return r


def reservar_faixa(cur, tenant_id: int, rede_id: str, tipo_id: str, usuario_id: int, quantidade: int) -> dict:
    """Reserva o próximo bloco livre de `quantidade` números do tipo para o usuário. A faixa é sempre
    contígua e nunca reutiliza número (o contador não anda para trás, nem depois de liberar)."""
    if not 1 <= quantidade <= QUANTIDADE_MAX_FAIXA:
        raise ErroAPI(422, "quantidade_invalida",
                      f"a quantidade da faixa fica entre 1 e {QUANTIDADE_MAX_FAIXA}")
    inicio = alocar(cur, tenant_id, tipo_id, quantidade)
    fim = inicio + quantidade - 1
    cur.execute(
        "INSERT INTO plat.rede_faixa(tenant_id, rede_id, tipo_id, usuario_id, inicio, fim) "
        "VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s) "
        "RETURNING id, inicio, fim, consumidos, criado_em",
        (tenant_id, rede_id, tipo_id, usuario_id, inicio, fim),
    )
    return cur.fetchone()


def reservar_faixa_explicita(cur, tenant_id: int, rede_id: str, tipo_id: str, usuario_id: int,
                             inicio: int, fim: int) -> dict:
    """Reserva o bloco exato [inicio, fim] (a forma `firstUnit`/`lastUnit` da fachada Esri). Recusa se
    qualquer número do bloco já virou ativo (409) ou se o bloco sobrepõe faixa aberta (a restrição de
    EXCLUSÃO do banco vira 409 `faixa_sobreposta`). Se o bloco passa do contador, o contador avança para
    depois dele — senão a criação conectada acabaria entregando um número reservado. Os números entre o
    contador e o início do bloco ficam como lacuna (a Esri tem o mesmo conceito: `gaps` do query)."""
    if inicio < 1 or fim < inicio or (fim - inicio + 1) > QUANTIDADE_MAX_FAIXA:
        raise ErroAPI(422, "faixa_invalida",
                      f"a faixa fica entre 1 e {QUANTIDADE_MAX_FAIXA} números, início <= fim")
    # trava a linha do contador até o commit (o DO UPDATE sem mudança de valor é de propósito: FOR UPDATE)
    cur.execute(
        "INSERT INTO plat.rede_numeracao(tenant_id, tipo_id, proximo) VALUES (%s, %s::uuid, 1) "
        "ON CONFLICT (tenant_id, tipo_id) DO UPDATE SET proximo = plat.rede_numeracao.proximo "
        "RETURNING proximo",
        (tenant_id, tipo_id),
    )
    proximo = cur.fetchone()["proximo"]
    cur.execute(
        "SELECT numero FROM plat.rede_ativo WHERE tipo_id = %s::uuid AND numero BETWEEN %s AND %s LIMIT 1",
        (tipo_id, inicio, fim),
    )
    if cur.fetchone() is not None:
        raise ErroAPI(409, "numero_em_uso", "há número dessa faixa já usado por um ativo deste tipo")
    if fim >= proximo:
        cur.execute(
            "UPDATE plat.rede_numeracao SET proximo = %s WHERE tenant_id = %s AND tipo_id = %s::uuid",
            (fim + 1, tenant_id, tipo_id),
        )
    try:
        cur.execute(
            "INSERT INTO plat.rede_faixa(tenant_id, rede_id, tipo_id, usuario_id, inicio, fim) "
            "VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s) "
            "RETURNING id, inicio, fim, consumidos, criado_em",
            (tenant_id, rede_id, tipo_id, usuario_id, inicio, fim),
        )
    except psycopg2.errors.ExclusionViolation as e:
        raise ErroAPI(409, "faixa_sobreposta",
                      "a faixa pedida sobrepõe uma faixa aberta já reservada para este tipo") from e
    return cur.fetchone()


def _faixa_aberta_do_usuario(cur, tenant_id: int, tipo_id: str, usuario_id: int, numero: int) -> dict:
    """A faixa aberta do usuário que cobre `numero`, travada FOR UPDATE (o consumo incrementa nela).
    Nenhuma = 422: número fora de faixa própria não entra — é a única porta da criação desconectada."""
    cur.execute(
        "SELECT id, inicio, fim, consumidos FROM plat.rede_faixa "
        "WHERE tenant_id = %s AND tipo_id = %s::uuid AND usuario_id = %s AND liberada_em IS NULL "
        "AND inicio <= %s AND fim >= %s "
        "ORDER BY inicio LIMIT 1 FOR UPDATE",
        (tenant_id, tipo_id, usuario_id, numero, numero),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(
            422, "numero_fora_de_faixa",
            "o número informado não está em nenhuma faixa aberta sua para este tipo de ativo; "
            "criação desconectada exige reservar a faixa antes",
        )
    return r


def criar_ativo(cur, tenant_id: int, rede_id: str, tipo_id: str, usuario_id: int,
                codigo_externo: str | None, numero: int | None) -> dict:
    """Cria a identidade do ativo. Sem `numero` (conectado): o servidor aloca o próximo. Com `numero`
    (sincronização do criado offline): tem de estar dentro de uma faixa aberta do próprio usuário."""
    faixa = None
    if numero is None:
        numero = alocar(cur, tenant_id, tipo_id, 1)
    else:
        if numero < 1:
            raise ErroAPI(422, "numero_invalido", "o número do ativo começa em 1")
        faixa = _faixa_aberta_do_usuario(cur, tenant_id, tipo_id, usuario_id, numero)
    try:
        cur.execute(
            "INSERT INTO plat.rede_ativo(tenant_id, rede_id, tipo_id, numero, codigo_externo, criado_por) "
            "VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s) "
            "RETURNING global_id, numero, codigo_externo, criado_em",
            (tenant_id, rede_id, tipo_id, numero, codigo_externo, usuario_id),
        )
    except psycopg2.errors.UniqueViolation as e:
        restricao = (e.diag.constraint_name or "")
        if "codigo_externo" in restricao:
            raise ErroAPI(409, "codigo_externo_existente",
                          "já existe um ativo nesta rede com esse código externo") from e
        raise ErroAPI(409, "numero_em_uso",
                      "esse número já foi usado por outro ativo deste tipo") from e
    r = cur.fetchone()
    if faixa is not None:
        cur.execute(
            "UPDATE plat.rede_faixa SET consumidos = consumidos + 1 WHERE id = %s::uuid",
            (str(faixa["id"]),),
        )
    return r


def renomear(cur, tenant_id: int, rede_id: str, global_id: str, novo_codigo: str, usuario_id: int) -> dict:
    """Troca o código externo mantendo o global_id; grava a renomeação. Renomear para o MESMO código é
    idempotente (200, sem linha de histórico — nada mudou)."""
    cur.execute(
        "SELECT global_id, codigo_externo FROM plat.rede_ativo "
        "WHERE global_id = %s::uuid AND rede_id = %s::uuid FOR UPDATE",
        (global_id, rede_id),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "ativo_inexistente", "ativo inexistente nesta rede")
    anterior = r["codigo_externo"]
    if anterior == novo_codigo:
        return {"mudou": False, "anterior": anterior}
    try:
        cur.execute(
            "UPDATE plat.rede_ativo SET codigo_externo = %s WHERE global_id = %s::uuid",
            (novo_codigo, global_id),
        )
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(409, "codigo_externo_existente",
                      "já existe um ativo nesta rede com esse código externo") from e
    cur.execute(
        "INSERT INTO plat.rede_ativo_renomeacao(tenant_id, ativo_global_id, codigo_externo_anterior, "
        "codigo_externo_novo, renomeado_por) VALUES (%s, %s::uuid, %s, %s, %s)",
        (tenant_id, global_id, anterior, novo_codigo, usuario_id),
    )
    return {"mudou": True, "anterior": anterior}


def uuid_ok(valor: str, codigo: str = "id_invalido") -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, codigo, "identificador inexistente") from e


def faixa_json(r: dict, dono_login: str | None = None) -> dict:
    tamanho = r["fim"] - r["inicio"] + 1
    if r["liberada_em"] is not None:
        estado = "liberada"
    elif r["consumidos"] >= tamanho:
        estado = "esgotada"
    else:
        estado = "aberta"
    saida = {
        "id": str(r["id"]),
        "tipo_id": str(r["tipo_id"]),
        "inicio": r["inicio"],
        "fim": r["fim"],
        "tamanho": tamanho,
        "consumidos": r["consumidos"],
        "estado": estado,
        "criado_em": r["criado_em"].isoformat(),
        "liberada_em": r["liberada_em"].isoformat() if r["liberada_em"] else None,
    }
    if dono_login is not None:
        saida["dono"] = dono_login
    if "usuario_id" in r:
        saida["usuario_id"] = r["usuario_id"]
    return saida
