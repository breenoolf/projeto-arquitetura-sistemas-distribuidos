# Configuração com .env

## Configuração Rápida

1. **Copie o arquivo de exemplo:**
```bash
cp .env.example .env
```

2. **Customize valores conforme necessário (opcionalmente):**
```bash
# Editar .env com seu editor favorito
```

3. **Execute Worker/Master normalmente:**
```bash
python worker.py    # Carrega .env automaticamente
python master.py    # Carrega .env automaticamente
```

---

## Variáveis Disponíveis

### Worker (Colaborador)

| Var | Padrão | Descrição |
|-----|--------|-----------|
| `WORKER_UUID` | `str(uuid4())` | ID único do Worker |
| `WORKER_ORIGIN_SERVER_UUID` | vazio | Master de origem (emprestado) |
| `WORKER_FAIL_RATE` | 0.0 | Taxa de falha simulada (0.0-1.0) |
| `MASTER_RESPONSE_TIMEOUT_S` | 5 | Timeout aguardando Master |
| `RECONNECT_DELAY_S` | 3 | Delay entre retentativas |
| `IDLE_WAIT_S` | 2 | Tempo entre heartbeats |
| `PROCESSING_MIN_S` | 0.5 | Min tempo processamento task |
| `PROCESSING_MAX_S` | 2.0 | Max tempo processamento task |
| `DISCOVERY_TIMEOUT_S` | 3.0 | Tempo coleta respostas UDP |
| `DISCOVERY_PORT` | 5000 | Porta UDP discovery |
| `DISCOVERY_BROADCAST_ADDR` | 255.255.255.255 | Endereço broadcast |

### Master (Servidor Principal)

| Var | Padrão | Descrição |
|-----|--------|-----------|
| `MASTER_SERVER_UUID` | Master_A | UUID do Master |
| `MASTER_NAME` | MASTER_A | Nome único (usado em eleição) |
| `MASTER_IP` | 127.0.0.1 | IP para bind TCP |
| `MASTER_TCP_PORT` | 8888 | Porta TCP |
| `DISCOVERY_BROADCAST_ADDR_MASTER` | 0.0.0.0 | Endereço escuta UDP |
| `MASTER_TASK_USERS` | Michel,Julia | Usuários para tarefas |
| `MASTER_LOG_PATH` | master_log.txt | Arquivo log |

---

## Exemplos

### Múltiplos Masters (Teste Local)

Terminal 1:
```bash
cat > .env << EOF
MASTER_NAME=MASTER_1
MASTER_IP=127.0.0.1
MASTER_TCP_PORT=8888
EOF
python master.py
```

Terminal 2:
```bash
cat > .env << EOF
MASTER_NAME=MASTER_2
MASTER_IP=127.0.0.1
MASTER_TCP_PORT=8889
EOF
python master.py
```

Terminal 3:
```bash
python worker.py
# Worker eleito MASTER_1 (ordem lexicográfica)
```

### Worker Personalizado

```bash
cat > .env << EOF
WORKER_UUID=W-CUSTOM-001
WORKER_FAIL_RATE=0.2
PROCESSING_MIN_S=1.0
PROCESSING_MAX_S=3.0
DISCOVERY_TIMEOUT_S=5.0
EOF
python worker.py
```

---

## ⚠️ Importante

- **`.env` não é versionado** (.gitignore) — use `.env.example` para documentação
- **Variáveis de ambiente CLI substituem `.env`:**
  ```bash
  MASTER_NAME=MASTER_X python master.py  # Sobrescreve .env
  ```
- Sem `.env`: código usa padrões incorporados (compatível com versões anteriores)
