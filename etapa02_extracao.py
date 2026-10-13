"""
ETAPA 2 -- Extração estruturada do pedido (15 min) e 🆕 A -- votação em paralelo (OPCIONAL, bônus).

ESQUELETO: implemente as etapas na ordem (troque cada raise NotImplementedError pelo código da etapa).
  ETAPA 2.1 -- complete o modelo Pydantic `Pedido` (campos + Field(description=...))
  ETAPA 2.2 -- criar_extrator(): um Agent com output_type=Pedido
  ETAPA 2.3 -- extrair(): roda UM extrator e devolve um Pedido
  --- daqui para baixo é OPCIONAL (item 🆕 A, vale bônus). Pule se estiver sem tempo: o resto do sistema não depende dele.
  🆕 A.1    -- INSTRUCOES_VOTANTES: 3 instruções ligeiramente diferentes
  🆕 A.2    -- extrair_com_votacao(): os 3 extratores AO MESMO TEMPO (asyncio.gather)
  (PRONTO)  -- votar(): maioria por campo; sem maioria em tipo/datas -> divergencia=True
  (PRONTO)  -- no __main__: o tempo em paralelo x em sequência

REFERÊNCIAS NAS AULAS
  aula2/agente_output.py                   output_type com um BaseModel simples
  aula2/agente_output2.py                  Enum + listas + Field(description=...)          <- o mais parecido
  aula7/exemplos/08_paralelismo/main.py    🆕 A: o CONCEITO de paralelismo (lá: tarefas DIFERENTES para ganhar tempo;
                                           aqui: a MESMA tarefa 3 vezes para ganhar confiabilidade)
  aula3/agente_parada3.py                  Runner.run (assíncrono) dentro de asyncio, como em A.2
  aula3/agente_retry.py                    por que a data de hoje entra nas instruções (já feito abaixo, com texto_hoje())

Rodar:
    python etapa02_extracao.py            # extrai C1, C2, C5 e C11
    python etapa02_extracao.py --votacao  # 🆕 A: C1, C2 e C9 com 3 votos e o tempo medido

Pronto quando: C2 sai com dias_vendidos=10, C11 com tipo_destino="exterior", C5 com matricula=None;
               na votação, C1/C2 unânimes e C9 mostrando os votos.
"""
import asyncio
import sys
import time
from collections import Counter
from enum import Enum

from agents import Agent, ModelSettings, Runner
from pydantic import BaseModel, Field

from dados.casos import CASOS
from etapa04_ferramentas import texto_hoje
from provedor import configurar

MODELO = configurar()


class TipoPedido(str, Enum):
    FERIAS = "ferias"
    ABONO = "abono"
    DIARIA = "diaria"
    LICENCA_SAUDE = "licenca_saude"
    OUTRO = "outro"


class TipoDestino(str, Enum):
    CAPITAL = "capital"
    INTERIOR = "interior"
    EXTERIOR = "exterior"


