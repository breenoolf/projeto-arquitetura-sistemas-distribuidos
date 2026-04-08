# Sprint 2 — Comunicação de Tarefas + ACK (TCP)

Este projeto implementa o fluxo completo de ciclo de vida de uma tarefa entre **Worker (cliente)** e **Master (servidor)** usando **TCP + JSON**.

- Mensagens são JSON com **delimitador `\n`** (uma mensagem por linha)
- Worker faz handshake/pedido: `{"WORKER":"ALIVE","WORKER_UUID":"..."}`
	- Campo opcional: `SERVER_UUID` (apenas se o Worker for "emprestado" / tiver Master de origem diferente)
- Master responde:
	- Com tarefa: `{"TASK":"QUERY","USER":"..."}`
	- Sem tarefa: `{"TASK":"NO_TASK"}`
- Worker processa e reporta: `{"STATUS":"OK"|"NOK","TASK":"QUERY","WORKER_UUID":"..."}`
- Master confirma: `{"STATUS":"ACK","WORKER_UUID":"..."}`

## Como executar (Sprint 2)

> Abra **2 terminais** na pasta do projeto.

### 1) Iniciar o Master (servidor)

```bash
python master.py
```

Por padrão o Master inicia com 2 tarefas (users `Michel` e `Julia`) e escreve logs em `master_log.txt`.

### 2) Iniciar o Worker (cliente)

```bash
python worker.py
```

O Worker vai repetir o ciclo: **ALIVE → (QUERY|NO_TASK) → STATUS → ACK**.

## Cenário: Worker “emprestado” (SERVER_UUID opcional)

Para simular um Worker emprestado, basta definir `WORKER_ORIGIN_SERVER_UUID` (o UUID do Master original):

PowerShell (Windows):

```powershell
$env:WORKER_UUID='W-999'
$env:WORKER_ORIGIN_SERVER_UUID='Master_B'
python worker.py
```

O Master deve reconhecer o campo `SERVER_UUID` no payload de apresentação e registrar no log a origem (LOCAL vs emprestado).

## Variáveis de ambiente (Sprint 2)

- `MASTER_SERVER_UUID` (padrão: `Master_A`)
- `MASTER_TASK_USERS` (padrão: `Michel,Julia`) — cria a fila inicial de tarefas
- `MASTER_LOG_PATH` (padrão: `master_log.txt`)

- `WORKER_UUID` (padrão: UUID aleatório)
- `WORKER_ORIGIN_SERVER_UUID` (opcional) — envia `SERVER_UUID` no ALIVE
- `MASTER_RESPONSE_TIMEOUT_S` (padrão: `5`) — timeout de espera por resposta/ACK
- `RECONNECT_DELAY_S` (padrão: `3`) — espera entre reconexões
- `IDLE_WAIT_S` (padrão: `2`) — espera entre ciclos quando `NO_TASK`
- `PROCESSING_MIN_S` / `PROCESSING_MAX_S` (padrão: `0.5` / `2.0`) — simulação de processamento
- `WORKER_FAIL_RATE` (padrão: `0.0`) — chance de reportar `NOK` (0.0 a 1.0)

---

# Sprint 1 — Heartbeat (TCP)

Este projeto implementa um mecanismo simples de **Heartbeat** entre um **Worker (cliente)** e um **Master (servidor)** usando **TCP + JSON**.

- Mensagens são JSON com **delimitador `\n`** (uma mensagem por linha)
- Worker envia `{"SERVER_UUID": "Master_A", "TASK": "HEARTBEAT"}`
- Master responde `{"SERVER_UUID": "Master_A", "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"}`
- Worker mantém loop periódico e tenta reconectar quando o Master cai

## Requisitos

- Python 3.11+ (sem dependências externas)

## Como executar

> Abra **2 terminais** na pasta do projeto.

### 1) Iniciar o Master (servidor)

```bash
python master.py
```

Você deve ver um log indicando que o servidor está rodando e aguardando conexões.

### 2) Iniciar o Worker (cliente)

```bash
python worker.py
```

Você deve ver o Worker enviando heartbeats e imprimindo `Status: ALIVE`.

## Teste de reconexão

1. Com o Worker rodando, interrompa o Master (`Ctrl + C`).
2. O Worker deve imprimir `Status: OFFLINE - Tentando reconectar` e continuar tentando.
3. Inicie o Master novamente (`python master.py`).
4. O Worker deve voltar a imprimir `Status: ALIVE`.

## Configurações (opcional)

O Worker permite ajustar tempos via variáveis de ambiente:

- `HEARTBEAT_INTERVAL_S` (padrão: `30`) — intervalo entre heartbeats
- `HEARTBEAT_TIMEOUT_S` (padrão: `5`) — tempo máximo esperando resposta
- `RECONNECT_DELAY_S` (padrão: `3`) — espera entre tentativas de reconexão
- `TARGET_SERVER_UUID` (padrão: `Master_A`) — valor enviado em `SERVER_UUID`

Exemplo no PowerShell (Windows):

```powershell
$env:HEARTBEAT_INTERVAL_S='2'
$env:HEARTBEAT_TIMEOUT_S='2'
$env:RECONNECT_DELAY_S='1'
python worker.py
```

## Arquivos principais

- `master.py` — servidor TCP que responde ao HEARTBEAT
- `worker.py` — cliente TCP que envia heartbeat em loop e reconecta
- `utils.py` — helpers de envio/recebimento (JSON + `\n`)
