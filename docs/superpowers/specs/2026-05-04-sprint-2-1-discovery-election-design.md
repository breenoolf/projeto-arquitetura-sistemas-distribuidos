# Sprint 2.1: Descoberta Dinâmica e Eleição de Master — Design Spec

**Project:** P2P com Balanceamento de Carga Dinâmico  
**Sprint:** 2.1  
**Professor:** Michel Junio  
**Date:** 2026-05-04  
**Status:** Design Approved ✅

---

## 1. Visão Geral

**Sprint 2.1** introduz mecanismo de **Service Discovery** e **Consenso Determinístico** em sistemas distribuídos. Workers iniciam **sem configuração prévia** de IP/porta dos Masters, executam descoberta em rede via **UDP Broadcast**, elegem deterministicamente um Master usando ordenação lexicográfica, e transitam para comunicação **TCP estável** (Sprint 1).

### Objetivos Pedagógicos

1. Implementar Service Discovery sem pré-configuração
2. Consenso determinístico sem comunicação entre Workers
3. Transição segura de protocolos (UDP → TCP)
4. Resiliência com fallback para próximo Master candidato
5. Logging estruturado para auditoria do fluxo

---

## 2. Requisitos Funcionais

### RF1: Discovery via UDP Broadcast

- **Worker** envia pacote `DISCOVERY` em **UDP Broadcast** (`255.255.255.255:5000`)
- **Masters** escutam na mesma porta e respondem via **UDP Unicast** para IP/porta de origem do Worker
- Worker aguarda **3 segundos** para coletar múltiplas respostas
- Timeout configurável via `DISCOVERY_TIMEOUT_S` (padrão: 3s)

### RF2: Eleição Determinística

- Worker armazena todas as respostas `DISCOVERY_REPLY`
- Extrai campo `MASTER_NAME` de cada resposta
- Ordena lexicograficamente crescente (`MASTER_1 < MASTER_2 < MASTER_10`)
- **Seleciona primeiro da lista** (menor lexicograficamente)
- Eleição é **idêntica em todos os Workers** quando recebem mesmas respostas

### RF3: Transição UDP → TCP + Handshake

- Worker conecta **TCP** ao `MASTER_IP:MASTER_PORT` do Master eleito
- Envia payload `ELECTION_ACK` confirmando seleção
- Aguarda `ACK` confirmando aceitação
- Em sucesso, **inicia imediatamente loop de Batida de Coração (Sprint 1)**

### RF4: Resiliência com Fallback

- Se Master eleito não responde (timeout TCP 5s), Worker marca como "dead"
- Tenta próximo Master da lista de candidatos (2º lexicograficamente, etc.)
- Se **todos os candidatos falharem**, invalida cache e **retorna ao Discovery**
- Implementa **backoff exponencial** entre tentativas (3s, 6s, 12s...)

### RF5: Análise Rigorosa & Registros

- Ignora campos desconhecidos em cargas
- Falha silenciosamente se campos obrigatórios ausentes (com aviso no registro)
- Registros estruturados: `[Worker] DISCOVERY`, `[Worker] ELECTION`, `[Worker] CONNECTING`, `[Worker] FALLBACK`

---

## 3. Requisitos Não-Funcionais

| Requisito | Valor | Justificativa |
|-----------|-------|---------------|
| Discovery Timeout | 3s | Balança entre coleta de respostas e latência |
| TCP Connect Timeout | 5s | Detecta rápido falhas de conectividade |
| Backoff Inicial | 3s | Recuperação sem sobrecarregar |
| Porta UDP Discovery | 5000 | Porta não-privilegiada, configurável |
| Porta TCP | 8888 (Sprint 1) | Compatível com Master existente |
| JSON Encoding | UTF-8 | Consistente com Sprint 1 |

---

## 4. Payloads Oficiais

Todos terminam com `\n` e **case-sensitive em CAIXA ALTA**:

### 4.1 Discovery Request (Worker → UDP Broadcast)

```json
{"TYPE":"DISCOVERY","WORKER_UUID":"string"}\n
```

**Campos:**
- `TYPE`: "DISCOVERY" (obrigatório)
- `WORKER_UUID`: ID único do Worker (obrigatório)

### 4.2 Discovery Reply (Master → UDP Unicast)

```json
{"TYPE":"DISCOVERY_REPLY","MASTER_NAME":"MASTER_X","MASTER_IP":"string","MASTER_PORT":int}\n
```

**Campos:**
- `TYPE`: "DISCOVERY_REPLY" (obrigatório)
- `MASTER_NAME`: Nome único do Master, ex. "MASTER_1", "MASTER_2" (obrigatório)
- `MASTER_IP`: Endereço IP do Master (obrigatório)
- `MASTER_PORT`: Porta TCP do Master (obrigatório, int)

### 4.3 Election Confirmation (Worker → Master TCP)

