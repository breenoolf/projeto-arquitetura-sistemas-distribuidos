import asyncio
import json
import os
import socket
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv

from utils import ProtocolError, exigir_campos, enviar_mensagem, receber_mensagem
from master_p2p import MasterP2PManager

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

# Sprint 3: Protocolo Master-to-Master P2P
# Configurações de saturação e limites
SATURATION_THRESHOLD = int(os.getenv("MASTER_SATURATION_THRESHOLD", "100"))
RELEASE_THRESHOLD = int(os.getenv("MASTER_RELEASE_THRESHOLD", "60"))
LOAD_CHECK_INTERVAL_S = float(os.getenv("LOAD_CHECK_INTERVAL_S", "2"))
MASTER_P2P_PORT = int(os.getenv("MASTER_P2P_PORT", "9999"))
NEIGHBORS_CONFIG = os.getenv("MASTER_NEIGHBORS", "")

# Locks para proteção de estruturas compartilhadas (concorrência)
task_queue_lock = Lock()
current_load_lock = Lock()
borrowed_workers_lock = Lock()
connected_workers_lock = Lock()

# Rastreamento de Workers conectados: worker_id -> writer
# Permite que o Master envie mensagens para Workers específicos (para command_redirect)
connected_workers: dict[str, asyncio.StreamWriter] = {}

# Monitoramento de carga (requisições pendentes)
current_load = 0

# Manager P2P
p2p_manager = MasterP2PManager(
    master_id=MASTER_NAME,
    saturation_threshold=SATURATION_THRESHOLD,
    release_threshold=RELEASE_THRESHOLD,
)
p2p_manager.parse_neighbors_config(NEIGHBORS_CONFIG)


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
    global current_load, connected_workers, borrowed_workers_lock, current_load_lock, connected_workers_lock, task_queue_lock, TASK_QUEUE, p2p_manager
    
    endereco = writer.get_extra_info('peername')

    worker_origem: dict[str, str | None] = {}
    worker_em_execucao: dict[str, dict] = {}
    worker_uuid_connected: str = None  # Rastrear worker UUID
    
    try:
        # === PHASE 1: Check for ELECTION_ACK (Sprint 2.1) ===
        primeira_msg = await receber_mensagem(reader)
        if not primeira_msg:
            print(f"[Master] {endereco} desconectou sem enviar mensagem")
            return
        
        if primeira_msg.get("TYPE") == "ELECTION_ACK":
            # Sprint 2.1: Handshake com eleição
            exigir_campos(primeira_msg, ["TYPE", "WORKER_UUID", "SELECTED_MASTER"])
            
            worker_uuid = str(primeira_msg["WORKER_UUID"])
            selected_master = str(primeira_msg["SELECTED_MASTER"])
            
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
                
                # Sprint 3 T07: Rastrear Worker conectado
                with connected_workers_lock:
                    connected_workers[worker_uuid] = writer
                    worker_uuid_connected = worker_uuid
                
                # Sprint 3: Se tem SERVER_UUID, é um Worker emprestado
                if server_uuid_origem:
                    with borrowed_workers_lock:
                        # Registrar como emprestado
                        original_address = f"{endereco[0]}:{endereco[1]}"  # Endereço do Worker
                        p2p_manager.register_borrowed_worker(worker_uuid, server_uuid_origem, original_address)
                    
                    _log_linha(f"[{_agora_iso()}] [Master {MASTER_UUID}] WORKER_REGISTERED: worker_id={worker_uuid} original_master={server_uuid_origem}")

                with task_queue_lock:
                    if TASK_QUEUE:
                        tarefa = TASK_QUEUE.popleft()
                        worker_em_execucao[worker_uuid] = tarefa
                        await enviar_mensagem(writer, tarefa)
                        _log_linha(f"[{_agora_iso()}] [Master {MASTER_UUID}] TASK-> Worker={worker_uuid} Origem={worker_origem[worker_uuid] or 'LOCAL'} Tarefa={tarefa}")
                        
                        # Incrementar carga apenas quando realmente enviamos uma tarefa
                        with current_load_lock:
                            current_load += 1
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
                is_borrowed = p2p_manager.is_borrowed_worker(worker_uuid)
                _log_linha(
                    f"[{_agora_iso()}] [Master {MASTER_UUID}] STATUS<- Worker={worker_uuid} Origem={origem or 'LOCAL'} Borrowed={is_borrowed} Status={status} Tarefa={tarefa_enviada}"
                )

                with current_load_lock:
                    current_load = max(0, current_load - 1)

                await enviar_mensagem(writer, {"STATUS": "ACK", "WORKER_UUID": worker_uuid})
                continue

            # Sprint 3: Suporte a command_release do Master vizinho
            # (este tipo de mensagem normalmente vem via conexão direta para o Worker,
            # mas por compatibilidade adicionamos aqui também)
            if mensagem.get("type") == "command_release":
                exigir_campos(mensagem, ["type", "payload"])
                payload = mensagem.get("payload", {})
                worker_id = payload.get("worker_id")
                
                print(f"[Master] command_release recebido para worker {worker_id}")
                # O Worker gerencia isto, não o Master
                continue

            # Se cair aqui, é um payload desconhecido: ignora (tolerância a interoperabilidade)
            # Permite que outros grupos enviem mensagens com tipos não reconhecidos
            continue
                
    except ProtocolError as e:
        print(f"[Master] Erro de protocolo com {endereco}: {e}")
    except Exception as e:
        print(f"[Master] Erro na conexão com {endereco}: {e}")
    finally:
        # Sprint 3 T07: Remover Worker do rastreamento ao desconectar
        if worker_uuid_connected:
            with connected_workers_lock:
                connected_workers.pop(worker_uuid_connected, None)
            _log_linha(f"[{_agora_iso()}] [Master {MASTER_UUID}] WORKER_DISCONNECTED: worker_id={worker_uuid_connected}")
        
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


