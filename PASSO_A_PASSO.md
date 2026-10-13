# Passo a passo: Assistente de Gestão de Pessoas

Este é o roteiro para **implementar** o exercício. O `ENUNCIADO.md` diz **o que** o sistema faz e como ele é avaliado; este arquivo
diz **em que ordem** preencher cada lacuna, **onde** está o exemplo parecido nas aulas e **o que deve aparecer na tela** quando
a lacuna estiver certa.

## Como ler as saídas esperadas

| Marca | Significado | Como comparar |
|---|---|---|
| ✅ **Saída real** | Gerada rodando uma solução do exercício. Não depende do LLM. | Deve sair **igual** (só mudam data/hora de hoje e a ordem de linhas marcada como variável). |
| 🔸 **Saída ilustrativa** | Depende do LLM: o texto muda de uma execução para outra e de um modelo para outro. | Compare a **estrutura** e os **valores-chave** (tipo, datas, bloqueado ou não), **nunca o texto**. |

## Antes de começar (uma vez, de preferência antes da aula)

Configure o ambiente com o script (detalhes e a opção manual no [`README.md`](README.md)):

```powershell
cd C:\pcdf\aula10                                                   # ou onde estiver o seu clone
powershell -ExecutionPolicy Bypass -File .\configurar_ambiente.ps1   # Linux/Mac: bash configurar_ambiente.sh
.venv\Scripts\Activate.ps1                                          # Linux/Mac: source .venv/bin/activate
```

Ele cria o `.venv`, instala tudo, cria o `.env` (com um `TOKEN_REGISTRO` aleatório), pede a sua `OPENAI_API_KEY` e termina
rodando o `verificar_ambiente.py`. Só comece quando ele disser `Resultado: tudo certo`.

**Rode tudo de dentro de `aula10/`.** Os comandos abaixo assumem isso.

Três atalhos úteis durante o exercício:

```powershell
$env:FERIADOS_OFFLINE = "1"           # simula a BrasilAPI e a API de câmbio fora do ar
Remove-Item Env:FERIADOS_OFFLINE      # volta a usar a internet
Remove-Item saidas\registros.json, saidas\auditoria.jsonl, saidas\checkpoints.db -ErrorAction SilentlyContinue   # recomeça do zero
```

> Os registros ficam em `saidas/registros.json` **entre execuções**. Se você gravar o C1 na Etapa 6 e rodá-lo de novo no grafo,
> o resultado vai ser `duplicado` (é a idempotência funcionando). Para comparar com as saídas abaixo, apague `saidas/` como acima.

**Como funciona cada lacuna:** procure `# ETAPA n.m` no arquivo, apague o `raise NotImplementedError("ETAPA n.m: ...")` e
escreva o código. Rodar o arquivo antes de terminar mostra `NotImplementedError: ETAPA n.m`: é esperado, e diz onde você está.

**Ao terminar cada etapa, rode `python conferir.py N`** (N = número da etapa). Ele diz o que passou (`[OK]`), o que falta
(`[PENDENTE]`) e o que está errado (`[FALHOU]`, com o que veio e o que era esperado). Sem `--llm`, não gasta tokens: nas Etapas 7
a 10 as respostas do modelo são trocadas por respostas fixas, então ele confere só o **seu** código. No fim, `python conferir.py`
mostra o resumo de todas as etapas e os marcos.

---

## Etapa 0: preparação (10 min)

**Faça**

1. Confira a instalação e os dados (se você usou o `configurar_ambiente`, isto já foi feito):

   ```powershell
   python verificar_ambiente.py --sem-llm
   python dados_rh.py
   ```

2. Leia `dados/normas.md` e preencha, no `ENTREGA.md`, a tabela "quem verifica cada regra" (função Python, agente ou humano).

**Saída esperada do `dados_rh.py`** ✅

```
9 servidores; 3 afastamentos; 13 feriados locais; 10 regras
[{'codigo': 'N1', 'tema': 'férias', 'regra': 'O servidor tem o saldo de férias do cadastro ... '}, {'codigo': 'N2', ...}, {'codigo': 'N3', ...}]
```

**Dica para a tabela:** uma regra que é **conta** (saldo, datas, limite da escala) é função Python; uma que exige **interpretar**
um texto é agente; uma que é **decisão de alguém** (N8, a chefia) é humano.

**Conferir:** `python conferir.py 0`

---

## Etapa 1: primeiro agente com tool (`etapa01_agente.py`, 15 min)

| Lacuna | O que fazer | Onde olhar |
|---|---|---|
| 1.1 | Tool `consultar_servidor`: `print` no começo, **docstring com `Args:`** e `return json.dumps(servidor_publico(matricula), ensure_ascii=False)` (a consulta `servidor_publico` já vem pronta, sem o salário) | `exercicios_resolvidos/aula4/ex10_function_tool.py` (tool que consulta uma tabela) |
| 1.2 | `criar_atendente()`: `Agent(name="AtendenteRH", instructions=..., tools=[consultar_servidor])` | `aula1/segundo_agente.py` |
| 1.3 | `main()`: as duas perguntas com `Runner.run_sync` | `aula8/exemplos/02_agente_tool/main.py` (o agente decide quando chamar) |

```powershell
python etapa01_agente.py
```

**Saída esperada** 🔸

```
[modelo] openai:gpt-4o-mini
[tool] consultar_servidor 1002
A matrícula 1002 (Bruno Castro) tem 30 dias de férias disponíveis.
Abono pecuniário é a conversão de parte das férias em dinheiro: o servidor "vende" alguns dias em vez de descansá-los.
```

**Confira:** a linha `[tool] consultar_servidor` aparece **uma vez** (só na primeira pergunta). Se aparecer duas vezes, melhore as
instruções; se não aparecer, melhore a docstring da tool. O salário **não** pode aparecer na resposta.

**Conferir:** `python conferir.py 1`

---

## Etapa 2: extração estruturada (`etapa02_extracao.py`, 15 min)

| Lacuna | O que fazer | Onde olhar |
|---|---|---|
| 2.1 | Completar os campos do `Pedido` com `Field(description=...)` | `aula2/agente_output2.py` (Enum, listas e descrições: **o mais parecido**) |
| 2.2 | `criar_extrator()` com `output_type=Pedido`; completar `INSTRUCOES_EXTRATOR` | `aula2/agente_output.py` |
| 2.3 | `extrair()`: `Runner.run_sync(...).final_output` | `aula2/agente_output.py` |

```powershell
python etapa02_extracao.py
```

**Saída esperada** 🔸 (os valores dos campos abaixo são os **corretos**; a `justificativa` varia)

