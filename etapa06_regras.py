"""
ETAPA 6.0 -- As regras OBJETIVAS da norma, em Python puro (sem LLM). (PRONTO: leia, rode e entenda)

Na Etapa 0 você classificou cada regra N1..N10: função Python, agente ou humano. As que são CONTA (saldo, datas,
limite da escala) ficam aqui: um LLM pode errar uma soma, uma função não. O agente Normas (etapa06_agentes.py) continua
útil para EXPLICAR as regras no despacho, mas quem decide "violou ou não" é este módulo.

Este arquivo já vem implementado. Compare-o com a SUA tabela da Etapa 0: cada `if` abaixo é uma regra que você marcou
como "função Python". Faltou alguma? Sobrou alguma que você achava que era do agente?

  violacoes_objetivas(): a lista de violações ("N3: ...") de um pedido
  precisa_chefia(): regra N8

REFERÊNCIAS NAS AULAS
  aula6/exemplos/11_grafo_real/main.py   avaliar_risco: "tool local (regra de negócio, sem IA)" dentro do fluxo
  aula6/desafio3/ENUNCIADO.md            "LLM para ESCREVER, [regra/modelo tipado] para DECIDIR"

Rodar:
    python etapa06_regras.py      # confere as regras nos casos C1, C2, C6 e C12 com pedidos montados à mão (sem LLM)
"""
from datetime import date, timedelta

from etapa04_ferramentas import buscar_feriados, data_retorno, dias_uteis, eh_dia_util, inicio_permitido


def resumo_periodo(inicio: str, fim: str) -> dict:
    """(PRONTO, usa as suas funções da Etapa 4) Tudo o que os especialistas precisam saber sobre as datas."""
    d1, d2 = date.fromisoformat(inicio), date.fromisoformat(fim)
    feriados, fonte = buscar_feriados(d1.year)
    return {
        "inicio": inicio, "fim": fim,
        "dias_corridos": (d2 - d1).days + 1,
        "dias_uteis": dias_uteis(inicio, fim),
        "feriados_no_periodo": {d: n for d, n in feriados.items() if inicio <= d <= fim},
        "retorno": data_retorno(fim),
        "inicio_permitido_n3": inicio_permitido(inicio),
        "fonte_feriados": fonte,
    }


def _dias_uteis_ate(hoje: date, alvo: date) -> int:
    """(PRONTO) Dias úteis entre amanhã e o dia anterior a `alvo` (antecedência do abono, N4)."""
    return sum(1 for k in range(1, (alvo - hoje).days) if eh_dia_util(hoje + timedelta(k)))


def violacoes_objetivas(pedido: dict, servidor: dict, periodo: dict, escala: dict, hoje: date | None = None) -> list[str]:
    """Lista de violações objetivas, cada uma começando pelo código da regra (ex.: "N3: começa numa sexta...").

    Args:
        pedido: Pedido.model_dump() (tipo, data_inicio, data_fim, dias_vendidos...).
        servidor: o cadastro (consultar_servidor do MCP) -- saldo_ferias_dias, abonos_restantes.
        periodo: resumo_periodo(...).
        escala: consultar_escala do MCP -- limite_afastados e afastamentos (sem contar o próprio servidor).
        hoje: data do pedido (padrão: date.today()).
    """
    hoje = hoje or date.today()
    violacoes = []
    tipo = pedido["tipo"]
    inicio = date.fromisoformat(pedido["data_inicio"])
    # N5: os afastamentos que se sobrepõem ao período, SEM contar o próprio servidor
    outros = [a for a in escala.get("afastamentos", []) if a["matricula"] != servidor["matricula"]]

    if tipo == "ferias":
        dias, vendidos = periodo["dias_corridos"], pedido.get("dias_vendidos", 0)
        if dias < 5 or dias > servidor["saldo_ferias_dias"]:
            violacoes.append(f"N1: período de {dias} dias (mínimo 5, saldo {servidor['saldo_ferias_dias']})")
        if vendidos > 10 or dias + vendidos > servidor["saldo_ferias_dias"]:
            violacoes.append(f"N2: {dias} dias + {vendidos} vendidos passam do saldo ou do limite de 10")
        if not periodo["inicio_permitido_n3"]:
            violacoes.append(f"N3: as férias não podem começar em {pedido['data_inicio']} (véspera de feriado/fim de semana)")
        if (inicio - hoje).days < 30:
            violacoes.append("N4: férias exigem 30 dias de antecedência")

    if tipo == "abono":
        if not eh_dia_util(inicio) or servidor["abonos_restantes"] <= 0:
            violacoes.append("N6: abono só em dia útil e com saldo de abonos")
        if _dias_uteis_ate(hoje, inicio) < 2:
            violacoes.append("N4: abono exige 2 dias úteis de antecedência")

    if tipo == "diaria" and (inicio - hoje).days < 10:
        violacoes.append("N4: diária exige 10 dias de antecedência")

    if tipo in ("ferias", "abono") and len(outros) >= escala.get("limite_afastados", 1):
        quem = ", ".join(f"{a['matricula']} ({a['inicio']} a {a['fim']})" for a in outros)
        violacoes.append(f"N5: a equipe já tem {len(outros)} afastado(s) no período: {quem}")

    return violacoes


def precisa_chefia(pedido: dict, violacoes: list[str]) -> bool:
    """Regra N8: férias e diárias deferíveis precisam da chefia; abono que cumpre as regras, não.
    Indeferimento por violação objetiva também não precisa (é a norma que nega, não a chefia)."""
    return pedido["tipo"] in ("ferias", "diaria") and not violacoes


if __name__ == "__main__":
    hoje = date(2026, 10, 9)
    ana = {"matricula": "1001", "saldo_ferias_dias": 30, "abonos_restantes": 5}
    bruno = {"matricula": "1002", "saldo_ferias_dias": 30, "abonos_restantes": 3}
    carla = {"matricula": "1003", "saldo_ferias_dias": 20, "abonos_restantes": 5}
    diego = {"matricula": "1004", "saldo_ferias_dias": 30, "abonos_restantes": 5}
    sem_conflito = {"limite_afastados": 1, "afastamentos": []}
    conflito = {"limite_afastados": 1, "afastamentos": [{"matricula": "1006", "inicio": "2027-07-05", "fim": "2027-07-19"}]}
    testes = [
        ("C1", {"tipo": "abono", "data_inicio": "2027-04-09", "data_fim": "2027-04-09", "dias_vendidos": 0}, ana, sem_conflito, []),
        ("C2", {"tipo": "ferias", "data_inicio": "2027-04-12", "data_fim": "2027-04-26", "dias_vendidos": 10}, bruno, sem_conflito, []),
        ("C6", {"tipo": "ferias", "data_inicio": "2027-07-12", "data_fim": "2027-07-26", "dias_vendidos": 0}, diego, conflito, ["N5"]),
        ("C12", {"tipo": "ferias", "data_inicio": "2027-04-30", "data_fim": "2027-05-14", "dias_vendidos": 0}, carla, sem_conflito, ["N3"]),
    ]
    for nome, pedido, servidor, escala, esperado in testes:
        periodo = resumo_periodo(pedido["data_inicio"], pedido["data_fim"])
        v = violacoes_objetivas(pedido, servidor, periodo, escala, hoje)
        ok = sorted(x.split(":")[0] for x in v) == esperado
        print(f"{nome}: {v or 'nenhuma violação'}  chefia={precisa_chefia(pedido, v)}  {'OK' if ok else 'ESPERADO ' + str(esperado)}")