# ETAPA 2.1 -- Modelo Pydantic com todos os campos + Field(description=...) que o LLM lê.
class Pedido(BaseModel):
    tipo: TipoPedido = Field(description=(
        "Tipo do pedido: 'ferias' (descanso anual, pode incluir venda de dias), 'abono' (folga de 1 dia útil), "
        "'diaria' (viagem a serviço), 'licenca_saude' (afastamento por doença) ou 'outro'. "
        "Atenção: 'vender dias' ou 'abono pecuniário' é tipo 'ferias' com dias_vendidos, NÃO tipo 'abono'."))
    matricula: str | None = Field(None, description=(
        "Matrícula do servidor, 4 dígitos (ex.: '1002'). Use null se o servidor não informou a matrícula no texto. "
        "Nunca invente nem deduza uma matrícula."))
    data_inicio: str | None = Field(None, description=(
        "Primeiro dia do afastamento ou da viagem, no formato AAAA-MM-DD. Se o ano não foi dito, use a próxima "
        "ocorrência daquela data a partir de hoje. Use null se o servidor não disse o DIA exato "
        "(ex.: 'agosto de 2027' ou 'uns dias em maio' -> null). Nunca escolha um dia por conta própria."))
    data_fim: str | None = Field(None, description=(
        "Último dia do afastamento ou da viagem, no formato AAAA-MM-DD. No abono (1 dia), é igual à data_inicio. "
        "Use null se o servidor não disse o DIA exato. Nunca escolha um dia por conta própria."))
    dias_vendidos: int = Field(default=0, ge=0, le=10, description=(
        "Dias de férias que o servidor quer VENDER (abono pecuniário, regra N2), de 0 a 10. "
        "Preencha só se ele pedir explicitamente para vender dias; caso contrário, 0."))
    destino: str | None = Field(None, description=(
        "Só para diária: a cidade E o país de destino da viagem a serviço, no formato 'Cidade, País' "
        "(ex.: 'Buenos Aires, Argentina'; 'Belo Horizonte, Brasil'). Nos outros tipos, null."))
    tipo_destino: TipoDestino | None = Field(None, description=(
        "Só para diária. Olhe o PAÍS escrito em destino: se não for Brasil, é 'exterior', mesmo que a cidade seja "
        "capital de outro país. Se for Brasil: 'capital' (capital de estado brasileiro) ou 'interior' (outra "
        "cidade brasileira). Nos outros tipos, null."))
    justificativa: str = Field(description=(
        "Resumo curto do motivo do pedido, em uma frase. Nunca inclua CPF, CID, diagnóstico ou outro dado de saúde."))


# ETAPA 2.2 -- Agente extrator: lê texto livre e devolve um Pedido estruturado.
def criar_extrator(instrucoes: str, input_guardrails: list | None = None) -> Agent:
    return Agent(
        name="Extrator",
        model=MODELO.split(":", 1)[-1],  # preserva o case (ex.: "Qwen3.8-27B-FP8")
        model_settings=ModelSettings(temperature=0),  # sem limite de tokens: o Qwen3 "pensa" antes do JSON
        instructions=instrucoes,
        output_type=Pedido,
        input_guardrails=input_guardrails or [],
    )


# Regras de cada campo, montadas a partir das descriptions do Pedido. Servidores locais (Ollama, vLLM) usam o
# esquema só para forçar o formato e não o mostram ao modelo; por isso as descriptions entram também no texto.
_CAMPOS = "\n".join(f"- {nome}: {campo.description}" for nome, campo in Pedido.model_fields.items())

INSTRUCOES_EXTRATOR = (
    f"Hoje é {texto_hoje()}. "  # (PRONTO) a data real: o modelo não tem relógio (aula3/agente_retry.py)
    "Você extrai pedidos de servidores para o RH (férias, abono ou diária). "
    "Regras: datas sempre no formato AAAA-MM-DD; não invente o que não foi dito (use null em matrícula, datas e "
    "destino ausentes; só mês ou período vago, sem o dia exato, também é null); dias vendidos só se o servidor "
    "pedir explicitamente para vender dias; 'vender dias' é férias com dias_vendidos, não abono; "
    "na diária, destino fora do Brasil é sempre 'exterior', mesmo que seja capital de outro país; "
    "a justificativa nunca leva CPF nem dado de saúde.\n\n"
    "Como preencher cada campo:\n" + _CAMPOS
)


# ETAPA 2.3 -- Roda UM extrator e devolve o Pedido (final_output já é o objeto, não texto).
def extrair(texto: str) -> Pedido:
    resultado = Runner.run_sync(criar_extrator(INSTRUCOES_EXTRATOR), texto)
    return resultado.final_output