```json
{"TYPE":"ELECTION_ACK","WORKER_UUID":"string","SELECTED_MASTER":"MASTER_X"}\n
```

**Campos:**
- `TYPE`: "ELECTION_ACK" (obrigatório)
- `WORKER_UUID`: ID do Worker (obrigatório)
- `SELECTED_MASTER`: Nome do Master eleito (obrigatório)

### 4.4 Election ACK (Master → Worker TCP)

```json
{"TYPE":"ELECTION_ACK","STATUS":"ACCEPTED","MASTER_NAME":"MASTER_X"}\n
```

**Campos:**
- `TYPE`: "ELECTION_ACK" (obrigatório)
- `STATUS`: "ACCEPTED" (obrigatório)
- `MASTER_NAME`: Confirmação do Master (obrigatório)

**Após este ACK, Worker inicia imediatamente loop de Batida de Coração (Sprint 1).**

---

## 5. Fluxo de Comunicação

```
WORKER (sem IP/porta)              MASTERS (escutando UDP + TCP)
       │
       ├─ [1] UDP DISCOVERY broadcast (255.255.255.255:5000)
       │   {"TYPE":"DISCOVERY","WORKER_UUID":"W-101"}
       │
       ├─ [2] Aguarda 3s, coleta respostas
       │
       │◄─── MASTER_2 UDP Unicast (espontâneo)
       │       {"TYPE":"DISCOVERY_REPLY","MASTER_NAME":"MASTER_2",...}
       │
       │◄─── MASTER_1 UDP Unicast
       │       {"TYPE":"DISCOVERY_REPLY","MASTER_NAME":"MASTER_1",...}
       │
       │◄─── MASTER_3 UDP Unicast
       │       {"TYPE":"DISCOVERY_REPLY","MASTER_NAME":"MASTER_3",...}
       │
       ├─ [3] Timeout 3s atingido
       │
       ├─ [4] Elegeu: MASTER_1 (lexicografia)
       │
       ├─ [5] TCP Connect → 192.168.1.20:8888 (IP/PORT de MASTER_1)
       │
       ├─ [6] TCP ELECTION_ACK
       │       {"TYPE":"ELECTION_ACK","WORKER_UUID":"W-101","SELECTED_MASTER":"MASTER_1"}
       │
       │◄─── [7] TCP ACK (MASTER_1)
       │       {"TYPE":"ELECTION_ACK","STATUS":"ACCEPTED","MASTER_NAME":"MASTER_1"}
       │
       ├─ [8] Inicia Loop Heartbeat (Sprint 1)
       │
       ├─ ALIVE → QUERY|NO_TASK → STATUS → ACK (repeat)
       │
       └─ [FALLBACK] Se TCP de MASTER_1 falhar:
           ├─ Marca MASTER_1 como "dead"
           ├─ Tenta MASTER_2 (próximo da lista)
           ├─ Se todos falharem: volta a [1] Discovery
```

---

## 6. Casos de Teste (CT)

| ID | Cenário | Ação Worker | Resposta Master | Critério de Sucesso |
|----|---------|------------|-----------------|-------------------|
| CT01 | Único Master | DISCOVERY broadcast | 1× DISCOVERY_REPLY (MASTER_1) | Conecta TCP, inicia Heartbeat |
| CT02 | Múltiplos Masters | DISCOVERY broadcast | 3× respostas (M2, M1, M3) | Elege MASTER_1, ignora M2/M3 |
| CT03 | Timeout sem respostas | DISCOVERY broadcast | (nenhuma) | Logs "NO_MASTER_FOUND", aplica backoff, retry |
| CT04 | Master eleito cai após TCP | TCP Connect → Master_1 | TCP fecha inesperadamente | Invalida cache, tenta M2, etc. |
| CT05 | Payload malformado | DISCOVERY broadcast | JSON incompleto | Worker descarta, continua aguardando |
| CT06 | Workers simultâneos | N× DISCOVERY (W1,W2,W3) | Mesmas respostas | Todos elegem MASTER_1 (consenso) |

---

## 7. Definição de "Pronto" (DoD)

Entrega concluída quando:

- [ ] Worker inicia **sem IP/porta do Master** pré-configurados
- [ ] Realiza discovery via UDP Broadcast e coleta respostas de Masters
- [ ] Elege consistentemente o **mesmo Master** quando múltiplos respondentes
- [ ] Estabelece TCP com Master eleito e envia primeiro Heartbeat com sucesso
- [ ] Trata timeout, ausência de Masters e queda pós-eleição
- [ ] Todos os payloads seguem padrão JSON + `\n` com parsing strict
- [ ] Logs estruturados em cada etapa (DISCOVERY, ELECTION, CONNECTING, FALLBACK)
- [ ] **Sem regressões** no código de Sprint 1 (Heartbeat continua funcionando)

---

## 8. Arquitetura de Implementação

