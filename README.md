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