# ------------------------------------------------------------------ 🆕 A: votação (OPCIONAL, bônus)
# Para ligar no grafo depois de pronto: USAR_VOTACAO = True em etapa07_grafo.py.
# 🆕 A.1 -- Três instruções ligeiramente diferentes: literal, conferindo datas, perspectiva de RH.
_REGRAS_COMUNS = (
    "Datas no formato AAAA-MM-DD; use null para matrícula, datas e destino que não foram ditos "
    "(data sem o dia exato também é null); destino fora do Brasil é 'exterior'; "
    "dias vendidos só se o servidor pedir explicitamente; 'vender dias' é férias, não abono; "
    "a justificativa nunca leva CPF nem dado de saúde.\n\nComo preencher cada campo:\n" + _CAMPOS
)
INSTRUCOES_VOTANTES: list[str] = [
    f"Hoje é {texto_hoje()}. Você extrai pedidos de servidores para o RH de forma LITERAL: registre só o que está "
    f"escrito, sem interpretar além do texto. {_REGRAS_COMUNS}",
    f"Hoje é {texto_hoje()}. Você extrai pedidos de servidores para o RH e CONFERE AS DATAS: resolva o ano a partir de "
    f"hoje, confira se o fim vem depois do início e se o período faz sentido no calendário. {_REGRAS_COMUNS}",
    f"Hoje é {texto_hoje()}. Você é um analista experiente de RH extraindo pedidos de servidores: identifique o tipo "
    f"de pedido como o RH o classificaria (férias, abono, diária). {_REGRAS_COMUNS}",
]


# 🆕 A.2 -- Fan-out: 3 extratores em paralelo; fan-in: votação por maioria.
async def extrair_com_votacao(texto: str) -> tuple[Pedido, bool, list[Pedido]]:
    extratores = [criar_extrator(instrucoes) for instrucoes in INSTRUCOES_VOTANTES]
    resultados = await asyncio.gather(*(Runner.run(e, texto) for e in extratores))
    votos = [r.final_output for r in resultados]
    pedido, divergencia = votar(votos)
    return pedido, divergencia, votos


def votar(votos: list[Pedido]) -> tuple[Pedido, bool]:
    """(PRONTO) Maioria por campo. Sem maioria (2 de 3) em `tipo` ou nas datas -> divergencia=True: o sistema vai
    pedir esclarecimento em vez de adivinhar. Os campos não votados vêm do primeiro voto."""
    decidido, divergencia = {}, False
    for campo in ("tipo", "matricula", "data_inicio", "data_fim", "dias_vendidos"):
        valor, quantos = Counter(getattr(voto, campo) for voto in votos).most_common(1)[0]
        decidido[campo] = valor
        if quantos < 2 and campo in ("tipo", "data_inicio", "data_fim"):
            divergencia = True
    return votos[0].model_copy(update=decidido), divergencia


def _demo_extracao() -> None:
    for nome in ("C1_abono_simples", "C2_ferias_com_venda", "C5_sem_matricula", "C11_diaria_exterior"):
        pedido = extrair(CASOS[nome]["pedido"])
        print(f"\n{nome}\n  {pedido.model_dump()}")


def _demo_votacao() -> None:
    for nome in ("C1_abono_simples", "C2_ferias_com_venda", "C9_divergencia"):
        texto = CASOS[nome]["pedido"]
        inicio = time.perf_counter()
        pedido, divergencia, votos = asyncio.run(extrair_com_votacao(texto))
        segundos = time.perf_counter() - inicio
        print(f"\n{nome}  ({segundos:.1f}s, divergencia={divergencia})")
        for i, voto in enumerate(votos, 1):
            print(f"  voto {i}: tipo={voto.tipo.value} {voto.data_inicio}..{voto.data_fim} vende={voto.dias_vendidos}")
        print(f"  decisão: {pedido.model_dump()}")
    # (PRONTO) os mesmos 3 extratores EM SEQUÊNCIA, para comparar: o paralelo fica perto do tempo de UMA chamada?
    texto = CASOS["C2_ferias_com_venda"]["pedido"]
    inicio = time.perf_counter()
    for instrucoes in INSTRUCOES_VOTANTES:
        Runner.run_sync(criar_extrator(instrucoes), texto)
    print(f"\nC2 em sequência: {time.perf_counter() - inicio:.1f}s (compare com o tempo do C2 em paralelo, acima)")


if __name__ == "__main__":
    print(f"[modelo] {MODELO}")
    _demo_votacao() if "--votacao" in sys.argv else _demo_extracao()