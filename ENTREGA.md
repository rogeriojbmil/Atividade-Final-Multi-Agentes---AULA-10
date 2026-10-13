# Entrega: Assistente de Gestão de Pessoas

**Aluno(s):** Rogério Alves da Conceição
**Até onde chegou:** ( ) Marco mínimo (Etapa 6)  ( ) Marco completo (Etapa 9)  (x) Etapas 10–11
**Opcionais e bônus feitos:** (x) 🆕 A  ( ) 🆕 B  ( ) 🆕 C  ( ) Outro: ______

## Etapa 0: quem verifica cada regra?

| Regra | Tema | Quem verifica (função Python / agente / humano) | Por quê | Onde foi implementada (preencha na Etapa 11) |
|---|---|---|---|---|
| N1 | férias | função Python | conta: dias corridos >= 5 e <= saldo | `violacoes_objetivas()` em `etapa06_regras.py`, chamada no nó `consolidar` (`etapa07_grafo.py`) |
| N2 | férias | função Python | conta: dias + vendidos <= saldo, vendidos <= 10 | `etapa06_regras.py`; o agente Financeiro (`etapa06_agentes.py`) só calcula e explica o valor da venda |
| N3 | férias | função Python | consulta de calendário (feriados e fim de semana) | `inicio_permitido()` e `buscar_feriados()` (`etapa04_ferramentas.py`), usados por `etapa06_regras.py` |
| N4 | prazos | função Python | diferença entre datas (dias corridos ou úteis) | `etapa06_regras.py` (30 dias para férias, 2 dias úteis para abono, 10 dias para diária) |
| N5 | escala | função Python | contagem de afastados da equipe no período x limite de 30% | tool `consultar_escala` (`etapa05_mcp_rh.py`) + `etapa06_regras.py` (só férias e abono); o agente Escala sugere outro período |
| N6 | abono | função Python | dia útil e saldo de abonos | `etapa06_regras.py`, com o cadastro da tool `consultar_servidor` (`etapa05_mcp_rh.py`) |
| N7 | diária | função Python | conta (diárias + meia diária, câmbio); o agente Financeiro só explica | tool `tabela_diarias` (`etapa05_mcp_rh.py`) + `cotacao_usd_brl()` (`etapa04_ferramentas.py`); agente Financeiro (`etapa06_agentes.py`) |
| N8 | aprovação | humano | é decisão da chefia; o server só confere se o aprovador é a chefia certa | `precisa_chefia()` (`etapa06_regras.py`); nó `aprovacao_chefia` com `interrupt()` (`etapa07_grafo.py`); `registrar_decisao` nega autoaprovação e chefia errada (`etapa05_mcp_rh.py`) |
| N9 | saúde | função Python (guardrail) | regex de CID/CPF barra antes de qualquer agente ver o texto; o classificador (agente) cobre o que a regex não pega | `encontrar_dado_sensivel()` e os `@input_guardrail` (`etapa03_guardrails.py`), no nó `proteger_entrada` (`etapa07_grafo.py`) |
| N10 | dados | função Python (guardrail de saída) | regex no despacho antes de gravar | guardrail de saída no nó `registrar` (`etapa07_grafo.py`, Etapa 9.4), com `encontrar_dado_sensivel()` |

## Etapa 11: os 12 casos

Compare **caminho e estado**, não o texto do despacho.

