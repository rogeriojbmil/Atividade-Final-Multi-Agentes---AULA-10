"""
ETAPA 4 -- APIs externas com resiliência: feriados, câmbio, idempotência e limites. (PRONTO: leia, rode e entenda)

Este arquivo já vem implementado, para sobrar tempo para o MCP, o grafo e a segurança. Tudo aqui é técnica que você já
viu na Aula 3 e na Aula 6; a sua tarefa é LER, RODAR (online e offline) e conseguir explicar cada função no ENTREGA.md.
Tudo é Python puro (nenhuma chamada ao LLM, exceto rodar_com_limites): dá para testar sem chave de API.

  4.1 -- texto_hoje(): a data REAL, injetada nas instruções dos extratores (etapa02_extracao.py já usa)
  4.2 -- get_json_com_retry(): timeout + até 3 tentativas + backoff exponencial
  4.3 -- buscar_feriados(): BrasilAPI com plano B (dados/feriados_2027.json) e cache
  4.4 -- dias_uteis(), data_retorno(), inicio_permitido() (regra N3)
  4.5 -- cotacao_usd_brl(): Frankfurter com o mesmo retry; falhou -> None ("a calcular")
  4.6 -- gerar_protocolo(): SHA-256 dos campos normalizados (idempotência)
  4.7 -- rodar_com_limites(): max_turns + asyncio.wait_for, com um erro para cada problema

REFERÊNCIAS NAS AULAS (compare cada função com o exemplo de origem)
  aula3/agente_retry.py                    4.1  injetar a data de hoje nas instruções (o modelo não tem relógio)
  aula3/agente_retry2.py                   4.2  retry com backoff; erro de NEGÓCIO (não repete) x erro TÉCNICO (repete)
  aula6/exemplos/11_grafo_real/main.py     4.3  buscar_feriados na MESMA API (BrasilAPI), com User-Agent e plano B local
  aula3/agente_retry4.py                   4.5  a MESMA API de câmbio (Frankfurter)
  aula3/agente_retry3.py                   4.6  idempotência com hash (chave_idempotencia)
  aula3/agente_parada3.py                  4.7  asyncio.wait_for (tempo) x MaxTurnsExceeded (loop)

Rodar:
    python etapa04_ferramentas.py                      # online: feriados da BrasilAPI e cotação real
    $env:FERIADOS_OFFLINE = "1"                # PowerShell (Linux/Mac: export FERIADOS_OFFLINE=1)
    python etapa04_ferramentas.py                      # offline: 3 tentativas visíveis e plano B local

Para pensar (e responder no ENTREGA.md): por que a espera DOBRA a cada tentativa? Por que o protocolo é um hash dos campos
e não um número sequencial? O que aconteceria se buscar_feriados não tivesse cache?
"""
import asyncio
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

from agents import Agent, MaxTurnsExceeded, Runner

from dados_rh import carregar_feriados_locais

URL_FERIADOS = "https://brasilapi.com.br/api/feriados/v1/{ano}"
URL_CAMBIO = "https://api.frankfurter.app/latest?from=USD&to=BRL"
DIAS_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def texto_hoje() -> str:
    """4.1 -- 'segunda-feira, 12/10/2026 (2026-10-12)'. O LLM não sabe que dia é hoje: quem sabe é o seu código."""
    hoje = date.today()
    return f"{DIAS_PT[hoje.weekday()]}, {hoje:%d/%m/%Y} ({hoje.isoformat()})"


def get_json_com_retry(url: str, tentativas: int = 3, espera_base: float = 0.5, timeout: float = 5) -> dict | list:
    """4.2 -- GET com retry. Falha TÉCNICA (rede, timeout, HTTP 5xx) vale tentar de novo; na última, a exceção sobe."""
    for n in range(1, tentativas + 1):
        try:
            if os.getenv("FERIADOS_OFFLINE") == "1":  # simula a internet fora do ar, para testar o plano B
                raise urllib.error.URLError("offline")
            pedido = urllib.request.Request(url, headers={"User-Agent": "curso-pcdf/1.0"})  # sem ele: HTTP 403
            with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
                return json.load(resposta)
        except (urllib.error.URLError, TimeoutError, OSError) as erro:
            print(f"[retry] tentativa {n} falhou: {erro}")
            if n == tentativas:
                raise
            time.sleep(espera_base * 2 ** (n - 1))  # backoff exponencial: 0.5 s, 1 s, 2 s...


_CACHE_FERIADOS: dict[int, tuple[dict[str, str], str]] = {}