```
C1_abono_simples
  {'tipo': <TipoPedido.ABONO: 'abono'>, 'matricula': '1001', 'data_inicio': '2027-04-09', 'data_fim': '2027-04-09', 'dias_vendidos': 0, 'destino': None, 'tipo_destino': None, 'justificativa': '...'}

C2_ferias_com_venda
  {'tipo': <TipoPedido.FERIAS: 'ferias'>, 'matricula': '1002', 'data_inicio': '2027-04-12', 'data_fim': '2027-04-26', 'dias_vendidos': 10, ...}

C5_sem_matricula
  {'tipo': <TipoPedido.FERIAS: 'ferias'>, 'matricula': None, 'data_inicio': None, 'data_fim': None, 'dias_vendidos': 0, ...}

C11_diaria_exterior
  {'tipo': <TipoPedido.DIARIA: 'diaria'>, 'matricula': '1003', 'data_inicio': '2027-06-08', 'data_fim': '2027-06-11', 'dias_vendidos': 0, 'destino': 'Buenos Aires', 'tipo_destino': <TipoDestino.EXTERIOR: 'exterior'>, ...}
```

**Confira:** o C5 **não** pode ter datas inventadas ("agosto de 2027" não é uma data exata). Se o modelo inventar, reforce na
`description` dos campos de data: "null se o servidor não disse o dia exato".

**Conferir:** `python conferir.py 2`

---

## Etapa 3: guardrails de entrada (`etapa03_guardrails.py`, 20 min)

| Lacuna | O que fazer | Onde olhar |
|---|---|---|
| (pronto) | `RE_CPF`, `RE_CID` e `encontrar_dado_sensivel()` já vêm prontos: leia e use nos guardrails | `exercicios_resolvidos/aula4/ex11_guardrails.py` (`_RE_RG`) |
| 3.2 | `criar_classificador()` com `output_type=AvaliacaoEscopo` e exemplos de nota baixa/alta | `aula2/agente_guardrail.py` (`guardrail_agent`: **o mais parecido**) |
| 3.3 | `nota_escopo()` | `aula2/agente_guardrail.py` |
| 3.4 | Os dois `@input_guardrail` (o motivo vai em `output_info`) | `aula2/agente_guardrail.py` (`bloquear_off_topics`) |
| 3.5 | `main()`: tratar `InputGuardrailTripwireTriggered` e imprimir a mensagem do motivo | `aula2/agente_guardrail.py`, `aula8/exemplos/04_prompt_injection/1_codigo_pronto/main.py` |

**A regex pronta, para você ver o que ela pega** (sem LLM) ✅

```powershell
python -c "from etapa03_guardrails import encontrar_dado_sensivel as f; print(f('Estou com CID F32.1'), f('CPF 123.456.789-09'), f('férias de 12/04/2027 a 26/04/2027'))"
```

```
cid cpf None
```

> Repare: a data `12/04/2027` **não** pode casar com a regex de CPF nem a de CID. Se casar, a regex está larga demais.

Nos 12 casos, a regex só deve encontrar algo no C3 ✅:

```
C3_dado_de_saude         cpf        (o C3 tem CPF e CID; o CPF é achado primeiro)
todos os outros          None
```

```powershell
python etapa03_guardrails.py
```

**Saída esperada** 🔸 (as notas variam; o que importa é **quem passa** e **por qual motivo bloqueia**)

```
C1_abono_simples     nota=0.05  PASSOU (tipo=abono)
C2_ferias_com_venda  nota=0.05  PASSOU (tipo=ferias)
C3_dado_de_saude     BLOQUEADO (cid/cpf): Por segurança, não envie CPF por este canal. ...
C4_fora_do_escopo    nota=0.95  BLOQUEADO (fora_do_escopo): Este canal atende apenas pedidos de férias, abono e diária.
C7_autoaprovacao     nota=0.90  BLOQUEADO (fora_do_escopo): Este canal atende apenas pedidos de férias, abono e diária.
C10_zona_cinzenta    nota=0.50  PASSOU (tipo=outro)      <- anote esta nota: ela é usada no opcional 🆕 C
```

**Confira:** se o C7 passar, inclua nas instruções do classificador exemplos de "tentar mudar as regras" ("ignore as regras",
"eu mesmo aprovo"). A nota do C10 deve ficar **no meio** (entre ~0,3 e ~0,7): se ficar perto de 0 ou de 1, ajuste os exemplos.

**Conferir:** `python conferir.py 3`

---

## Etapa 4: APIs externas com resiliência (`etapa04_ferramentas.py`, 10 min, **pronto**)

O `etapa04_ferramentas.py` **já vem implementado**. Não há lacuna: **leia, rode e explique**. Tudo aqui é Python puro, então dá para testar
**sem chave de API**. Para cada função, abra o exemplo de origem e compare:

| Função | O que faz | Exemplo de origem nas aulas |
|---|---|---|
| `texto_hoje()` | a data real (já injetada nas instruções do extrator, em `etapa02_extracao.py`) | `aula3/agente_retry.py` |
| `get_json_com_retry()` | `User-Agent`, `timeout`, 3 tentativas, espera `0.5 * 2**(n-1)` | `aula3/agente_retry2.py` |
| `buscar_feriados()` | BrasilAPI com plano B (arquivo local) e cache | `aula6/exemplos/11_grafo_real/main.py` (**a mesma API**) |
| `dias_uteis()`, `data_retorno()`, `inicio_permitido()` | as contas de datas; N3: o dia de início e os 2 seguintes são úteis | (lógica de datas) |
| `cotacao_usd_brl()` | câmbio com o mesmo retry; falhou → `None` ("a calcular") | `aula3/agente_retry4.py` (**a mesma API**) |
| `gerar_protocolo()` | `strip().lower()`, `None` → `""`, junta com `"|"`, `sha256(...).hexdigest()[:8]` | `aula3/agente_retry3.py` |
| `rodar_com_limites()` | `asyncio.wait_for` (tempo) + `max_turns` (loop), um erro para cada | `aula3/agente_parada3.py` |

Rode nos dois modos e responda no `ENTREGA.md`: por que a espera **dobra** a cada tentativa? Por que o protocolo é um **hash** dos
campos e não um número sequencial? O que aconteceria se `buscar_feriados` não tivesse **cache**?

```powershell
$env:FERIADOS_OFFLINE = "1"
python etapa04_ferramentas.py
```

**Saída esperada, OFFLINE** ✅ (só a linha `hoje:` muda)

