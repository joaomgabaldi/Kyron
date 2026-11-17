# recuperacao_fitas.py
#
# Copyright 2026 joaomgabaldi
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Diagnóstico da causa de uma fita Tuya ter parado de responder.

Cruza o erro da última tentativa com o que a varredura da rede anunciou e diz o que mudou: o IP, a versão do protocolo ou (só nas versões 3.4 em diante) a chave local.
"""

import logging
import time
from typing import TYPE_CHECKING, Any, NamedTuple, Optional

from kyron.utils import tuya_conta

if TYPE_CHECKING:
    from kyron.utils.session_fita import Fita

ERRO_DE_CHAVE = "914"
VERSAO_MINIMA_DA_CHAVE = 3.4
# Segundos entre duas idas à nuvem pela mesma fita: a chave só muda quando a fita é pareada de novo.
INTERVALO_DA_NUVEM = 600

_ultima_busca: dict[str, float] = {}
_sem_conta_avisada: set[str] = set()


def _agora() -> float:
    return time.monotonic()


class Mudanca(NamedTuple):
    """O que corrigir na fita; ``ip``/``versao`` só vêm quando diferem do gravado."""

    ip: Optional[str]
    versao: Optional[str]
    buscar_chave: bool


def diagnosticar(
    fita: "Fita",
    erro: Optional[str],
    ips: dict[str, str],
    versoes: dict[str, str],
) -> Mudanca:
    """Compara o gravado com o anunciado pela varredura (``ips``/``versoes`` por id)."""
    ip = ips.get(fita.id)
    versao = versoes.get(fita.id)
    ip = ip if ip and ip != fita.ip else None
    versao = versao if versao and versao != fita.versao else None
    # Versão nova anunciada: a versão errada também dá 914, então não busca a chave ainda.
    if versao or erro != ERRO_DE_CHAVE:
        return Mudanca(ip, versao, False)
    try:
        busca = float(fita.versao) >= VERSAO_MINIMA_DA_CHAVE
    except ValueError:
        busca = False
    return Mudanca(ip, versao, busca)


def nuvem(regiao: str, chave: str, segredo: str) -> Any:
    """A fábrica da nuvem da Tuya: o único ponto que fala com ela (os testes trocam este)."""
    import tinytuya  # noqa: PLC0415

    return tinytuya.Cloud(apiRegion=regiao, apiKey=chave, apiSecret=segredo)


def chave_da_nuvem(fita: "Fita") -> Optional[str]:
    """A chave local atual da fita segundo a nuvem, ou ``None`` (sem conta, limite, erro, fita ausente ou chave igual). Nunca levanta."""
    conta = tuya_conta.carregar()
    if conta is None:
        if fita.id not in _sem_conta_avisada:
            _sem_conta_avisada.add(fita.id)
            logging.warning("Fita %s: a chave mudou, mas não há conta da nuvem salva; rode o assistente", fita.nome)
        return None

    agora = _agora()
    ultima = _ultima_busca.get(fita.id)
    if ultima is not None and agora - ultima < INTERVALO_DA_NUVEM:
        return None
    _ultima_busca[fita.id] = agora

    try:
        resposta = nuvem(conta.regiao, conta.chave, conta.segredo).getdevices()
    except Exception as erro:  # a tinytuya levanta de tudo
        # O texto do erro pode trazer a requisição inteira: os dois códigos nunca vão ao log.
        texto = str(erro).replace(conta.segredo, "***").replace(conta.chave, "***")
        logging.warning("Fita %s: a busca da chave na nuvem falhou: %s", fita.nome, texto)
        return None

    nova = None
    if isinstance(resposta, list):
        for item in resposta:
            if isinstance(item, dict) and str(item.get("id")) == fita.id:
                nova = str(item.get("key") or "") or None
    if nova is None or nova == fita.key:
        logging.info("Fita %s: a nuvem não trouxe chave nova", fita.nome)
        return None
    return nova