def buscar_feriados(ano: int) -> tuple[dict[str, str], str]:
    """4.3 -- ({"2027-04-21": "Tiradentes", ...}, fonte). fonte: "brasilapi", "arquivo_local" ou "indisponivel".

    O cache evita chamar a API a cada data consultada (dias_uteis pergunta dia por dia)."""
    if ano in _CACHE_FERIADOS:
        return _CACHE_FERIADOS[ano]
    try:
        feriados = {f["date"]: f["name"] for f in get_json_com_retry(URL_FERIADOS.format(ano=ano))}
        resultado = (feriados, "brasilapi")
    except Exception:
        # Plano B: a cópia local só tem 2027. Para outro ano, seguimos sem feriados (e a fonte avisa isso).
        resultado = (carregar_feriados_locais(), "arquivo_local") if ano == 2027 else ({}, "indisponivel")
    _CACHE_FERIADOS[ano] = resultado
    return resultado


def eh_dia_util(dia: date) -> bool:
    """Segunda a sexta e não feriado."""
    feriados, _ = buscar_feriados(dia.year)
    return dia.weekday() < 5 and dia.isoformat() not in feriados


def dias_uteis(inicio: str, fim: str) -> int:
    """4.4 -- Dias úteis entre inicio e fim (AAAA-MM-DD), inclusive."""
    dia, ultimo, total = date.fromisoformat(inicio), date.fromisoformat(fim), 0
    while dia <= ultimo:
        total += eh_dia_util(dia)
        dia += timedelta(days=1)
    return total


def data_retorno(fim: str) -> str:
    """4.4 -- O primeiro dia útil DEPOIS de `fim`."""
    dia = date.fromisoformat(fim) + timedelta(days=1)
    while not eh_dia_util(dia):
        dia += timedelta(days=1)
    return dia.isoformat()


def inicio_permitido(inicio: str) -> bool:
    """4.4 -- Regra N3: as férias não podem começar nos 2 dias antes de feriado ou fim de semana.
    Ou seja: o dia de início e os 2 dias seguintes precisam ser úteis (por isso quinta e sexta nunca podem)."""
    dia = date.fromisoformat(inicio)
    return all(eh_dia_util(dia + timedelta(days=k)) for k in range(3))


def cotacao_usd_brl() -> float | None:
    """4.5 -- Cotação USD->BRL de hoje, ou None se a API falhar (o Financeiro escreve "a calcular": NÃO inventa câmbio)."""
    try:
        return get_json_com_retry(URL_CAMBIO)["rates"]["BRL"]
    except Exception:
        return None


def gerar_protocolo(matricula: str, tipo: str, data_inicio: str | None, data_fim: str | None) -> str:
    """4.6 -- 8 primeiros caracteres do SHA-256 dos campos normalizados. O MESMO pedido gera o MESMO protocolo
    (C1 e C8: 'ae788d33'), então gravar duas vezes não duplica: é a idempotência da Aula 3."""
    bruto = "|".join((campo or "").strip().lower() for campo in (matricula, tipo, data_inicio, data_fim))
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:8]


class TempoEsgotado(Exception):
    """O agente demorou mais que o limite de tempo."""


class LoopExcedido(Exception):
    """O agente passou de max_turns (está em loop)."""


async def rodar_com_limites(agente: Agent, entrada: str, max_turns: int = 8, timeout_s: float = 90, **kwargs):
    """4.7 -- Runner.run com DOIS limites: tempo (wait_for) e voltas do loop (max_turns), cada um com o seu erro.
    **kwargs repassa hooks=..., context=... para o Runner (o item opcional 🆕 B usa hooks)."""
    try:
        return await asyncio.wait_for(Runner.run(agente, entrada, max_turns=max_turns, **kwargs), timeout=timeout_s)
    except asyncio.TimeoutError as erro:
        raise TempoEsgotado(f"{agente.name} passou de {timeout_s}s") from erro
    except MaxTurnsExceeded as erro:
        raise LoopExcedido(f"{agente.name} passou de {max_turns} turnos") from erro


def rodar_com_limites_sync(agente: Agent, entrada: str, **kwargs):
    """Versão síncrona, para usar dentro dos nós do grafo e no fluxo linear."""
    return asyncio.run(rodar_com_limites(agente, entrada, **kwargs))


if __name__ == "__main__":
    inicio = time.perf_counter()
    feriados, fonte = buscar_feriados(2027)
    print(f"feriados 2027: {len(feriados)} (fonte: {fonte}, {time.perf_counter() - inicio:.1f}s)")
    print("hoje:", texto_hoje())
    for dia, esperado in [("2027-04-12", True), ("2027-04-30", False), ("2027-04-15", False), ("2027-05-03", True)]:
        print(f"inicio_permitido({dia}) = {inicio_permitido(dia)}  (esperado {esperado})")
    print("dias úteis 12/04 a 26/04/2027:", dias_uteis("2027-04-12", "2027-04-26"), "| retorno:", data_retorno("2027-04-26"))
    print("cotação USD->BRL:", cotacao_usd_brl())
    p1 = gerar_protocolo("1001", "abono", "2027-04-09", "2027-04-09")
    p8 = gerar_protocolo(" 1001 ", "ABONO", "2027-04-09", "2027-04-09")
    print(f"protocolo C1={p1} C8={p8} iguais={p1 == p8}")