### 8.1 Worker (Modificação inline em `worker.py`)

**Estrutura:**

```python
async def iniciar_worker(...):
    while True:
        try:
            # [NOVO] Fase 1: Discovery
            discovered_masters = await discovery_phase()
            if not discovered_masters:
                # Backoff e retry
                await asyncio.sleep(RECONNECT_DELAY_S)
                continue
            
            # [NOVO] Fase 2: Election
            selected_master = election_phase(discovered_masters)
            
            # [NOVO] Fase 3: TCP Connect + Handshake
            reader, writer = await connect_and_handshake(selected_master)
            
            # [EXISTENTE] Fase 4: Loop Heartbeat (Sprint 1)
            await heartbeat_loop(reader, writer)
            
        except Exception as e:
            # Fallback: próximo Master ou retry Discovery
            await asyncio.sleep(RECONNECT_DELAY_S)
```

### 8.2 Master (Modificação em `master.py`)

**Estrutura:**

```python
async def main():
    # [NOVO] Task 1: UDP Discovery Listener
    asyncio.create_task(discovery_server())
    
    # [EXISTENTE] Task 2: TCP Server (Heartbeat + Tasks)
    await tcp_server()

async def discovery_server():
    # Escuta UDP 255.255.255.255:5000
    # Para cada DISCOVERY recebido:
    #   - Parse WORKER_UUID
    #   - Responde UDP Unicast: DISCOVERY_REPLY
    pass

async def tcp_server():
    # [MODIFICADO] Handshake: espera ELECTION_ACK antes de Heartbeat
    # Responde: ELECTION_ACK com STATUS=ACCEPTED
    # Depois continua com loop Heartbeat (Sprint 1)
    pass
```

### 8.3 Sem mudanças em `utils.py`

Reutiliza `enviar_mensagem()` e `receber_mensagem()` existentes.

---

## 9. Variáveis de Ambiente (Sprint 2.1)

| Var | Padrão | Descrição |
|-----|--------|-----------|
| `DISCOVERY_TIMEOUT_S` | 3.0 | Tempo aguardando respostas UDP |
| `DISCOVERY_PORT` | 5000 | Porta UDP para discovery (recomendado) |
| `DISCOVERY_BROADCAST_ADDR` | 255.255.255.255 | Endereço broadcast |
| `MASTER_NAME` | MASTER_A | Nome único do Master (no master.py) |
| `MASTER_TCP_PORT` | 8888 | Porta TCP (compatível Sprint 1) |
| `WORKER_UUID` | uuid4() | ID único Worker (já existe) |
| `MASTER_RESPONSE_TIMEOUT_S` | 5 | Timeout TCP pós-eleição |
| `RECONNECT_DELAY_S` | 3 | Backoff inicial (já existe) |

---

## 10. Notas de Implementação

### 10.1 UDP Broadcast em Python

Use `socket.socket(socket.AF_INET, socket.SOCK_DGRAM)` com:
```python
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.bind(('', DISCOVERY_PORT))  # Escuta em 0.0.0.0
# Envio: sock.sendto(payload, (BROADCAST_ADDR, DISCOVERY_PORT))
```

### 10.2 Ordenação Lexicográfica

```python
def eleger_master(respostas: list[dict]) -> dict:
    nomes_ordenados = sorted(
        respostas, 
        key=lambda r: r['MASTER_NAME']
    )
    return nomes_ordenados[0]  # Primeira (menor lexicograficamente)
```

### 10.3 Tratamento de Exceções

- `asyncio.TimeoutError` → Discovery timeout ou TCP timeout
- `ConnectionRefusedError` → Master não aceita conexão
- `json.JSONDecodeError` → Payload malformado
- Logs com `[Worker] DISCOVERY:`, `[Worker] ELECTION:`, etc. para rastreabilidade

### 10.4 Compatibilidade Sprint 1

- Após `ELECTION_ACK` aceito, fluxo **continua idêntico** ao heartbeat Sprint 1
- Não quebra Workers/Masters existentes (forward-compatible)

---

## 11. Critérios de Aceitação

1. ✅ Discovery funciona em rede local (broadcast)
2. ✅ Eleição é determinística (múltiplos Workers elegem mesmo Master)
3. ✅ Fallback para próximo candidato funciona
4. ✅ Todos os cenários de teste (CT01-CT06) passam
5. ✅ Logs estruturados permitem auditoria completa
6. ✅ Nenhuma regressão em Sprint 1 (Heartbeat intacto)

---

## 12. Próximas Fases

- **Sprint 2.2**: Balanceamento de carga dinâmico (movimentação de Workers entre Masters)
- **Sprint 3**: Consenso distribuído (Raft/Paxos) para eleição de Master global

---

**Document Version:** 1.0  
**Last Updated:** 2026-05-04  
**Status:** Ready for Implementation ✅
