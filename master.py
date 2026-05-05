import asyncio
import json
import os
import socket
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from utils import ProtocolError, exigir_campos, enviar_mensagem, receber_mensagem

# Load environment variables from .env file
load_dotenv(Path(__file__).parent / ".env")

# Identificador do Master (útil para logs/testes).
MASTER_UUID = os.getenv("MASTER_SERVER_UUID", "Master_A")
MASTER_NAME = os.getenv("MASTER_NAME", "MASTER_A")
MASTER_IP = os.getenv("MASTER_IP", "127.0.0.1")
MASTER_TCP_PORT = int(os.getenv("MASTER_TCP_PORT", "8888"))

# Sprint 2.1: Discovery
DISCOVERY_PORT = int(os.getenv("DISCOVERY_PORT", "5000"))
DISCOVERY_LISTEN_ADDR = os.getenv("DISCOVERY_LISTEN_ADDR", "0.0.0.0")

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


async def discovery_server(
    master_name: str = MASTER_NAME,
    master_ip: str = MASTER_IP,
    master_port: int = MASTER_TCP_PORT,
    discovery_port: int = DISCOVERY_PORT,
    listen_addr: str = DISCOVERY_LISTEN_ADDR,
):
    """
    Listen for DISCOVERY broadcasts on UDP and respond via unicast.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((listen_addr, discovery_port))
    sock.setblocking(False)
    
    print(f"[Master] DISCOVERY: Escutando em UDP {listen_addr}:{discovery_port}")
    
    try:
        loop = asyncio.get_event_loop()
        
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                
                try:
                    msg = json.loads(data.decode("utf-8", errors="replace").strip())
                    
                    if msg.get("TYPE") != "DISCOVERY":
                        continue
                    
                    worker_uuid = msg.get("WORKER_UUID")
                    if not worker_uuid:
                        continue
                    
                    # Respond with DISCOVERY_REPLY via unicast
                    reply = {
                        "TYPE": "DISCOVERY_REPLY",
                        "MASTER_NAME": master_name,
                        "MASTER_IP": master_ip,
                        "MASTER_PORT": master_port,
                    }
                    reply_json = json.dumps(reply, ensure_ascii=False) + "\n"
                    
                    sock.sendto(reply_json.encode("utf-8"), addr)
                    print(f"[Master] DISCOVERY: Respondido para {addr[0]}:{addr[1]} ({worker_uuid})")
                
                except json.JSONDecodeError:
                    continue
            
            except BlockingIOError:
                await asyncio.sleep(0.01)
                continue
    
    finally:
        sock.close()


async def tratar_conexao(reader, writer):
    endereco = writer.get_extra_info('peername')
    print(f"[Master] Nova conexão de {endereco}")

    worker_origem: dict[str, str | None] = {}
    worker_em_execucao: dict[str, dict] = {}
    
    try:
        # === PHASE 1: Check for ELECTION_ACK (Sprint 2.1) ===
        primeira_msg = await receber_mensagem(reader)
        if not primeira_msg:
            print(f"[Master] {endereco} desconectou sem enviar mensagem")
            return
        
        print(f"[Master] Primeira mensagem recebida: {primeira_msg}")
        
        if primeira_msg.get("TYPE") == "ELECTION_ACK":
            # Sprint 2.1: Handshake com eleição
            exigir_campos(primeira_msg, ["TYPE", "WORKER_UUID", "SELECTED_MASTER"])
            
            worker_uuid = str(primeira_msg["WORKER_UUID"])
            selected_master = str(primeira_msg["SELECTED_MASTER"])
            
            print(f"[Master] ELECTION_ACK recebido de {worker_uuid} (eleito: {selected_master})")
            
            # Verify this Worker selected us
            if selected_master != MASTER_NAME:
                print(f"[Master] Worker selecionou {selected_master}, não {MASTER_NAME}. Fechando.")
                return
            
            # Send acceptance
            ack_response = {
                "TYPE": "ELECTION_ACK",
                "STATUS": "ACCEPTED",
                "MASTER_NAME": MASTER_NAME,
            }
            await enviar_mensagem(writer, ack_response)
            print(f"[Master] ELECTION_ACK: Aceito {worker_uuid}")
            primeira_msg = None
        
        # === PHASE 2: Heartbeat loop (Sprint 1 compatible) ===
        while True:
            # Use primeira_msg if available, otherwise read next message
            if primeira_msg is not None:
                mensagem = primeira_msg
                primeira_msg = None  # Mark as consumed
            else:
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


async def tcp_server(host: str = MASTER_IP, porta: int = MASTER_TCP_PORT):
    """TCP server for heartbeat and task communication."""
    servidor = await asyncio.start_server(tratar_conexao, host, porta)
    endereco = servidor.sockets[0].getsockname()
    print(f"[Master] TCP Server rodando em {endereco} com UUID: {MASTER_UUID}")
    print(f"[Master] Sprint2: fila inicial com {len(TASK_QUEUE)} tarefa(s). Log: {LOG_PATH}")
    
    async with servidor:
        await servidor.serve_forever()


async def main():
    """Run both UDP discovery and TCP server concurrently."""
    discovery_task = asyncio.create_task(discovery_server())
    tcp_task = asyncio.create_task(tcp_server())
    
    await asyncio.gather(discovery_task, tcp_task)


if __name__ == "__main__":
    asyncio.run(main())