```
[retry] tentativa 1 falhou: <urlopen error offline>
[retry] tentativa 2 falhou: <urlopen error offline>
[retry] tentativa 3 falhou: <urlopen error offline>
feriados 2027: 13 (fonte: arquivo_local, 1.5s)
hoje: segunda-feira, 12/10/2026 (2026-10-12)
inicio_permitido(2027-04-12) = True  (esperado True)
inicio_permitido(2027-04-30) = False  (esperado False)
inicio_permitido(2027-04-15) = False  (esperado False)
inicio_permitido(2027-05-03) = True  (esperado True)
dias úteis 12/04 a 26/04/2027: 10 | retorno: 2027-04-27
[retry] tentativa 1 falhou: <urlopen error offline>
[retry] tentativa 2 falhou: <urlopen error offline>
[retry] tentativa 3 falhou: <urlopen error offline>
cotação USD->BRL: None
protocolo C1=ae788d33 C8=ae788d33 iguais=True
```

**Saída esperada, ONLINE** (`Remove-Item Env:FERIADOS_OFFLINE`): sem as linhas `[retry]`, `fonte: brasilapi` e uma cotação de
verdade (ex.: `cotação USD->BRL: 5.43`). Os demais valores são **iguais** aos do offline: a BrasilAPI e o arquivo local têm os
mesmos feriados nacionais.

**Para entender a saída:**
- `1.5s` no offline = as esperas do backoff (0,5 s + 1 s) antes de desistir e usar o arquivo local.
- `dias úteis ... 10`: são 11 dias de segunda a sexta, menos o feriado de Tiradentes (21/04).
- `protocolo C1=ae788d33`: o mesmo pedido gera sempre o mesmo protocolo. Ele vai aparecer em todas as saídas a partir daqui; se
  os seus protocolos não baterem com os deste roteiro, o problema está nos campos que a **extração** devolveu (matrícula, tipo,
  datas), não neste arquivo.

**Conferir:** `python conferir.py 4`

---

## Etapa 5: MCP Server do RH (`etapa05_mcp_rh.py` e `etapa05_cliente_mcp.py`, 35 min)

| Lacuna | O que fazer | Onde olhar |
|---|---|---|
| 5.1 | As 5 tools de leitura: `@mcp.tool()`, **docstring** e `return` da consulta pronta de `dados_rh.py` (`servidor_publico`, `escala_da_equipe`, `normas`, `diaria`, `remuneracao`). **Toda tool devolve um dict** | `aula6/desafio2/mcp_unidades.py` (**MCP lendo CSV**), `aula5/exemplos/05_multiplas_tools/server.py` |
| 5.2 | `registrar_decisao()` idempotente (só a parte de gravar; a segurança é a 9.2) | `aula3/agente_retry3.py` |
| (pronto) | `chamar_mcp_async()` já vem pronto (é o mesmo cliente do `aula6/desafio2/main.py`): leia para entender como o código chama uma tool sem LLM | `aula6/desafio2/main.py` (`chamar_mcp`) |
| 5.3 | `perguntar_ao_atendente()` com `MCPServerStdio` | `aula5/exemplos/04_agente_mcp/agente.py` |

**1) Teste o server sozinho no MCP Inspector** (precisa de Node.js):

```powershell
npx @modelcontextprotocol/inspector python etapa05_mcp_rh.py
```

No navegador: **Connect** → **Tools** → **List Tools**. Devem aparecer **6** tools: `consultar_servidor`, `consultar_escala`,
`consultar_normas`, `tabela_diarias`, `consultar_remuneracao` e `registrar_decisao`. Chame `consultar_servidor` com `1002`.

**2) Teste o cliente sem agente** (o `chamar_mcp` já vem pronto; quem precisa estar certo são as suas tools):

```powershell
python etapa05_cliente_mcp.py
```

**Saída esperada, DEPOIS das Etapas 5.1, 5.2, 9.2 e 9.3** ✅ (com `saidas/` vazia)

```
{'matricula': '1002', 'nome': 'Bruno Castro', 'cargo': 'Escrivão', 'equipe': 'Plantão A', 'saldo_ferias_dias': 30, 'abonos_restantes': 3, 'chefia': '1010'}
{'equipe': 'Cartório', 'tamanho_equipe': 4, 'limite_afastados': 1, 'afastamentos': [{'matricula': '1006', 'equipe': 'Cartório', 'inicio': '2027-07-05', 'fim': '2027-07-19', 'tipo': 'ferias'}]}
{'tema': 'abono', 'regras': [{'codigo': 'N6', 'tema': 'abono', 'regra': 'Abono (folga) é de **1 dia útil** por pedido, limitado a `abonos_restantes`. Não pode cair em fim de semana nem em feriado.'}]}
1ª gravação: {'sucesso': True, 'protocolo': 'teste001'}
2ª gravação: {'sucesso': True, 'duplicado': True, 'protocolo': 'teste001'}  <- deve dizer duplicado
{"sem_token": {"sucesso": false, "erro": "token inválido"}}  <- depois da Etapa 9.2, deve ser negado
```

**Antes da Etapa 9.2**, a última linha mostra `{"sucesso": true, "duplicado": true, ...}`: ainda não há conferência de token, e o
protocolo `teste001` já existe. Isso é esperado agora; volte a esta saída depois da Etapa 9.

**Confira:** o `consultar_servidor` **não** tem `salario_base`; o limite do Cartório é **1** (4 servidores × 30% = 1,2 → 1).

**3) Teste o agente com o server:**

```powershell
python etapa05_cliente_mcp.py --agente
```

**Saída esperada** 🔸

```
[modelo] openai:gpt-4o-mini
Sim. Na equipe Cartório, a matrícula 1006 está de férias de 05/07/2027 a 19/07/2027, o que se sobrepõe ao período de 12 a 26/07/2027.
```

**Conferir:** `python conferir.py 5`

---

## Etapa 6: especialistas e fluxo linear (30 min) ⇒ Marco mínimo

### 6.0: regras objetivas (`etapa06_regras.py`, **pronto**): leia e rode

O `etapa06_regras.py` já vem implementado: `violacoes_objetivas()` (N1, N2, N3, N4, N5, N6) e `precisa_chefia()` (N8). Compare cada `if`
com a sua tabela da Etapa 0 (faltou ou sobrou alguma regra?). A ideia de colocar a regra de negócio em Python, no meio de um fluxo
com IA, é a mesma do `avaliar_risco` em `aula6/exemplos/11_grafo_real/main.py`.

```powershell
python etapa06_regras.py
```

**Saída esperada** ✅ (com `$env:FERIADOS_OFFLINE = "1"` aparecem também linhas `[retry]` antes; sem ele, não)

