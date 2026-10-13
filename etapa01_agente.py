"""
ETAPA 1 -- Primeiro agente com tool local (15 min).

ESQUELETO: implemente as etapas na ordem. Cada uma está marcada com um comentário e um
raise NotImplementedError: troque esse raise pelo código da etapa e rode o arquivo.
  ETAPA 1.1 -- a tool consultar_servidor (SEM o salário)
  ETAPA 1.2 -- o agente AtendenteRH com a tool
  ETAPA 1.3 -- duas perguntas: uma que precisa da tool e uma que não precisa

REFERÊNCIAS NAS AULAS
  aula1/segundo_agente.py                            Agent + @function_tool + Runner.run_sync (o básico)
  exercicios_resolvidos/aula4/ex10_function_tool.py  tool que consulta uma TABELA e devolve JSON  <- o mais parecido
  aula8/exemplos/02_agente_tool/main.py              o agente decide quando chamar a tool (e quando não)

Rodar (a partir de aula10/):
    python etapa01_agente.py

Pronto quando: a tool é chamada só na primeira pergunta (o print dentro dela prova).
"""
import json

from agents import Agent, Runner, function_tool

from dados_rh import servidor_publico
from provedor import configurar, AJUSTES

MODELO = configurar()  # LLM REAL: PROVEDOR no .env (openai ou ollama)


# ETAPA 1.1 -- Tool que consulta o cadastro de UM servidor pela matrícula (sem o salário).
@function_tool
def consultar_servidor(matricula: str) -> str:
    """Consulta o cadastro de um servidor pela matrícula.

    Use quando a pergunta for sobre os dados de UM servidor específico: nome, equipe, saldo de férias
    ou abonos restantes. NÃO use para perguntas gerais sobre regras ou conceitos de RH (ex.: o que é
    abono pecuniário), que não dependem de nenhum servidor.

    Args:
        matricula: matrícula do servidor, só os dígitos (ex.: "1002").

    Returns:
        JSON com nome, equipe, saldo de férias e abonos restantes do servidor (o salário não é
        informado), ou um aviso de "matrícula não encontrada".
    """
    print("[tool] consultar_servidor", matricula)
    return json.dumps(servidor_publico(matricula), ensure_ascii=False)


# ETAPA 1.2 -- Cria o agente que atende os servidores, com a tool de consulta ao cadastro.
def criar_atendente() -> Agent:
    return Agent(
        name="AtendenteRH",
        model=MODELO.split(":", 1)[-1],  # extrai só o nome do modelo (ex.: "Qwen3.8-27B-FP8")
        model_settings=AJUSTES,
        instructions=(
            "Você é o atendente do setor de Gestão de Pessoas e responde dúvidas dos servidores.\n"
            "- Responda sempre em português do Brasil, de forma breve (até 3 frases).\n"
            "- Se a pergunta for sobre os dados de UM servidor (saldo de férias, abonos, equipe), chame a tool "
            "consultar_servidor com a matrícula e responda com base no resultado. Nunca invente saldos ou dados.\n"
            "- Se a pergunta for geral (conceitos, regras), responda direto, sem chamar a tool.\n"
            "- Se a matrícula não for encontrada, diga isso e peça para o servidor conferir o número."
        ),
        tools=[consultar_servidor],
    )


# ETAPA 1.3 -- Roda as duas perguntas: a primeira precisa da tool, a segunda não.
def main() -> None:
    atendente = criar_atendente()
    perguntas = [
        "Quantos dias de férias a matrícula 1002 ainda tem?",  # precisa da tool
        "O que é abono pecuniário?",                           # não precisa
    ]
    for pergunta in perguntas:
        print(f"\n[pergunta] {pergunta}")
        resultado = Runner.run_sync(atendente, pergunta)
        print(f"[resposta] {resultado.final_output}")


if __name__ == "__main__":
    print(f"[modelo] {MODELO}")
    main()