async def tratar_conexao_p2p(reader, writer):
    """Trata conexão incoming de outros Masters (Sprint 3)."""
    endereco = writer.get_extra_info('peername')
    print(f"[MasterP2P] Nova conexão P2P de {endereco}")
    
    try:
        while True:
            mensagem = await receber_mensagem(reader)
            if not mensagem:
                break
            
            print(f"[MasterP2P] Recebido de {endereco}: {mensagem}")
            
            msg_type = mensagem.get("type")
            request_id = mensagem.get("request_id")
            payload = mensagem.get("payload", {})
            
            # T03: Responder a request_help
            if msg_type == "request_help":
                exigir_campos(mensagem, ["type", "request_id", "payload"])
                exigir_campos(payload, ["master_id", "current_load", "capacity", "workers_needed"])
                
                workers_needed = payload.get("workers_needed", 0)
                
                # Verificar disponibilidade de Workers locais ociosos
                # Por enquanto, sempre recusamos (será implementado em T06)
                # TODO: implementar lógica de decisão baseada em carga local
                
                resposta = {
                    "type": "response_rejected",
                    "request_id": request_id,
                    "payload": {
                        "reason": "high_load"  # Simplificado por enquanto
                    }
                }
                await enviar_mensagem(writer, resposta)
                print(f"[MasterP2P] response_rejected enviado")
            
            # T05: Receber notificação de devolução de Worker
            elif msg_type == "notify_worker_returned":
                exigir_campos(mensagem, ["type", "request_id", "payload"])
                exigir_campos(payload, ["worker_id"])
                
                worker_id = payload.get("worker_id")
                print(f"[MasterP2P] Worker {worker_id} foi devolvido pelo Master vizinho")
                
                with borrowed_workers_lock:
                    p2p_manager.unregister_borrowed_worker(worker_id)
                
                _log_linha(f"[{_agora_iso()}] [Master {MASTER_UUID}] WORKER_RETURNED: worker_id={worker_id}")
            
            else:
                # Tipo desconhecido - ignorar conforme Sprint 3
                print(f"[MasterP2P] Tipo de mensagem desconhecido: {msg_type}")
    
    except ProtocolError as e:
        print(f"[MasterP2P] Erro de protocolo: {e}")
    except Exception as e:
        print(f"[MasterP2P] Erro: {e}")
    finally:
        print(f"[MasterP2P] Fechando conexão com {endereco}")
        writer.close()
        await writer.wait_closed()


async def p2p_server(host: str = MASTER_IP, porta: int = MASTER_P2P_PORT):
    """TCP server para comunicação P2P com outros Masters (Sprint 3)."""
    servidor = await asyncio.start_server(tratar_conexao_p2p, host, porta)
    endereco = servidor.sockets[0].getsockname()
    print(f"[MasterP2P] P2P Server rodando em {endereco}")
    
    async with servidor:
        await servidor.serve_forever()