```
C1: nenhuma violação  chefia=False  OK
C2: nenhuma violação  chefia=True  OK
C6: ['N5: a equipe já tem 1 afastado(s) no período: 1006 (2027-07-05 a 2027-07-19)']  chefia=False  OK
C12: ['N3: as férias não podem começar em 2027-04-30 (véspera de feriado/fim de semana)']  chefia=False  OK
```

Repare na N5: o próprio servidor é descartado da lista de afastamentos (senão um pedido conflitaria com ele mesmo).

### 6.1 a 6.4: agentes e fluxo linear

| Lacuna | O que fazer | Onde olhar |
|---|---|---|
| 6.1 | `criar_normas/escala/financeiro/redator()`, cada um **só** com as suas tools | `aula7/exemplos/02_agentes_especializados/main.py`, `aula7/agentes.py` (`ModelSettings(temperature=0)`) |
| 6.2 | `criar_coordenador()` com os 3 especialistas `as_tool(..., hooks=hooks, failure_error_function=None)` | `aula4/ex03_agente_as_tool.py` (**o mais parecido**), `aula2/agente_handoff2.py` |
| 6.3 | `analisar()`: roda o Coordenador com `rodar_com_limites_sync` | `aula4/ex03_agente_as_tool.py` |
| 6.4 | `processar()`: os 9 passos, imprimindo cada um | `aula6/exemplos/01_fluxo_linear/main.py` |

```powershell
python etapa06_linear.py
```

**Saída esperada** 🔸 (os textos variam; o **resultado** e o **protocolo** não)

```
=============== C1_abono_simples
[1/9] guardrails
[2/9] extração: abono 1001 2027-04-09..2027-04-09
[3/9] servidor: Ana Ribeiro (Plantão A)
[4/9] período: 1 dia útil, retorno 2027-04-12 (fonte: brasilapi)
[5/9] violações: nenhuma
[6/9] coordenador: consultou parecer_normas, parecer_escala
[7/9] redator
[8/9] protocolo ae788d33
[9/9] registrar: {'sucesso': True, 'protocolo': 'ae788d33'}
{
  "resultado": "registrado",
  "protocolo": "ae788d33",
  "despacho": "Defiro o abono de 1 (um) dia útil em 09/04/2027 à servidora de matrícula 1001 ...",
  "parecer": "..."
}

=============== C2_ferias_com_venda       ... "protocolo": "b7b6f485"  (despacho de DEFERIMENTO, venda de 10 dias = R$ 3.166,67)
=============== C6_conflito_de_escala     ... "protocolo": "6f1b47d7"  (despacho de INDEFERIMENTO por N5, sugerindo outro período)
=============== C11_diaria_exterior       ... "protocolo": "ec67dba1"  (3,5 diárias x USD 320 = USD 1.120, convertido em reais)
```

**Confira os valores que dá para calcular à mão:**
- C2: 10 dias vendidos × R$ 9.500 / 30 = **R$ 3.166,67**.
- C11: 3 diárias com pernoite + meia diária no retorno = **3,5 × USD 320 = USD 1.120** (× a cotação do dia). Offline: "a calcular".
- C6: a sugestão de datas precisa começar **depois de 19/07/2027** (fim das férias da 1006) e num dia permitido pela N3.

> **Depois da Etapa 9.2**, o C2 e o C11 deste fluxo linear passam a ser **negados** pelo server (`aprovador` = `pendente_chefia`,
> que não é a chefia). É o comportamento certo: a aprovação de verdade só existe no grafo (Etapa 8).

**Conferir:** `python conferir.py 6`

---

## Etapa 7: o grafo (`etapa07_grafo.py`, 55 min)

Faça na ordem abaixo: assim o grafo roda cedo e você testa caso a caso.

| Lacuna | O que fazer | Onde olhar |
|---|---|---|
| 7.1 | `violacoes: Annotated[list[str], operator.add]` | `aula7/exemplos/08_paralelismo/main.py` e o item 4 do `exercicio.md` da mesma pasta (o conflito de escrita) |
| 7.5 (arestas) | `construir()`: as arestas do diagrama do `ENUNCIADO.md` (sem a chefia e sem a triagem ainda) | `aula6/exemplos/06_fluxo_condicional/main.py`, `aula6/exemplos/07_dag/main.py` |
| 7.2 | `proteger_entrada` (limiar único), `no_extrair`, `identificar_servidor`, `calcular_periodo` e os roteadores | `aula6/exemplos/11_grafo_real/main.py` (nós de LLM, MCP e API), `aula6/desafio2/main.py` (**o mais parecido**) |
| 7.3 | `no_normas`, `no_escala`, `no_financeiro` e `consolidar` | `aula7/exemplos/08_paralelismo/main.py` (fan-out/fan-in por lista), `aula7/exemplos/05_equipe_multiagente/main.py` |
| 7.4 | `redigir_despacho`, `validar` (usa a `problemas_do_despacho()`, já pronta, e conta as tentativas) e `rotear_validacao` | `aula6/exemplos/08_fluxo_ciclico/main.py` (ciclo com parada) |
| 7.5 (registrar) | `registrar()` chamando `registrar_decisao` no MCP | `aula6/desafio2/main.py` (`chamar_mcp` num nó) |

> Até a Etapa 8, em `rotear_validacao` mande `"chefia"` também para `"registrar"`, e no `construir()` ainda não ligue
> `aprovacao_chefia`. Deixe `USAR_VOTACAO` e `USAR_TRIAGEM_HUMANA` em `False` (são os opcionais 🆕 A e 🆕 C).

```powershell
python etapa07_grafo.py --mermaid
python etapa07_grafo.py C1_abono_simples
python etapa07_grafo.py C6_conflito_de_escala
```

**Saída esperada** ✅ (os caminhos não dependem do LLM, desde que a extração esteja certa)

```
[C1_abono_simples] caminho: receber -> proteger_entrada -> extrair -> identificar_servidor -> calcular_periodo -> escala -> financeiro -> normas -> consolidar -> redigir_despacho -> validar -> registrar
[C1_abono_simples] resultado: registrado  protocolo: ae788d33
[C1_abono_simples] despacho: (texto do Redator, citando a matrícula 1001, 2027-04-09 e "deferido")

[C6_conflito_de_escala] caminho: receber -> proteger_entrada -> extrair -> identificar_servidor -> calcular_periodo -> escala -> financeiro -> normas -> consolidar -> redigir_despacho -> validar -> registrar
[C6_conflito_de_escala] resultado: registrado  protocolo: 6f1b47d7
[C6_conflito_de_escala] despacho: (texto do Redator, citando a matrícula 1004, 2027-07-12 e "indeferido")
```

