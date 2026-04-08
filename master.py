import asyncio
import os
from collections import deque
from datetime import datetime, timezone

from utils import ProtocolError, exigir_campos, enviar_mensagem, receber_mensagem

# Identificador do Master (útil para logs/testes).
MASTER_UUID = os.getenv("MASTER_SERVER_UUID", "Master_A")

# Sprint 2: fila de tarefas.
# Formato: lista de usuários, gerando tarefas {"TASK":"QUERY","USER":"..."}.
_users_raw = os.getenv("MASTER_TASK_USERS", "Michel,Julia")
TASK_QUEUE: deque[dict] = deque(
    {"TASK": "QUERY", "USER": u.strip()} for u in _users_raw.split(",") if u.strip()
)

# Persistência simples de logs.
LOG_PATH = os.getenv("MASTER_LOG_PATH", "master_log.txt")


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log_linha(linha: str) -> None:
    print(linha)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fp:
            fp.write(linha + "\n")
    except Exception:
        # Não derruba o servidor por falha de I/O no log.
        pass

async def tratar_conexao(reader, writer):
    endereco = writer.get_extra_info('peername')
    print(f"[Master] Nova conexão de {endereco}")

    worker_origem: dict[str, str | None] = {}
    worker_em_execucao: dict[str, dict] = {}
    
    try:
        while True:
            # Escuta contínua por mensagens na conexão
            mensagem = await receber_mensagem(reader)
            if not mensagem:
                break
                
            print(f"[Master] Recebido: {mensagem}")

            # Compatibilidade Sprint 1 (Heartbeat)
            if mensagem.get("TASK") == "HEARTBEAT":
                resposta = {
                    "SERVER_UUID": MASTER_UUID,
                    "TASK": "HEARTBEAT",
                    "RESPONSE": "ALIVE",
                }
                await enviar_mensagem(writer, resposta)
                print(f"[Master] Resposta enviada: {resposta}")
                continue

            # Sprint 2: apresentação e pedido de tarefa (Worker -> Master)
            if mensagem.get("WORKER") == "ALIVE":
                exigir_campos(mensagem, ["WORKER", "WORKER_UUID"])
                if mensagem["WORKER"] != "ALIVE":
                    raise ProtocolError("Campo WORKER deve ser 'ALIVE'")
                worker_uuid = str(mensagem["WORKER_UUID"])
                server_uuid_origem = mensagem.get("SERVER_UUID")
                worker_origem[worker_uuid] = str(server_uuid_origem) if server_uuid_origem is not None else None

                if TASK_QUEUE:
                    tarefa = TASK_QUEUE.popleft()
                    worker_em_execucao[worker_uuid] = tarefa
                    await enviar_mensagem(writer, tarefa)
                    _log_linha(f"[{_agora_iso()}] [Master {MASTER_UUID}] TASK-> Worker={worker_uuid} Origem={worker_origem[worker_uuid] or 'LOCAL'} Tarefa={tarefa}")
                else:
                    await enviar_mensagem(writer, {"TASK": "NO_TASK"})
                continue

            # Sprint 2: reporte de status (Worker -> Master)
            if "STATUS" in mensagem:
                exigir_campos(mensagem, ["STATUS", "TASK", "WORKER_UUID"])
                status = mensagem["STATUS"]
                task = mensagem["TASK"]
                worker_uuid = str(mensagem["WORKER_UUID"])

                if status not in ("OK", "NOK"):
                    raise ProtocolError("STATUS deve ser 'OK' ou 'NOK'")
                if task != "QUERY":
                    raise ProtocolError("TASK no reporte de status deve ser 'QUERY'")

                tarefa_enviada = worker_em_execucao.pop(worker_uuid, None)
                if tarefa_enviada is None:
                    raise ProtocolError("Status recebido sem tarefa em execução registrada")

                origem = worker_origem.get(worker_uuid)
                _log_linha(
                    f"[{_agora_iso()}] [Master {MASTER_UUID}] STATUS<- Worker={worker_uuid} Origem={origem or 'LOCAL'} Status={status} Tarefa={tarefa_enviada}"
                )

                await enviar_mensagem(writer, {"STATUS": "ACK", "WORKER_UUID": worker_uuid})
                continue

            # Se cair aqui, é um payload desconhecido: strict parsing.
            raise ProtocolError("Payload desconhecido")
                
    except ProtocolError as e:
        print(f"[Master] Erro de protocolo com {endereco}: {e}")
    except Exception as e:
        print(f"[Master] Erro na conexão com {endereco}: {e}")
    finally:
        print(f"[Master] Fechando conexão com {endereco}")
        writer.close()
        await writer.wait_closed()

async def iniciar_master(host='127.0.0.1', porta=8888):
    servidor = await asyncio.start_server(tratar_conexao, host, porta)
    endereco = servidor.sockets[0].getsockname()
    print(f"[Master] Servidor rodando em {endereco} com UUID: {MASTER_UUID}")
    print(f"[Master] Sprint2: fila inicial com {len(TASK_QUEUE)} tarefa(s). Log: {LOG_PATH}")
    
    async with servidor:
        await servidor.serve_forever()

if __name__ == "__main__":
    asyncio.run(iniciar_master())