| Caso | Caminho percorrido | Resultado (bloqueado / pediu dados / triagem humana / indeferido / pausou na chefia / registrado + protocolo) | Bateu com o esperado? |
|---|---|---|---|
| C1_abono_simples | receber -> proteger_entrada -> extrair -> identificar_servidor -> calcular_periodo -> escala -> financeiro -> normas -> consolidar -> redigir_despacho -> validar -> registrar | registrado (deferido, sem chefia), protocolo ae788d33 | sim |
| C2_ferias_com_venda | receber -> proteger_entrada -> extrair -> identificar_servidor -> calcular_periodo -> escala -> financeiro -> normas -> consolidar -> redigir_despacho -> validar -> aprovacao_chefia (pausou) -> (sim 1010) registrar | pausou na chefia; depois registrado (deferido pela 1010), protocolo b7b6f485 | sim |
| C3_dado_de_saude | receber -> proteger_entrada -> recusar | bloqueado (CPF/CID no texto) | sim |
| C4_fora_do_escopo | receber -> proteger_entrada -> recusar | bloqueado (fora do escopo) | sim |
| C5_sem_matricula | receber -> proteger_entrada -> extrair -> pedir_dados | pediu dados (sem matrícula) | sim |
| C6_conflito_de_escala | receber -> proteger_entrada -> extrair -> identificar_servidor -> calcular_periodo -> escala -> financeiro -> normas -> consolidar -> redigir_despacho -> validar -> registrar | registrado (indeferido, N5), protocolo 6f1b47d7 | sim |
| C7_autoaprovacao | receber -> proteger_entrada -> recusar | bloqueado (fora do escopo / manipulação) | sim |
| C8_idempotencia | igual ao C1 | registrado como duplicado, mesmo protocolo ae788d33 (não gravou de novo) | sim |
| C9_divergencia | receber -> proteger_entrada -> extrair -> pedir_dados | pediu dados (pedido vago, sem datas exatas) | sim |
| C10_zona_cinzenta | receber -> proteger_entrada -> extrair -> pedir_dados | pediu dados | sim |
| C11_diaria_exterior | receber -> proteger_entrada -> extrair -> identificar_servidor -> calcular_periodo -> escala -> financeiro -> normas -> consolidar -> redigir_despacho -> validar -> aprovacao_chefia (pausou) -> (sim 1011) registrar | pausou na chefia; depois registrado (deferido pela 1011), protocolo ec67dba1 | sim |
| C12_inicio_proibido | receber -> proteger_entrada -> extrair -> identificar_servidor -> calcular_periodo -> escala -> financeiro -> normas -> consolidar -> redigir_despacho -> validar -> registrar | registrado (indeferido, N3), protocolo 7c458e62 | sim |

O C9 e o C10 dependem do LLM. Nesta execução os dois saíram por `pedir_dados`: o extrator não conseguiu preencher matrícula e datas exatas com segurança, e o grafo pediu os dados em vez de adivinhar. Em outra execução o resultado desses dois pode mudar.

## O grafo

```mermaid
%% cole aqui a saída de: python etapa07_grafo.py --mermaid
```

## Etapa 4 (pronta): o que eu entendi

- Diferença entre a saída online e a offline:
- Por que a espera do retry dobra a cada tentativa:
- Por que o protocolo é um hash dos campos (e não um número sequencial):
- O que aconteceria sem o cache de feriados:

## Observabilidade (C2)

- Onde o tempo foi gasto:
- Tokens totais: ___

## Opcionais (preencha só os que fez)

- 🆕 A: votos e decisão do C9: ___ ; tempo dos 3 extratores em paralelo ___ s, em sequência ___ s
- 🆕 B: saída do `python etapa06_linear.py --governanca`:
- 🆕 C: caminho do C10 com a triagem humana (sim e não):

## Reflexão (até 3 linhas cada)

1. Quem decide o caminho no seu sistema: o LLM, o grafo, as regras ou um humano? Dê um exemplo de cada.
2. Se o guardrail de entrada falhar, o que ainda impede uma autoaprovação?
3. Por que o nó da chefia não pode gravar nada antes do `interrupt()`?
4. Qual dado veio do **MCP**, qual de **API externa** e qual de **tool local**? Por que essa divisão?
5. O que você mudaria para colocar este sistema em produção?
6. (Só se fez) 🆕 A: votar triplica o custo da extração. Em que pedidos vale a pena?
7. (Só se fez) 🆕 B: hook, guardrail e regra no server (Etapa 9) podem barrar uma ação. Qual a diferença de **onde** cada um atua?
8. (Só se fez) 🆕 C: o que muda quando o humano decide a **entrada** em vez da **saída**? Quem é consultado em cada pausa?

## De onde veio cada parte

| Arquivo / trecho | Exemplo das aulas em que me baseei | O que precisei adaptar |
|---|---|---|
| | | |