**Confira:**
- `escala -> financeiro -> normas` são os três ramos **paralelos**: a ordem entre eles pode variar. O que não pode variar é que
  os três aparecem **antes** de `consolidar`, e `consolidar` aparece **uma vez**.
- Se o caminho tiver `redigir_despacho -> validar` repetido, o validador reprovou o despacho; até 3 tentativas é normal.
  Olhe `erro_validacao` para saber por quê.
- Rodou o C1 de novo e o resultado virou `duplicado`? Está certo: o protocolo `ae788d33` já foi gravado. Apague `saidas/` para
  ver `registrado` outra vez.

**Conferir:** `python conferir.py 7`

---

## Etapa 8: persistência e aprovação da chefia (`etapa07_grafo.py`, 30 min)

| Lacuna | O que fazer | Onde olhar |
|---|---|---|
| 8.1 | Nada a escrever: o `main()` já compila com `SqliteSaver`. Leia e entenda. | `aula7/exemplos/04_persistencia/main.py` |
| 8.2 | `aprovacao_chefia()` com `interrupt()` | `aula7/exemplos/06_human_in_the_loop/main.py`, `aula7/exemplos/07_aprovacao_revisao/main.py` (**o mais parecido**) |
| 8.3 | `rotear_chefia()` e as arestas de `validar` → `aprovacao_chefia` → `redigir_despacho`/`registrar` | `aula7/exemplos/07_aprovacao_revisao/main.py` |
| 8.4 | `retomar()` com `Command(resume=...)` (o `listar_pendentes()` já vem pronto: leia, ele usa `get_state`) | `aula7/exemplos/06_human_in_the_loop/main.py` (`retomar`), `aula7/exemplos/04_persistencia/main.py` (`get_state`) |

**1) O C2 pausa e o processo termina** ✅

```powershell
python etapa07_grafo.py C2_ferias_com_venda
```

```
[C2_ferias_com_venda] caminho: receber -> proteger_entrada -> extrair -> identificar_servidor -> calcular_periodo -> escala -> financeiro -> normas -> consolidar -> redigir_despacho -> validar
[C2_ferias_com_venda] PAUSADO em ('aprovacao_chefia',): Aprova o despacho?
   retome com: python etapa07_grafo.py --retomar C2_ferias_com_venda sim|"nao:motivo" <quem>
```

**2) Quem está pausado** ✅ (depois de rodar `python etapa07_grafo.py --todos`; a ordem das linhas pode variar)

```powershell
python etapa07_grafo.py --pendentes
```

```
C12_inicio_proibido: concluído
C11_diaria_exterior: PAUSADO em ('aprovacao_chefia',)
C10_zona_cinzenta: concluído                                <- com o opcional 🆕 C: PAUSADO em ('triagem_humana',)
C9_divergencia: concluído
C8_idempotencia: concluído
C7_autoaprovacao: concluído
C6_conflito_de_escala: concluído
C5_sem_matricula: concluído
C4_fora_do_escopo: concluído
C3_dado_de_saude: concluído
C2_ferias_com_venda: PAUSADO em ('aprovacao_chefia',)
C1_abono_simples: concluído
```

**3) A chefia rejeita uma vez e depois aprova (em OUTRO processo)** ✅

```powershell
python etapa07_grafo.py C2_ferias_com_venda
python etapa07_grafo.py --retomar C2_ferias_com_venda "nao:confirme o valor da venda" 1010
python etapa07_grafo.py --retomar C2_ferias_com_venda sim 1010
```

```
[C2_ferias_com_venda] caminho: receber -> ... -> validar -> aprovacao_chefia -> redigir_despacho -> validar
[C2_ferias_com_venda] PAUSADO em ('aprovacao_chefia',): Aprova o despacho?

[C2_ferias_com_venda] caminho: receber -> ... -> validar -> aprovacao_chefia -> redigir_despacho -> validar -> aprovacao_chefia -> registrar
[C2_ferias_com_venda] resultado: registrado  protocolo: b7b6f485
```

**4) A diária no exterior, aprovada pela chefia certa (1011)** ✅

```powershell
python etapa07_grafo.py --retomar C11_diaria_exterior sim 1011
```

```
[C11_diaria_exterior] caminho: receber -> ... -> validar -> aprovacao_chefia -> registrar
[C11_diaria_exterior] resultado: registrado  protocolo: ec67dba1
```

**5) Retomar o que já terminou** ✅

```powershell
python etapa07_grafo.py --retomar C11_diaria_exterior sim 1011
```

```
[C11_diaria_exterior] nada pausado
```

**Confira:**
- Na 3ª, o despacho da segunda versão deve levar em conta o motivo da chefia ("confirme o valor da venda").
- Ponha um `print("ANTES do interrupt")` no começo de `aprovacao_chefia` e retome: ele aparece **de novo**. É por isso que nada
  com efeito colateral pode vir antes do `interrupt()`.
- Duas rejeições seguidas → o registro sai com `decisao` = `indeferido_pela_chefia`.

**Conferir:** `python conferir.py 8`

---

## Etapa 9: segurança (`etapa05_mcp_rh.py` e `etapa07_grafo.py`, 25 min) ⇒ Marco completo

| Lacuna | O que fazer | Onde olhar |
|---|---|---|
| 9.1 | Nada a escrever: confira que nenhum agente tem `registrar_decisao` e só o Financeiro tem `consultar_remuneracao` | `aula8/exemplos/06_excessive_agency/1_codigo_pronto/main.py` |
| 9.2 | Em `registrar_decisao`: token, enum de decisão, autoaprovação e chefia certa (N8) | `aula5/exemplos/10_seguranca/server_seguro.py` (**o mais parecido**) |
| 9.3 | `_auditar()`: uma linha JSON por tentativa, ALLOW ou DENY | `aula5/exemplos/10_seguranca/server_seguro.py` (`_registrar_auditoria`) |
| 9.4 | No `registrar` do grafo: não grava despacho com CPF/CID | `aula8/exemplos/05_guardrail_saida/1_codigo_pronto/main.py` |

**1) Autoaprovação e chefia errada** ✅

```powershell
python etapa07_grafo.py C2_ferias_com_venda
python etapa07_grafo.py --retomar C2_ferias_com_venda sim 1002
python etapa07_grafo.py C2_ferias_com_venda
python etapa07_grafo.py --retomar C2_ferias_com_venda sim 1011
```

```
[C2_ferias_com_venda] caminho: receber -> ... -> validar -> aprovacao_chefia -> registrar
[C2_ferias_com_venda] resultado: negado_pelo_server: autoaprovação (N8)  protocolo: b7b6f485

[C2_ferias_com_venda] caminho: receber -> ... -> validar -> aprovacao_chefia -> registrar
[C2_ferias_com_venda] resultado: negado_pelo_server: aprovador não é a chefia 1010 (N8)  protocolo: b7b6f485
```

