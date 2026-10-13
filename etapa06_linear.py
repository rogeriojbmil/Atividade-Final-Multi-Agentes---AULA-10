"""
ETAPA 6 -- O sistema inteiro como um FLUXO LINEAR em Python puro (sem LangGraph) ⇒ Marco mínimo.

ESQUELETO:
  ETAPA 6.3 -- analisar(): o Coordenador junta os pareceres (com os limites da Etapa 4.7)
  ETAPA 6.4 -- processar(): guardrails -> extração -> MCP -> feriados -> regras -> coordenador -> redator
               -> protocolo -> MCP (registrar)
  🆕 B.4    -- (OPCIONAL, bônus) testar_governanca(): os dois testes de bloqueio do --governanca

REFERÊNCIAS NAS AULAS
  aula6/exemplos/01_fluxo_linear/main.py     o fluxo linear: funciona, mas sem decisão nem volta (por isso a Etapa 7)
  aula4/ex03_agente_as_tool.py               o Coordenador com especialistas como tools
  aula7/exemplos/02_agentes_especializados/main.py   cada especialista imprime o que fez: dá para saber quem fez o quê

Rodar:
    python etapa06_linear.py                 # C1, C2, C6 e C11
    python etapa06_linear.py --governanca    # 🆕 B (opcional): os dois testes de bloqueio

Pronto quando: C1, C2 e C11 são gravados com protocolo, C6 vira indeferimento com sugestão de datas, e você sabe dizer
qual agente escreveu cada parte. (Opcional) no --governanca: a tool restrita NÃO executa e o C2 para no orçamento.
"""
import json
import os
import sys

from agents import RunHooks

import etapa06_agentes as agentes
from etapa05_cliente_mcp import chamar_mcp
from dados.casos import CASOS
from etapa02_extracao import extrair
from etapa04_ferramentas import gerar_protocolo, rodar_com_limites_sync
from etapa10_governanca import Governanca, LimiteExcedido
from etapa03_guardrails import encontrar_dado_sensivel, nota_escopo, LIMIAR, MENSAGENS
from provedor import configurar
from etapa06_regras import precisa_chefia, resumo_periodo, violacoes_objetivas

MODELO = configurar()

TEMPO_LIMITE = 300  # segundos por agente: o modelo local leva mais que os 90 s padrão do rodar_com_limites


# ETAPA 6.3 -- O Coordenador recebe os fatos (pedido, servidor, período e violações objetivas), consulta os
# especialistas como tools e devolve o parecer único. Imprime quais especialistas ele consultou.
def analisar(pedido: dict, servidor: dict, periodo: dict, violacoes: list[str], hooks: RunHooks | None = None) -> str:
    fatos = (
        f"Pedido: {json.dumps(pedido, ensure_ascii=False)}\n"
        f"Servidor: matrícula {servidor['matricula']}, equipe {servidor['equipe']}\n"
        f"Período: {json.dumps(periodo, ensure_ascii=False)}\n"
        f"Violações objetivas (definitivas): {violacoes or 'nenhuma'}"
    )
    resultado = rodar_com_limites_sync(agentes.criar_coordenador(hooks), fatos, hooks=hooks, timeout_s=TEMPO_LIMITE)
    consultados = [getattr(item.raw_item, "name", "?") for item in resultado.new_items if item.type == "tool_call_item"]
    print(f"[6/9] coordenador: consultou {', '.join(consultados) or 'nenhum especialista'}")
    return resultado.final_output


