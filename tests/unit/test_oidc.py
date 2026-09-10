"""Unidade do item L0-08-a-oidc: PKCE, cifra do client_secret e as 4 cláusulas literais do portão sobre
`validar_id_token` (assinatura errada, expirado, nonce errado, issuer errado) mais a cláusula da refutação
(aud/client_id de outro cliente) — tudo com chaves RSA sintéticas geradas na hora, sem Docker/Keycloak (o
Keycloak real é usado só pelos testes de integração em `tests/api/oidc/`, que também exercitam estas mesmas
4+1 cláusulas contra um IdP de verdade)."""

import base64
import hashlib
import time

import pytest
from joserfc import jwt as joserfc_jwt
from joserfc.jwk import KeySet, RSAKey

from app.auth import oidc

ISSUER = "https://idp-teste.invalido/realms/x"
CLIENT_ID = "cliente-x"


def _par_chaves(kid="k1"):
    priv = RSAKey.generate_key(2048, parameters={"kid": kid})
    pub = RSAKey.import_key(priv.as_dict(private=False))
    return priv, pub


def _token(priv, *, kid="k1", alg="RS256", **claims_extra):
    agora = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "usuario-1",
        "iat": agora,
        "exp": agora + 300,
        "nonce": "nonce-1",
        "email": "teste@x.invalido",
        "name": "Teste da Silva",
        "groups": ["gg-x"],
    }
    claims.update(claims_extra)
    return joserfc_jwt.encode({"alg": alg, "kid": kid}, claims, priv)


@pytest.fixture(autouse=True)
def _sem_cache_entre_testes():
    oidc.limpar_cache()
    yield
    oidc.limpar_cache()


def test_pkce_desafio_e_o_sha256_base64url_do_verificador():
    verificador, desafio = oidc.gerar_par_pkce()
    assert 43 <= len(verificador) <= 128
    esperado = (
        base64.urlsafe_b64encode(hashlib.sha256(verificador.encode("ascii")).digest()).decode("ascii").rstrip("=")
    )
    assert desafio == esperado
    # dois pares nunca repetem (haveria colisão de state/nonce se o gerador fosse fraco)
    assert oidc.gerar_par_pkce() != (verificador, desafio)


def test_client_secret_cifra_e_decifra_e_nunca_grava_em_claro():
    segredo_plat = "a" * 64
    cifrado = oidc.cifrar_client_secret("segredo-super-secreto", segredo_plat)
    assert cifrado.startswith(oidc.PREFIXO_CIFRA)
    assert "segredo-super-secreto" not in cifrado
    assert oidc.decifrar_client_secret(cifrado, segredo_plat) == "segredo-super-secreto"


def test_client_secret_decifrar_recusa_valor_sem_prefixo():
    with pytest.raises(ValueError):
        oidc.decifrar_client_secret("texto-qualquer-sem-prefixo", "a" * 64)


def test_id_token_valido_passa_e_devolve_as_claims(monkeypatch):
    priv, pub = _par_chaves()
    monkeypatch.setattr(oidc, "jwks_de", lambda uri, forcar=False: KeySet([pub]))
    claims = oidc.validar_id_token(
        _token(priv), jwks_uri="https://x/jwks", issuer=ISSUER, client_id=CLIENT_ID, nonce_esperado="nonce-1"
    )
    assert claims["sub"] == "usuario-1" and claims["email"] == "teste@x.invalido"


def test_assinatura_errada_e_recusada(monkeypatch):
    """Cláusula literal do portão: id_token com assinatura errada -> ErroOidc (motivo no log, nunca 200)."""
    priv, pub = _par_chaves()
    _, pub_outra = _par_chaves(kid="k1")  # kid IGUAL mas chave pública DIFERENTE: simula assinatura adulterada
    monkeypatch.setattr(oidc, "jwks_de", lambda uri, forcar=False: KeySet([pub_outra]))
    with pytest.raises(oidc.ErroOidc) as exc:
        oidc.validar_id_token(
            _token(priv), jwks_uri="https://x/jwks", issuer=ISSUER, client_id=CLIENT_ID, nonce_esperado="nonce-1"
        )
    assert exc.value.motivo_interno.startswith("assinatura_invalida")


def test_id_token_expirado_e_recusado(monkeypatch):
    """Cláusula literal do portão: id_token expirado -> ErroOidc (a assinatura sozinha NÃO detecta isto —
    achado do ADR D3: joserfc.jwt.decode não confere claims, só a assinatura)."""
    priv, pub = _par_chaves()
    monkeypatch.setattr(oidc, "jwks_de", lambda uri, forcar=False: KeySet([pub]))
    agora = int(time.time())
    token = _token(priv, iat=agora - 700, exp=agora - 600)
    with pytest.raises(oidc.ErroOidc) as exc:
        oidc.validar_id_token(
            token, jwks_uri="https://x/jwks", issuer=ISSUER, client_id=CLIENT_ID, nonce_esperado="nonce-1"
        )
    assert exc.value.motivo_interno.startswith("claim_invalida")