**2) O C7 sem o guardrail de entrada** ✅ (o "eu aprovo" não aprova nada: as regras indeferem)

```powershell
python etapa07_grafo.py --sem-guardrail C7_autoaprovacao
```

```
[modelo] openai:gpt-4o-mini  [guardrail de entrada DESLIGADO]
[C7_autoaprovacao] caminho: receber -> proteger_entrada -> extrair -> identificar_servidor -> calcular_periodo -> escala -> financeiro -> normas -> consolidar -> redigir_despacho -> validar -> registrar
[C7_autoaprovacao] resultado: registrado  protocolo: (depende da data de "amanhã")
[C7_autoaprovacao] despacho: (INDEFERIMENTO: N4, antecedência menor que 30 dias)
```

**3) A auditoria** ✅ (`saidas/auditoria.jsonl`, uma linha por tentativa). Partindo de `saidas/` vazia, rodando `--todos` e depois
as retomadas desta página, estas linhas aparecem nesta ordem (resumo das colunas protocolo, quem, acesso, motivo e decisão; o C7
sem guardrail e um C10 que siga adiante acrescentam linhas suas):

```
ae788d33 sistema ALLOW gravado deferido                         C1
6f1b47d7 sistema ALLOW gravado indeferido                       C6
ae788d33 sistema ALLOW duplicado deferido                       C8
7c458e62 sistema ALLOW gravado indeferido                       C12
b7b6f485 1002 DENY autoaprovação (N8) deferido                  C2, o próprio servidor
b7b6f485 1011 DENY aprovador não é a chefia 1010 (N8) deferido  C2, chefia errada
b7b6f485 1010 ALLOW gravado deferido                            C2, chefia certa
ec67dba1 1011 ALLOW gravado deferido                            C11
```

Uma linha completa, para comparar o formato:

```json
{"quando": "2026-10-12T13:49:11.003562", "thread_id": "", "quem": "sistema", "tool": "registrar_decisao", "protocolo": "teste001", "decisao_acesso": "DENY", "motivo": "token inválido", "parametros": {"matricula": "1001", "tipo": "abono", "inicio": "2027-04-09", "fim": "2027-04-09", "decisao": "deferido", "aprovador": "sistema", "thread_id": ""}}
```

**Confira:** o `token` e o `despacho` **não** aparecem na auditoria. Volte também à saída do `python etapa05_cliente_mcp.py` (Etapa 5): a
última linha agora deve dizer `token inválido`.

**Conferir:** `python conferir.py 9`

---

## Etapa 10: observabilidade (`etapa10_governanca.py` e `etapa10_observabilidade.py`, 15 min)

| Lacuna | O que fazer | Onde olhar |
|---|---|---|
| 10.1 | Em `etapa10_governanca.py`, `on_tool_end` e `on_agent_end` acrescentam a `self.eventos` (tool, argumentos, resultado, tokens); passe `hooks=Governanca()` nos `rodar_com_limites_sync` dos nós | `aula3/agente_hook2.py`, `aula5/exemplos/11_observabilidade/agente_observavel.py` |
| 10.2 | `medido()`: tempo por nó numa linha de `saidas/metricas.jsonl` | `aula8/exemplos/03_observabilidade/1_codigo_pronto/passo1_trace.py` (a ideia de span por etapa) |
| (pronto) | `resumo(thread_id)` já vem pronto: ele lê o JSONL que o seu `medido()` grava | |

```powershell
python etapa07_grafo.py C2_ferias_com_venda
python etapa10_observabilidade.py C2_ferias_com_venda
```

**Saída esperada** 🔸 (os números variam; a **forma** não)

`saidas/metricas.jsonl` (uma linha por nó):

```json
{"thread_id": "C2_ferias_com_venda", "no": "receber", "segundos": 0.0}
{"thread_id": "C2_ferias_com_venda", "no": "proteger_entrada", "segundos": 1.12, "tokens": 412}
{"thread_id": "C2_ferias_com_venda", "no": "extrair", "segundos": 2.31, "tokens": 2650}
{"thread_id": "C2_ferias_com_venda", "no": "calcular_periodo", "segundos": 1.84, "fonte_feriados": "brasilapi"}
...
```

Resumo:

```json
{
  "nos": ["receber", "proteger_entrada", "extrair", "identificar_servidor", "calcular_periodo", "escala", "financeiro", "normas", "consolidar", "redigir_despacho", "validar"],
  "segundos_total": 14.7,
  "mais_lento": ["financeiro", 4.2],
  "tokens_total": 9830
}
```

**Confira:** se você fez o opcional 🆕 A, o nó `extrair` gasta cerca de **3 vezes** os tokens de um extrator só. Os nós
sem LLM que chamam o MCP (`identificar_servidor`, `calcular_periodo`) levam cerca de 1 s cada, porque cada `chamar_mcp` sobe o
server de novo: bom assunto para a pergunta "o que mudaria em produção?".

**Conferir:** `python conferir.py 10`

---

## Etapa 11: demonstração e entrega (20 min)

1. Apague `saidas/` e rode tudo:

   ```powershell
   python etapa07_grafo.py --todos
   python etapa07_grafo.py --retomar C2_ferias_com_venda sim 1010
   python etapa07_grafo.py --retomar C11_diaria_exterior sim 1011
   ```

2. Preencha a tabela do `ENTREGA.md` e compare com a referência abaixo.

**Referência dos 12 casos** ✅ (partindo de `saidas/` vazia; os protocolos só batem se a extração e a normalização do protocolo
estiverem certas)

| Caso | Caminho (resumido) | Resultado | Protocolo |
|---|---|---|---|
| C1 | ... `consolidar -> redigir_despacho -> validar -> registrar` | registrado (deferido, sem chefia) | `ae788d33` |
| C2 | ... `validar` → **pausa** em `aprovacao_chefia` → (sim 1010) `registrar` | registrado (deferido pela 1010) | `b7b6f485` |
| C3 | `receber -> proteger_entrada -> recusar` | recusado (CPF/CID) | |
| C4 | `receber -> proteger_entrada -> recusar` | recusado (fora do escopo) | |
| C5 | `receber -> proteger_entrada -> extrair -> pedir_dados` | pediu dados | |
| C6 | ... `consolidar -> redigir_despacho -> validar -> registrar` | registrado (**indeferido**, N5) | `6f1b47d7` |
| C7 | `receber -> proteger_entrada -> recusar` | recusado (fora do escopo / manipulação) | |
| C8 | igual ao C1 | **duplicado** | `ae788d33` |
| C9 | `receber -> proteger_entrada -> extrair -> pedir_dados` 🔸 | pediu dados (pedido vago, sem datas exatas) | |
| C10 | `receber -> proteger_entrada -> extrair -> pedir_dados` 🔸 | pediu dados (ou recusado, se a nota passar do `LIMIAR`) | |
| C11 | ... `validar` → **pausa** em `aprovacao_chefia` → (sim 1011) `registrar` | registrado (deferido pela 1011) | `ec67dba1` |
| C12 | ... `consolidar -> redigir_despacho -> validar -> registrar` | registrado (**indeferido**, N3) | `7c458e62` |