# ETAPA 6.4 -- O fluxo linear completo, em 9 passos, imprimindo cada um. Cada saída antecipada (bloqueado,
# pedir_dados) é um "return" no meio da função: é o limite do fluxo linear que o grafo da Etapa 7 resolve.
def processar(texto: str, hooks: RunHooks | None = None) -> dict:
    # ETAPA 6.4 -- encadeie, imprimindo cada passo ("[1/9] guardrails", ...):
    #   1. encontrar_dado_sensivel / nota_escopo >= LIMIAR  -> devolva {"resultado": "bloqueado", "mensagem": ...}
    #   2. pedido = extrair(texto).model_dump(mode="json")  -> sem matrícula ou datas: {"resultado": "pedir_dados"}
    #   3. servidor = chamar_mcp("consultar_servidor", ...) -> não encontrado: {"resultado": "pedir_dados"}
    #   4. periodo = resumo_periodo(...)                     (API de feriados, Etapa 4)
    #   5. escala = chamar_mcp("consultar_escala", ...); violacoes = violacoes_objetivas(...)
    #   6. parecer = analisar(...)
    #   7. despacho = rodar_com_limites_sync(agentes.criar_redator(), <fatos + parecer + violações>).final_output
    #   8. protocolo = gerar_protocolo(...)
    #   9. chamar_mcp("registrar_decisao", {..., "decisao": "indeferido" se houver violação senão "deferido",
    #        "aprovador": "pendente_chefia" se precisa_chefia(...) senão "sistema", "token": os.getenv("TOKEN_REGISTRO")})
    #      (a aprovação de verdade da chefia entra na Etapa 8; aqui só marcamos que ela será necessária)
    #   Devolva {"resultado": ..., "protocolo": ..., "despacho": ..., "parecer": ...}.
    print("[1/9] guardrails")
    sensivel = encontrar_dado_sensivel(texto)
    if sensivel:
        return {"resultado": "bloqueado", "mensagem": MENSAGENS[sensivel]}
    nota, _motivo = nota_escopo(texto)
    if nota >= LIMIAR:
        return {"resultado": "bloqueado", "mensagem": MENSAGENS["fora_do_escopo"]}

    pedido = extrair(texto).model_dump(mode="json")
    print(f"[2/9] extração: {pedido['tipo']} {pedido['matricula']} {pedido['data_inicio']}..{pedido['data_fim']}")
    if not (pedido["matricula"] and pedido["data_inicio"] and pedido["data_fim"]):
        return {"resultado": "pedir_dados", "mensagem": "Informe a matrícula e as datas exatas (início e fim)."}

    servidor = chamar_mcp("consultar_servidor", {"matricula": pedido["matricula"]})
    if "nome" not in servidor:
        return {"resultado": "pedir_dados", "mensagem": f"Matrícula {pedido['matricula']} não encontrada."}
    print(f"[3/9] servidor: {servidor['nome']} ({servidor['equipe']})")

    periodo = resumo_periodo(pedido["data_inicio"], pedido["data_fim"])
    print(f"[4/9] período: {periodo['dias_uteis']} dia(s) útil(eis), retorno {periodo['retorno']} "
          f"(fonte: {periodo['fonte_feriados']})")

    escala = chamar_mcp("consultar_escala", {"equipe": servidor["equipe"], "inicio": pedido["data_inicio"],
                                             "fim": pedido["data_fim"]})
    violacoes = violacoes_objetivas(pedido, servidor, periodo, escala)
    print(f"[5/9] violações: {violacoes or 'nenhuma'}")

    parecer = analisar(pedido, servidor, periodo, violacoes, hooks)  # imprime o passo [6/9]

    decisao = "indeferido" if violacoes else "deferido"
    fatos = (
        f"Matrícula: {pedido['matricula']}\nTipo: {pedido['tipo']}\n"
        f"Período: {pedido['data_inicio']} a {pedido['data_fim']} (retorno em {periodo['retorno']})\n"
        f"Decisão: {decisao}\nViolações: {violacoes or 'nenhuma'}\nParecer dos especialistas:\n{parecer}"
    )
    print("[7/9] redator")
    despacho = rodar_com_limites_sync(agentes.criar_redator(), fatos, hooks=hooks, timeout_s=TEMPO_LIMITE).final_output

    protocolo = gerar_protocolo(pedido["matricula"], pedido["tipo"], pedido["data_inicio"], pedido["data_fim"])
    print(f"[8/9] protocolo {protocolo}")

    registro = chamar_mcp("registrar_decisao", {
        "protocolo": protocolo, "matricula": pedido["matricula"], "tipo": pedido["tipo"],
        "inicio": pedido["data_inicio"], "fim": pedido["data_fim"], "decisao": decisao,
        # a aprovação de verdade da chefia entra na Etapa 8; aqui só marcamos que ela será necessária
        "aprovador": "pendente_chefia" if precisa_chefia(pedido, violacoes) else "sistema",
        "despacho": despacho, "token": os.getenv("TOKEN_REGISTRO", ""),
    })
    print(f"[9/9] registrar: {registro}")
    if not registro.get("sucesso"):
        resultado = f"negado_pelo_server: {registro.get('erro', '')}"
    else:
        resultado = "duplicado" if registro.get("duplicado") else "registrado"
    return {"resultado": resultado, "protocolo": protocolo, "despacho": despacho, "parecer": parecer}


def testar_governanca() -> None:
    # 🆕 B.4 (opcional) -- dois testes, cada um tratando LimiteExcedido e imprimindo o motivo:
    #   a) coordenador = agentes.criar_coordenador(hooks=Governanca(), tools_extras=[agentes.consultar_remuneracao])
    #      pergunte "Qual o salário da matrícula 1002?" -> deve ser BARRADO e o print da tool NÃO pode aparecer.
    #   b) processar(CASOS["C2_ferias_com_venda"]["pedido"], hooks=Governanca(max_tools=1))
    #      -> deve parar ANTES do segundo especialista.
    raise NotImplementedError("🆕 B.4: testar_governanca")


if __name__ == "__main__":
    print(f"[modelo] {MODELO}")
    if "--governanca" in sys.argv:
        testar_governanca()
    else:
        for nome in ("C1_abono_simples", "C2_ferias_com_venda", "C6_conflito_de_escala", "C11_diaria_exterior"):
            print(f"\n=============== {nome}")
            print(json.dumps(processar(CASOS[nome]["pedido"]), ensure_ascii=False, indent=2))