# 📚 Projeto de Arquitetura Distribuída - Sistema Master-Worker P2P

Sistema de processamento distribuído em Python implementando protocolo P2P entre Masters com suporte a negociação dinâmica de Workers. Desenvolvido em 3 sprints progressivas.

---

## 📑 Índice de Sprints

1. **[Sprint 1: Batida de Coração (TCP)](#sprint-1--batida-de-coração-tcp)** - Comunicação básica Master-Worker
2. **[Sprint 2: Comunicação de Tarefas + ACK](#sprint-2--comunicação-de-tarefas--ack-tcp)** - Ciclo de vida completo de tarefas
3. **[Sprint 3: Protocolo Master-to-Master P2P](#sprint-3--protocolo-master-to-master-p2p)** - Negociação e redistribuição dinâmica

---

# Sprint 1 — Batida de Coração (TCP)

Este projeto implementa um mecanismo simples de **Batida de Coração (Heartbeat)** entre um **Worker (cliente)** e um **Master (servidor)** usando **TCP + JSON**.

- Mensagens são JSON com **delimitador `\n`** (uma mensagem por linha)
- Worker envia `{"SERVER_UUID": "Master_A", "TASK": "HEARTBEAT"}`
- Master responde `{"SERVER_UUID": "Master_A", "TASK": "HEARTBEAT", "RESPONSE": "ALIVE"}`
- Worker mantém loop periódico e tenta reconectar quando o Master cai

## Requisitos

- Python 3.11+ (sem dependências externas)

## Como Executar

> Abra **2 terminais** na pasta do projeto.

### 1) Iniciar o Master (Servidor)

```bash
python master.py
```

Você deve ver um registro indicando que o servidor está rodando e aguardando conexões.

### 2) Iniciar o Worker (Cliente)

```bash
python worker.py
```

Você deve ver o Worker enviando batidas de coração e imprimindo `Status: ALIVE`.

## Teste de Reconexão

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

---

# Sprint 2 — Comunicação de Tarefas + ACK (TCP)

Implementa o fluxo completo de ciclo de vida de uma tarefa entre **Worker (cliente)** e **Master (servidor)** usando **TCP + JSON**.

## Protocolo Sprint 2

- Mensagens são JSON com **delimitador `\n`** (uma mensagem por linha)
- Worker faz verificação/pedido: `{"WORKER":"ALIVE","WORKER_UUID":"..."}`
	- Campo opcional: `SERVER_UUID` (apenas se o Worker for "emprestado" / tiver Master de origem diferente)
- Master responde:
	- Com tarefa: `{"TASK":"QUERY","USER":"..."}`
	- Sem tarefa: `{"TASK":"NO_TASK"}`
- Worker processa e reporta: `{"STATUS":"OK"|"NOK","TASK":"QUERY","WORKER_UUID":"..."}`
- Master confirma: `{"STATUS":"ACK","WORKER_UUID":"..."}`

## Como Executar (Sprint 2)

> Abra **2 terminais** na pasta do projeto.

### 1) Iniciar o Master (Servidor)

```bash
python master.py
```

Por padrão o Master inicia com 2 tarefas (usuários `Michel` e `Julia`) e escreve registros em `master_log.txt`.

### 2) Iniciar o Worker (Cliente)

```bash
python worker.py
```

O Worker vai repetir o ciclo: **ALIVE → (QUERY|NO_TASK) → STATUS → ACK**.

## Cenário: Worker "Emprestado" (SERVER_UUID Opcional)

Para simular um Worker emprestado, basta definir `WORKER_ORIGIN_SERVER_UUID` (o UUID do Master original):

PowerShell (Windows):

```powershell
$env:WORKER_UUID='W-999'
$env:WORKER_ORIGIN_SERVER_UUID='Master_B'
python worker.py
```

O Master deve reconhecer o campo `SERVER_UUID` no carga da apresentação e registrar no registro a origem (LOCAL vs emprestado).

## Variáveis de Ambiente (Sprint 2)

- `MASTER_SERVER_UUID` (padrão: `Master_A`)
- `MASTER_TASK_USERS` (padrão: `Michel,Julia`) — cria a fila inicial de tarefas
- `MASTER_LOG_PATH` (padrão: `master_log.txt`)

- `WORKER_UUID` (padrão: UUID aleatório)
- `WORKER_ORIGIN_SERVER_UUID` (opcional) — envia `SERVER_UUID` no ALIVE
- `MASTER_RESPONSE_TIMEOUT_S` (padrão: `5`) — tempo limite de espera por resposta/ACK
- `RECONNECT_DELAY_S` (padrão: `3`) — espera entre reconexões
- `IDLE_WAIT_S` (padrão: `2`) — espera entre ciclos quando `NO_TASK`
- `PROCESSING_MIN_S` / `PROCESSING_MAX_S` (padrão: `0.5` / `2.0`) — simulação de processamento
- `WORKER_FAIL_RATE` (padrão: `0.0`) — chance de reportar `NOK` (0.0 a 1.0)

## Arquivos principais

- `master.py` — servidor TCP que gerencia tarefas e Workers
- `worker.py` — cliente TCP que processa tarefas em loop
- `utils.py` — helpers de envio/recebimento (JSON + `\n`)

---

# Sprint 3 — Protocolo Master-to-Master P2P

Implementa comunicação **P2P entre Masters** para negociação dinâmica de Workers emprestados. Um Master saturado pode solicitar Workers de um Master vizinho, e devolvê-los quando a carga normaliza.

## 🎯 Objetivos Sprint 3

✅ **T01**: Infraestrutura TCP entre Masters (conexões cliente-servidor)  
✅ **T02**: Detecção de saturação com histerese  
✅ **T03**: Protocolo de negociação (request_help / response_accepted / response_rejected)  
✅ **T04**: Redirecionamento dinâmico de Workers (command_redirect)  
✅ **T05**: Devolução de Workers (command_release + notify_worker_returned)  
✅ **T06**: Concorrência e resiliência (locks, timeouts, AsyncIO)  
✅ **T07**: Logs e observabilidade (rastreamento completo)

## Protocolo Sprint 3

### Mensagens entre Masters

#### 1. request_help (T03)
```json
{
  "type": "request_help",
  "request_id": "uuid-v4",
  "payload": {
    "master_id": "MASTER_A",
    "current_load": 150,
    "capacity": 100,
    "workers_needed": 2
  }
}
```

#### 2. response_accepted (T03)
```json
{
  "type": "response_accepted",
  "request_id": "uuid-v4",
  "payload": {
    "workers_offered": 2,
    "worker_details": [
      {"id": "B1", "address": "127.0.0.1:9001"},
      {"id": "B2", "address": "127.0.0.1:9002"}
    ]
  }
}
```

#### 3. response_rejected (T03)
```json
{
  "type": "response_rejected",
  "request_id": "uuid-v4",
  "payload": {
    "reason": "Capacidade insuficiente"
  }
}
```

### Mensagens Master → Worker

#### 4. command_redirect (T04)
```json
{
  "type": "command_redirect",
  "request_id": "uuid-v4",
  "payload": {
    "new_master_address": "127.0.0.1:8888"
  }
}
```

#### 5. command_release (T05)
```json
{
  "type": "command_release",
  "request_id": "uuid-v4",
  "payload": {
    "original_master_address": "127.0.0.1:8889"
  }
}
```

### Mensagens Master → Master

#### 6. notify_worker_returned (T05)
```json
{
  "type": "notify_worker_returned",
  "request_id": "uuid-v4",
  "payload": {
    "worker_id": "B1"
  }
}
```

## Fluxo de Negociação Completo

```
Master A (saturado)         Master B (vizinho)          Worker B1
     |                            |                         |
     |-- request_help ----------->|                          |
     |                            |                          |
     |<-- response_accepted ------|                          |
     |                            |-- command_redirect ----->|
     |                            |                     [desconecta]
     |<---- new TCP connection --------------------------|
     |                    register_temporary_worker       |
     |-- QUERY (tarefa) -------->B1                         |
     |<-- STATUS (resultado) -----B1                        |
     |                            |                          |
     |-- command_release -------->B1                        |
     |                       [reconecta ao B]               |
     |-- notify_worker_returned ->|                         |
     |                            |                          |
```

## Como Executar (Sprint 3)

### 1) Configurar Vizinhos no .env

```env
MASTER_UUID=Master_A
MASTER_IP=127.0.0.1
MASTER_TCP_PORT=8888
MASTER_UDP_PORT=5000

# Configuração P2P Sprint 3
MASTER_NEIGHBORS=MASTER_B:127.0.0.1:8889
MASTER_P2P_PORT=9999
MASTER_SATURATION_THRESHOLD=100
MASTER_RELEASE_THRESHOLD=60
LOAD_CHECK_INTERVAL_S=2
```

### 2) Iniciar os Masters (em terminais diferentes)

**Terminal 1 - Master A:**
```bash
python master.py
```

**Terminal 2 - Master B:**
```bash
$env:MASTER_UUID='Master_B'
$env:MASTER_TCP_PORT='8889'
$env:MASTER_P2P_PORT='9990'
$env:MASTER_NEIGHBORS='MASTER_A:127.0.0.1:9999'
python master.py
```

### 3) Iniciar Workers

```bash
# Worker 1 (conectado a Master B)
$env:WORKER_UUID='W-001'
python worker.py

# Worker 2 (conectado a Master B)
$env:WORKER_UUID='W-002'
python worker.py
```

### 4) Enviar Tarefas para Saturar Master B

```bash
python master_avancado.py
```

O sistema deve:
1. Master B atingir saturação (load > 100)
2. Master B solicitar ajuda ao Master A
3. Master A redirecionar alguns Workers para Master B
4. Workers processarem tarefas em Master A
5. Quando carga normaliza, Workers retornam ao Master B

## Variáveis de Ambiente (Sprint 3)

**Master:**
- `MASTER_UUID` (padrão: `Master_A`)
- `MASTER_IP` (padrão: `127.0.0.1`)
- `MASTER_TCP_PORT` (padrão: `8888`)
- `MASTER_UDP_PORT` (padrão: `5000`)
- `MASTER_P2P_PORT` (padrão: `9999`)
- `MASTER_NEIGHBORS` — formato: `MASTER_B:host:port,MASTER_C:host:port`
- `MASTER_SATURATION_THRESHOLD` (padrão: `100`)
- `MASTER_RELEASE_THRESHOLD` (padrão: `60`)
- `LOAD_CHECK_INTERVAL_S` (padrão: `2`)

**Worker:**
- `WORKER_UUID` (padrão: UUID aleatório)
- `WORKER_ORIGIN_SERVER_UUID` (opcional) — Master original do Worker
- `MASTER_RESPONSE_TIMEOUT_S` (padrão: `5`)
- `RECONNECT_DELAY_S` (padrão: `3`)
- `IDLE_WAIT_S` (padrão: `2`)

## Arquivos Sprint 3

- `master.py` — Master com P2P e monitor de saturação
- `master_p2p.py` — **NOVO** - Gerenciador P2P e negociação
- `worker.py` — Worker com handlers de redirecionamento/devolução
- `test_sprint3.py` — Suite completa de testes (9 casos)
- `.env` — Configuração Sprint 3

## Testes Sprint 3

Execute a suite completa de testes:

```bash
python test_sprint3.py
```

Resultado esperado:
```
✅ TODOS OS TESTES PASSARAM COM SUCESSO!
- Test MasterP2PManager: 5/5 ✓
- Test Message Formats: 4/4 ✓
```

## Documentação Completa

Para documentação técnica detalhada, consulte:

📄 **[SPRINT3_IMPLEMENTATION.md](SPRINT3_IMPLEMENTATION.md)** - Especificação técnica completa

---

## 🔧 Estrutura de Projeto

```
.
├── README.md                           # Este arquivo
├── SPRINT3_IMPLEMENTATION.md           # Documentação técnica Sprint 3
├── master.py                           # Master principal (P2P + Discovery)
├── master_p2p.py                       # Gerenciador P2P (Sprint 3)
├── master_avancado.py                  # Master auxiliar para testes
├── worker.py                           # Worker (redireção + devolução)
├── worker_avancado.py                  # Worker auxiliar para testes
├── utils.py                            # Helpers (enviar/receber JSON)
├── .env                                # Configuração (incluindo Sprint 3)
├── test_sprint3.py                     # Testes unitários Sprint 3
├── master_log.txt                      # Log de execução (gerado)
└── skills/                             # Documentação de boas práticas
    ├── subagent-driven-development/
    ├── test-driven-development/
    └── ...
```

---

## 📊 Definição de Pronto (DoD)

- ✅ Master saturado abre conexão TCP com vizinho e envia `request_help`
- ✅ Master vizinho processa e responde com `response_accepted` ou `response_rejected`
- ✅ Após `response_accepted`, Master envia `command_redirect` aos Workers
- ✅ Workers emprestados executam tarefas no Master novo
- ✅ Workers identificam-se com `SERVER_UUID` na apresentação
- ✅ Quando carga normaliza, Master envia `command_release` e `notify_worker_returned`
- ✅ Worker reconecta ao Master original com sucesso
- ✅ Interoperabilidade com implementação de outro Master (mesmo protocolo)
- ✅ Parsing tolera campos desconhecidos
- ✅ Sem vazamento de threads, conexões ou mensagens

---

## 📝 Notas de Desenvolvimento

- **Concorrência**: Sistema usa AsyncIO para operações não-bloqueantes
- **Thread Safety**: 4 locks distintos protegem fila de tarefas, carga atual, Workers emprestados e Workers conectados
- **Timeout**: Padrão de 5 segundos para operações P2P
- **Logging**: Todos os eventos registrados em `master_log.txt` com timestamp ISO
- **Compatibilidade**: Cada sprint é retrocompatível com as anteriores

---

## 🧪 Como Testar Sprint 3

### Teste Rápido: Master + 1 Worker

**Terminal 1:**
```bash
python master.py
```

**Terminal 2:**
```bash
$env:WORKER_UUID='W-001'
python worker.py
```

Você deve ver:
- Worker faz Discovery UDP
- Worker eleita MASTER_A via Election
- Worker conecta via TCP Handshake
- Worker recebe 2 tarefas e executa
- Worker aguarda mais tarefas em ciclos de heartbeat

### Teste Completo: Master + 3 Workers (Paralelo)

**Terminal 1:**
```bash
python master.py
```

**Terminal 2:**
```bash
python test_integration_level3.py
```

Este teste simula 3 Workers em paralelo:
- Discovery UDP simultâneo
- Election lexicográfica
- Handshake TCP para todos
- Distribuição de 2 tarefas entre 3 Workers
- 5 ciclos de heartbeat por Worker

**Resultado esperado:**
```
============================================================
✅ TESTE PASSOU!
```

### Teste Unitário: Componentes Sprint 3

```bash
python test_sprint3.py
```

Testa em isolamento:
- Manager P2P (vizinhos, empréstimos)
- Formatos de mensagens (request_help, command_redirect, etc.)
- Persistência de estado

**Resultado esperado:**
```
Ran 9 tests ... OK
```

---

## 🚀 Próximos Passos

1. Testes de integração com múltiplos Masters
2. Implementar pool de conexões Master-to-Master
3. Métricas de latência e utilização
4. Dashboard de monitoramento em tempo real
5. Circuit breaker para Masters indisponíveis