🔸 C9 e C10 dependem do LLM: se o extrator "inventar" datas, eles seguem adiante (e isso é um erro de extração a corrigir nas
instruções). Registre no `ENTREGA.md` o que aconteceu. Com os opcionais, o C9 sai por `divergencia` (🆕 A) e o C10 pausa em
`triagem_humana` (🆕 C).

**O diagrama** (`python etapa07_grafo.py --mermaid`) ✅: o seu deve ter estes nós e estas arestas (a ordem das linhas pode variar):

```
	__start__ --> receber;
	aprovacao_chefia -. &nbsp;redigir&nbsp; .-> redigir_despacho;
	aprovacao_chefia -.-> registrar;
	calcular_periodo --> escala;
	calcular_periodo --> financeiro;
	calcular_periodo --> normas;
	consolidar --> redigir_despacho;
	escala --> consolidar;
	extrair -. &nbsp;ok&nbsp; .-> identificar_servidor;
	extrair -. &nbsp;incompleto&nbsp; .-> pedir_dados;
	financeiro --> consolidar;
	identificar_servidor -. &nbsp;ok&nbsp; .-> calcular_periodo;
	identificar_servidor -. &nbsp;nao_encontrado&nbsp; .-> pedir_dados;
	normas --> consolidar;
	proteger_entrada -. &nbsp;ok&nbsp; .-> extrair;
	proteger_entrada -. &nbsp;bloqueado&nbsp; .-> recusar;
	receber --> proteger_entrada;
	redigir_despacho --> validar;
	validar -. &nbsp;chefia&nbsp; .-> aprovacao_chefia;
	validar -. &nbsp;redigir&nbsp; .-> redigir_despacho;
	validar -.-> registrar;
	pedir_dados --> __end__;
	recusar --> __end__;
	registrar --> __end__;
```

Com o opcional 🆕 C ligado, aparecem também `proteger_entrada -. duvida .-> triagem_humana`, `triagem_humana -. segue .-> extrair`
e `triagem_humana -. recusa .-> recusar`. Cole a saída completa em <https://mermaid.live> para ver o desenho. Repare: `escala`, `financeiro` e `normas` entram em
`consolidar` com setas **cheias** (fan-in por lista); as **pontilhadas** são as decisões (arestas condicionais).

**Conferir:** `python conferir.py 11`

---

## Itens opcionais 🆕 (bônus: só depois do Marco completo)

Os três itens abaixo usam um conceito já visto em aula num contexto novo. **Nenhum é necessário** para o sistema funcionar:
faça-os só se terminou a Etapa 9 (ou a 11) e sobrou tempo. Cada um vale até +5 pontos de bônus.

**Conferir:** `python conferir.py --opcionais` (ou só um: `python conferir.py 🆕A`, `🆕B`, `🆕C`).

### 🆕 A: votação em paralelo (`etapa02_extracao.py`, +5 pontos)

| Lacuna | O que fazer | Onde olhar |
|---|---|---|
| A.1 | 3 instruções diferentes em `INSTRUCOES_VOTANTES` | (contexto novo, sem exemplo) |
| A.2 | `extrair_com_votacao()`: `await asyncio.gather(*(Runner.run(e, texto) for e in extratores))` | `aula7/exemplos/08_paralelismo/main.py` (o conceito: fan-out/fan-in); `aula3/agente_parada3.py` (`Runner.run` com `asyncio`) |
| (pronto) | `votar()` (maioria por campo, divergência sem maioria) já vem pronto: leia | |
| (pronto) | a medição do tempo em sequência já vem pronta no `_demo_votacao` | |

```powershell
python etapa02_extracao.py --votacao
```

**Saída esperada** 🔸

```
C1_abono_simples  (1.9s, divergencia=False)
  voto 1: tipo=abono 2027-04-09..2027-04-09 vende=0
  voto 2: tipo=abono 2027-04-09..2027-04-09 vende=0
  voto 3: tipo=abono 2027-04-09..2027-04-09 vende=0
  decisão: {'tipo': <TipoPedido.ABONO: 'abono'>, 'matricula': '1001', ...}

C2_ferias_com_venda  (2.3s, divergencia=False)
  voto 1: tipo=ferias 2027-04-12..2027-04-26 vende=10
  ... (os 3 iguais)

C9_divergencia  (2.4s, divergencia=True)
  voto 1: tipo=ferias 2027-03-22..2027-03-31 vende=0
  voto 2: tipo=ferias 2027-03-25..2027-04-03 vende=5
  voto 3: tipo=ferias None..None vende=0
  decisão: {...}
paralelo: 2.3s | sequencial: 6.8s
```

Para usar no grafo: `USAR_VOTACAO = True` em `etapa07_grafo.py` (e, no `no_extrair`, chame `extrair_com_votacao`).

**Confira:** C1 e C2 **unânimes**; o C9 é um pedido vago de propósito ("uns dez dias perto da Páscoa"): o normal é os votos
discordarem nas datas e sair `divergencia=True`. O tempo em paralelo deve ficar perto do de **uma** chamada, e o sequencial,
perto de **três**.

### 🆕 B: hooks que barram (`etapa10_governanca.py`, +5 pontos)

| Lacuna | O que fazer | Onde olhar |
|---|---|---|
| B.1 | `PERMISSOES` para Normas, Escala, Financeiro e Coordenador (os `tool_name` das `as_tool`) | `aula8/exemplos/06_excessive_agency/1_codigo_pronto/main.py` (o risco) |
| B.2 | `on_tool_start`: conta; fora da lista ou acima de `max_tools` → `raise LimiteExcedido(...)` | `aula3/agente_hook2.py`, `aula3/agente_loop.py` (assinaturas dos métodos) |
| B.3 | `on_llm_start`: idem para `max_llm` | `aula3/agente_hook3.py` |
| B.4 | `testar_governanca()` em `etapa06_linear.py` | (contexto novo, sem exemplo) |

```powershell
python etapa06_linear.py --governanca
```