async def monitor_saturation(check_interval: float = LOAD_CHECK_INTERVAL_S):
    """
    Monitor de saturação (Sprint 3, T02).
    Verifica periodicamente se a carga excedeu o threshold de saturação.
    """
    global current_load
    
    print(f"[MasterP2P] Monitor de saturação iniciado. Threshold={SATURATION_THRESHOLD}, Liberação={RELEASE_THRESHOLD}, Intervalo={check_interval}s")
    
    while True:
        await asyncio.sleep(check_interval)
        
        with current_load_lock:
            load = current_load
        
        with borrowed_workers_lock:
            borrowed_count = p2p_manager.get_borrowed_workers_count()
        
        _log_linha(f"[{_agora_iso()}] [Master {MASTER_UUID}] LOAD_CHECK: current_load={load} borrowed_workers={borrowed_count}")
        
        # T02: Detectar saturação
        if load > SATURATION_THRESHOLD and borrowed_count == 0:
            workers_needed = max(1, (load - SATURATION_THRESHOLD) // 10)  # Heurística simples
            print(f"[MasterP2P] ⚠️  SATURAÇÃO DETECTADA: load={load} > threshold={SATURATION_THRESHOLD}")
            print(f"[MasterP2P] Solicitando {workers_needed} Workers emprestados...")
            
            # T03: Enviar request_help
            help_response = await p2p_manager.request_help(
                current_load=load,
                capacity=SATURATION_THRESHOLD,
                workers_needed=workers_needed,
                timeout_s=5.0
            )
            
            if help_response:
                print(f"[MasterP2P] Ajuda aceita: {help_response['workers_offered']} Workers")
                _log_linha(f"[{_agora_iso()}] [Master {MASTER_UUID}] HELP_ACCEPTED: workers_offered={help_response['workers_offered']}")
                
                # T04: Enviar command_redirect a cada Worker
                neighbor = help_response.get('neighbor')
                if neighbor:
                    for worker_detail in help_response.get('worker_details', []):
                        worker_id = worker_detail.get('id')
                        worker_address = worker_detail.get('address')
                        
                        # Enviar command_redirect
                        print(f"[MasterP2P] Enviando command_redirect para {worker_id} (novo Master: {MASTER_IP}:{MASTER_TCP_PORT})")
                        success = await p2p_manager.send_command_redirect(
                            worker_id=worker_id,
                            new_master_address=f"{MASTER_IP}:{MASTER_TCP_PORT}",
                            connected_workers=connected_workers
                        )
                        
                        if success:
                            # Registrar temporariamente
                            with borrowed_workers_lock:
                                p2p_manager.register_borrowed_worker(worker_id, neighbor.master_id, neighbor.address_tuple())
                            _log_linha(f"[{_agora_iso()}] [Master {MASTER_UUID}] REDIRECT_SENT: worker_id={worker_id}")
                        else:
                            _log_linha(f"[{_agora_iso()}] [Master {MASTER_UUID}] REDIRECT_FAILED: worker_id={worker_id}")
            else:
                print(f"[MasterP2P] Ajuda recusada por todos os vizinhos")
                _log_linha(f"[{_agora_iso()}] [Master {MASTER_UUID}] HELP_REJECTED: Nenhum vizinho disponível")
        
        # Verificar liberação de Workers
        elif load <= RELEASE_THRESHOLD and borrowed_count > 0:
            print(f"[MasterP2P] ℹ️  CARGA NORMALIZADA: load={load} <= threshold_liberacao={RELEASE_THRESHOLD}")
            print(f"[MasterP2P] Devolvendo {borrowed_count} Workers emprestados...")
            
            # T05: Devolver Workers
            with borrowed_workers_lock:
                # Copiar lista de Workers para evitar problemas de iteração enquanto modifica
                borrowed_list = list(p2p_manager.borrowed_workers.items())
            
            for worker_id, (original_master_id, original_address) in borrowed_list:
                # Enviar command_release ao Worker
                print(f"[MasterP2P] Enviando command_release para {worker_id} (Master original: {original_address})")
                success = await p2p_manager.send_command_release(
                    worker_id=worker_id,
                    original_master_address=original_address,
                    connected_workers=connected_workers
                )
                
                if success:
                    _log_linha(f"[{_agora_iso()}] [Master {MASTER_UUID}] RELEASE_SENT: worker_id={worker_id} original_master={original_master_id}")
                    
                    # Encontrar o Master vizinho original para notificar
                    neighbor = p2p_manager.neighbors.get(original_master_id)
                    if neighbor:
                        # Enviar notify_worker_returned
                        await p2p_manager.notify_worker_returned(
                            worker_id=worker_id,
                            original_master_neighbor=neighbor
                        )
                        _log_linha(f"[{_agora_iso()}] [Master {MASTER_UUID}] NOTIFY_RETURNED: worker_id={worker_id}")
                    
                    # Desregistrar do rastreamento de emprestados
                    with borrowed_workers_lock:
                        p2p_manager.unregister_borrowed_worker(worker_id)
                else:
                    _log_linha(f"[{_agora_iso()}] [Master {MASTER_UUID}] RELEASE_FAILED: worker_id={worker_id}")


async def main():
    """Run both UDP discovery and TCP server concurrently."""
    discovery_task = asyncio.create_task(discovery_server())
    tcp_task = asyncio.create_task(tcp_server())
    p2p_task = asyncio.create_task(p2p_server())
    saturation_task = asyncio.create_task(monitor_saturation())
    
    await asyncio.gather(discovery_task, tcp_task, p2p_task, saturation_task)


if __name__ == "__main__":
    asyncio.run(main())
