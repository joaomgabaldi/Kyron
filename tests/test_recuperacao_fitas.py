import logging

import pytest

from kyron.utils import recuperacao_fitas, tuya_conta
from kyron.utils.recuperacao_fitas import Mudanca, chave_da_nuvem, diagnosticar
from kyron.utils.session_fita import Fita

F34 = Fita("Sala", "eb1", "10.0.0.5", "k", "3.4")
F33 = Fita("Sala", "eb1", "10.0.0.5", "k", "3.3")


def test_sem_anuncio_nao_muda_nada():
    assert diagnosticar(F34, "905", {}, {}) == Mudanca(None, None, False)


def test_outro_ip():
    r = diagnosticar(F34, "905", {"eb1": "10.0.0.9"}, {"eb1": "3.4"})
    assert r == Mudanca("10.0.0.9", None, False)


def test_mesmo_ip_nao_muda():
    r = diagnosticar(F34, None, {"eb1": "10.0.0.5"}, {"eb1": "3.4"})
    assert r == Mudanca(None, None, False)


def test_outra_versao():
    r = diagnosticar(F34, "914", {"eb1": "10.0.0.5"}, {"eb1": "3.5"})
    assert r == Mudanca(None, "3.5", False)


def test_ip_e_versao_juntos():
    r = diagnosticar(F34, "914", {"eb1": "10.0.0.9"}, {"eb1": "3.5"})
    assert r == Mudanca("10.0.0.9", "3.5", False)


def test_chave_em_34():
    r = diagnosticar(F34, "914", {"eb1": "10.0.0.5"}, {"eb1": "3.4"})
    assert r.buscar_chave is True
    assert diagnosticar(F34, "914", {}, {}).buscar_chave is True


def test_33_muda_nunca_busca_chave():
    for erro in (None, "914"):
        r = diagnosticar(F33, erro, {"eb1": "10.0.0.5"}, {"eb1": "3.3"})
        assert r.buscar_chave is False


def test_anuncio_de_outro_aparelho_ignorado():
    r = diagnosticar(F34, "905", {"zz9": "10.0.0.9"}, {"zz9": "3.5"})
    assert r == Mudanca(None, None, False)


def test_versao_ilegivel_nao_busca():
    fita = Fita("Sala", "eb1", "10.0.0.5", "k", "x")
    assert diagnosticar(fita, "914", {}, {}).buscar_chave is False


@pytest.fixture(autouse=True)
def _estado_limpo():
    recuperacao_fitas._ultima_busca.clear()
    recuperacao_fitas._sem_conta_avisada.clear()


@pytest.fixture
def nuvem_falsa(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    relogio = [1000.0]
    estado = {"chamadas": 0, "resposta": [{"id": "eb1", "key": "nova"}], "erro": None}

    class Nuvem:
        def getdevices(self):
            estado["chamadas"] += 1
            if estado["erro"]:
                raise estado["erro"]
            return estado["resposta"]

    monkeypatch.setattr(recuperacao_fitas, "nuvem", lambda *_a: Nuvem())
    monkeypatch.setattr(tuya_conta, "carregar", lambda: tuya_conta.Conta("ID", "SEGREDO", "us"))
    monkeypatch.setattr(recuperacao_fitas, "_agora", lambda: relogio[0])
    estado["relogio"] = relogio
    return estado


def test_traz_a_chave_nova(nuvem_falsa, caplog):
    assert chave_da_nuvem(F34) == "nova"
    assert "nova" not in caplog.text


def test_limite_de_dez_minutos(nuvem_falsa):
    assert chave_da_nuvem(F34) == "nova"
    assert chave_da_nuvem(F34) is None
    assert nuvem_falsa["chamadas"] == 1
    nuvem_falsa["relogio"][0] += 601
    assert chave_da_nuvem(F34) == "nova"
    assert nuvem_falsa["chamadas"] == 2


def test_chave_igual_nao_e_nova(nuvem_falsa, caplog):
    nuvem_falsa["resposta"] = [{"id": "eb1", "key": "k"}]
    assert chave_da_nuvem(F34) is None
    assert "Fita Sala: a nuvem não trouxe chave nova" in caplog.text


def test_sem_conta_avisa_uma_vez(nuvem_falsa, monkeypatch, caplog):
    monkeypatch.setattr(tuya_conta, "carregar", lambda: None)
    assert chave_da_nuvem(F34) is None
    assert chave_da_nuvem(F34) is None
    aviso = "Fita Sala: a chave mudou, mas não há conta da nuvem salva; rode o assistente"
    assert caplog.text.count(aviso) == 1


def test_erro_da_nuvem_mascara_credenciais(nuvem_falsa, caplog):
    nuvem_falsa["erro"] = RuntimeError("falhou ID SEGREDO")
    assert chave_da_nuvem(F34) is None
    assert "***" in caplog.text
    assert "ID" not in caplog.text and "SEGREDO" not in caplog.text


def test_resposta_de_erro_nao_levanta(nuvem_falsa):
    nuvem_falsa["resposta"] = {"Error": "x"}
    assert chave_da_nuvem(F34) is None