**Saída esperada** 🔸 (as mensagens são suas; o que importa está em negrito abaixo)

```
a) Coordenador com uma tool que não é dele
[governança] Coordenador -> consultar_remuneracao: BARRADO (fora da lista do Coordenador)
   barrado: Coordenador não pode usar consultar_remuneracao

b) C2 com MAX_TOOLS = 1
[governança] Coordenador -> parecer_normas: OK (1 de 1)
[governança] Normas -> consultar_normas: BARRADO (orçamento de tools estourado: 2 de 1)
   barrado: orçamento de tools estourado (2 de 1)
```

**Confira:**
- A linha `[tool] consultar_remuneracao(1002) EXECUTOU` **não pode aparecer** no teste (a). Se aparecer, o hook não está
  barrando **antes** da tool.
- No (b), o bloqueio acontece **dentro** do primeiro especialista: o mesmo hook enxerga as tools de todos (por causa do
  `hooks=hooks` nas `as_tool`). Isso é mais cedo do que "antes do segundo especialista", e está certo.
- Se o bloqueio "sumir" e o Coordenador responder normalmente, faltou `failure_error_function=None` nas `as_tool`; se aparecer
  um `UserError: Error running tool ...` em vez do seu `except`, a exceção não herda de `AgentsException` (já vem certo no
  esqueleto: não mude).

### 🆕 C: o humano decide a entrada (`etapa07_grafo.py`, +5 pontos)

Ligue `USAR_TRIAGEM_HUMANA = True` em `etapa07_grafo.py`: o nó `triagem_humana` só entra no grafo com ele ligado.

| Lacuna | O que fazer | Onde olhar |
|---|---|---|
| C.1 | `proteger_entrada` e `rotear_entrada` com duas faixas (`ok` / `duvida` / `bloqueado`) | (contexto novo) |
| C.2 | `triagem_humana` com `interrupt()`, `rotear_triagem` e as arestas | `aula7/exemplos/06_human_in_the_loop/main.py` (o mecanismo), `aula7/desafio2/` (duas pessoas no mesmo fluxo) |

```powershell
python etapa07_grafo.py C10_zona_cinzenta
```

**Saída esperada** ✅

```
[C10_zona_cinzenta] caminho: receber -> proteger_entrada
[C10_zona_cinzenta] PAUSADO em ('triagem_humana',): Este texto deve seguir como pedido ao RH?
   retome com: python etapa07_grafo.py --retomar C10_zona_cinzenta sim|"nao:motivo" <quem>
```

**O atendente recusa, com orientação** ✅

```powershell
python etapa07_grafo.py --retomar C10_zona_cinzenta "nao:procure a junta médica ou peça licença para acompanhar familiar" rh
```

```
[C10_zona_cinzenta] caminho: receber -> proteger_entrada -> triagem_humana -> recusar
[C10_zona_cinzenta] resultado: recusado  protocolo: None
[C10_zona_cinzenta] despacho: procure a junta médica ou peça licença para acompanhar familiar
```

**O atendente deixa seguir** (rode o C10 de novo antes, porque o anterior terminou):

```powershell
python etapa07_grafo.py C10_zona_cinzenta
python etapa07_grafo.py --retomar C10_zona_cinzenta "sim:tratar como abono" rh
```

```
[C10_zona_cinzenta] caminho: receber -> proteger_entrada -> triagem_humana -> extrair -> ...
```

🔸 O que vem depois de `extrair` depende do LLM: o pedido não tem data exata ("semana que vem"), então o mais comum é
`-> pedir_dados`. Se o modelo calcular uma data a partir de hoje, o caminho segue até `registrar`.

**Confira:** C1 não pausa nenhuma vez; C2 pausa só na chefia; C10 pausa na triagem (e, se seguir até virar férias, pode pausar
**de novo** na chefia: duas pessoas diferentes no mesmo fluxo). Se o C10 não pausar, recalibre `LIMIAR_OK`/`LIMIAR_BLOQUEIO`
com a nota que você anotou na Etapa 3.

---

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `NotImplementedError: ETAPA n.m` | Falta implementar aquela lacuna (às vezes de **outro** arquivo: o `etapa03_guardrails.py` para na 2.2 se o extrator ainda não existe) | Implemente a etapa citada na mensagem |
| `NotImplementedError: 🆕 ...` | Você ligou um item opcional (`USAR_VOTACAO`, `USAR_TRIAGEM_HUMANA` ou `--governanca`) sem implementá-lo | Volte a chave para `False` ou faça o item |
| `SystemExit: PROVEDOR=openai exige OPENAI_API_KEY` | `.env` sem chave, ou você não está dentro de `aula10/` | Preencha o `.env` e rode de dentro de `aula10/` |
| `HTTP Error 403` na BrasilAPI | Requisição sem `User-Agent` | Envie o cabeçalho (veja `aula6/exemplos/11_grafo_real/main.py`) |
| `RuntimeError: MCP consultar_xxx: [TextContent(... text='Error executing tool consultar_xxx' ...)]` | Erro **dentro** da tool do server; o detalhe não chega ao cliente | Chame a tool no MCP Inspector, que mostra o traceback |
| `asyncio.run() cannot be called from a running event loop` | `chamar_mcp` (síncrono) dentro de código `async`, como uma tool de agente | Dentro de `async def`, use `await chamar_mcp_async(...)` |
| `InvalidUpdateError: At key 'violacoes': Can receive only one value per step` | Dois ramos paralelos escreveram no mesmo campo sem reducer | Etapa 7.1: `Annotated[list[str], operator.add]` |
| `GraphRecursionError: Recursion limit of 40 reached` | O ciclo `redigir_despacho -> validar` (ou o da chefia) não para | Confira se `tentativas`/`rejeicoes` aumentam e se o roteador lê o limite |
| Caminho com nós repetidos desde o começo (`receber -> receber -> ...`) | Execução anterior no mesmo `thread_id` | O `executar()` pronto já apaga o thread; se você mexeu nele, devolva as duas linhas do `delete_thread` |
| `negado_pelo_server: token inválido` em tudo | `TOKEN_REGISTRO` vazio ou diferente no `.env` | O server lê o `.env` sozinho: confira o valor e salve o arquivo |
| Resultado `duplicado` onde você esperava `registrado` | O protocolo já estava em `saidas/registros.json` | Apague `saidas/` para recomeçar (veja "Antes de começar") |
| O hook do 🆕 B não barra nada | `PERMISSOES` vazio, nomes errados (use o `tool_name` das `as_tool`) ou `hooks=` não repassado | Imprima `agent.name` e `tool.name` dentro do `on_tool_start` |