def test_nonce_errado_e_recusado(monkeypatch):
    """Cláusula literal do portão: nonce errado -> ErroOidc (defesa contra replay de uma transação diferente)."""
    priv, pub = _par_chaves()
    monkeypatch.setattr(oidc, "jwks_de", lambda uri, forcar=False: KeySet([pub]))
    with pytest.raises(oidc.ErroOidc) as exc:
        oidc.validar_id_token(
            _token(priv),
            jwks_uri="https://x/jwks",
            issuer=ISSUER,
            client_id=CLIENT_ID,
            nonce_esperado="nonce-DIFERENTE",
        )
    assert exc.value.motivo_interno.startswith("claim_invalida")


def test_issuer_errado_e_recusado(monkeypatch):
    """Cláusula literal do portão: issuer errado -> ErroOidc. Token assinado por um issuer que NÃO é o
    configurado no provedor (mesma chave, para provar que a checagem de iss é INDEPENDENTE da assinatura)."""
    priv, pub = _par_chaves()
    monkeypatch.setattr(oidc, "jwks_de", lambda uri, forcar=False: KeySet([pub]))
    token = _token(priv, iss="https://outro-idp.invalido/realms/y")
    with pytest.raises(oidc.ErroOidc) as exc:
        oidc.validar_id_token(
            token, jwks_uri="https://x/jwks", issuer=ISSUER, client_id=CLIENT_ID, nonce_esperado="nonce-1"
        )
    assert exc.value.motivo_interno.startswith("claim_invalida")


def test_aud_de_outro_client_id_e_recusado_refutacao(monkeypatch):
    """A refutação do item: 'tenta aud de outro inquilino' -- id_token com assinatura válida (mesmo issuer,
    mesma chave) mas emitido para OUTRO client_id nunca é aceito pelo provedor configurado com o client_id
    certo, mesmo sem nenhum outro campo forjado."""
    priv, pub = _par_chaves()
    monkeypatch.setattr(oidc, "jwks_de", lambda uri, forcar=False: KeySet([pub]))
    token = _token(priv, aud="cliente-de-outro-inquilino")
    with pytest.raises(oidc.ErroOidc) as exc:
        oidc.validar_id_token(
            token, jwks_uri="https://x/jwks", issuer=ISSUER, client_id=CLIENT_ID, nonce_esperado="nonce-1"
        )
    assert exc.value.motivo_interno.startswith("claim_invalida")


def test_algoritmo_none_e_recusado_antes_de_qualquer_jwks(monkeypatch):
    """'alg: none' (RFC 8725 §3.1, o clássico bypass de assinatura) nunca chega a consultar o JWKS: o
    cabeçalho é recusado na primeira checagem, sem qualquer chance de 'toda assinatura vazia bate'."""
    chamado = []
    monkeypatch.setattr(oidc, "jwks_de", lambda uri, forcar=False: chamado.append(1) or KeySet([]))
    cabecalho = base64.urlsafe_b64encode(b'{"alg":"none","kid":"k1"}').decode().rstrip("=")
    payload = (
        base64.urlsafe_b64encode(b'{"iss":"x","aud":"y","sub":"z","exp":9999999999,"nonce":"n"}').decode().rstrip("=")
    )
    token_none = f"{cabecalho}.{payload}."
    with pytest.raises(oidc.ErroOidc) as exc:
        oidc.validar_id_token(
            token_none, jwks_uri="https://x/jwks", issuer=ISSUER, client_id=CLIENT_ID, nonce_esperado="n"
        )
    assert exc.value.motivo_interno.startswith("algoritmo_recusado")
    assert not chamado  # nunca bateu no JWKS -- recusado só pelo cabeçalho


def test_rotacao_de_chave_refaz_o_jwks_uma_vez(monkeypatch):
    """Cache com rotação (cláusula da hipótese): kid desconhecido no cache -> um refetch forçado; se a
    chave nova aparecer nesse refetch, o token passa (sem exigir reiniciar o processo)."""
    priv_velha, pub_velha = _par_chaves(kid="k-velha")
    priv_nova, pub_nova = _par_chaves(kid="k-nova")
    chamadas = {"n": 0}

    def _fake_jwks(uri, forcar=False):
        chamadas["n"] += 1
        if not forcar:
            return KeySet([pub_velha])  # cache "desatualizado": só tem a chave velha
        return KeySet([pub_velha, pub_nova])  # refetch (rotação): achou a chave nova

    monkeypatch.setattr(oidc, "jwks_de", _fake_jwks)
    token = _token(priv_nova, kid="k-nova")
    claims = oidc.validar_id_token(
        token, jwks_uri="https://x/jwks", issuer=ISSUER, client_id=CLIENT_ID, nonce_esperado="nonce-1"
    )
    assert claims["sub"] == "usuario-1"
    assert chamadas["n"] == 2  # 1 tentativa com cache velho (falhou) + 1 refetch forçado (achou)
