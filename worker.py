import asyncio
import json
import os
import random
import socket
import uuid
from pathlib import Path

from dotenv import load_dotenv

from utils import ProtocolError, exigir_campos, enviar_mensagem, receber_mensagem

# Load environment variables from .env file
load_dotenv(Path(__file__).parent / ".env")

# Sprint 2
MASTER_RESPONSE_TIMEOUT_S = float(os.getenv("MASTER_RESPONSE_TIMEOUT_S", "5"))
RECONNECT_DELAY_S = float(os.getenv("RECONNECT_DELAY_S", "3"))
IDLE_WAIT_S = float(os.getenv("IDLE_WAIT_S", "2"))

# Sprint 2.1: Discovery
DISCOVERY_TIMEOUT_S = float(os.getenv("DISCOVERY_TIMEOUT_S", "3.0"))
DISCOVERY_PORT = int(os.getenv("DISCOVERY_PORT", "5000"))
DISCOVERY_BROADCAST_ADDR = os.getenv("DISCOVERY_BROADCAST_ADDR", "255.255.255.255")

WORKER_UUID = os.getenv("WORKER_UUID", str(uuid.uuid4()))

# Campo opcional (apenas se o Worker for "emprestado").
# Ex.: WORKER_ORIGIN_SERVER_UUID=Master_B
WORKER_ORIGIN_SERVER_UUID = os.getenv("WORKER_ORIGIN_SERVER_UUID")

# Simulação de processamento
PROCESSING_MIN_S = float(os.getenv("PROCESSING_MIN_S", "0.5"))
PROCESSING_MAX_S = float(os.getenv("PROCESSING_MAX_S", "2.0"))
FAIL_RATE = float(os.getenv("WORKER_FAIL_RATE", "0.0"))


async def discovery_phase(
    broadcast_addr: str = DISCOVERY_BROADCAST_ADDR,
    discovery_port: int = DISCOVERY_PORT,
    timeout_s: float = DISCOVERY_TIMEOUT_S
) -> list[dict]:
    """
    Send DISCOVERY broadcast via UDP and collect DISCOVERY_REPLY responses.
    
    Returns list of discovered masters: [{"MASTER_NAME": "...", "MASTER_IP": "...", "MASTER_PORT": ...}, ...]
    """
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)  # Non-blocking for asyncio
    
    try:
        # Prepare DISCOVERY payload
        payload = {
            "TYPE": "DISCOVERY",
            "WORKER_UUID": WORKER_UUID
        }
        payload_json = json.dumps(payload, ensure_ascii=False) + "\n"
        
        print(f"[Worker] DISCOVERY: Enviando broadcast para {broadcast_addr}:{discovery_port}")
        sock.sendto(payload_json.encode("utf-8"), (broadcast_addr, discovery_port))
        
        # Collect responses for timeout_s seconds
        discovered = {}
        start_time = asyncio.get_event_loop().time()
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout_s:
                break
            
            remaining = timeout_s - elapsed
            
            try:
                # Non-blocking receive with timeout
                sock.settimeout(min(0.1, remaining))  # Small poll interval
                data, addr = sock.recvfrom(1024)
                
                try:
                    msg = json.loads(data.decode("utf-8", errors="replace").strip())
                    
                    if msg.get("TYPE") != "DISCOVERY_REPLY":
                        continue
                    
                    master_name = msg.get("MASTER_NAME")
                    if not master_name:
                        print(f"[Worker] DISCOVERY: Resposta sem MASTER_NAME ignorada")
                        continue
                    
                    # Store/overwrite with latest response from this master
                    discovered[master_name] = {
                        "MASTER_NAME": master_name,
                        "MASTER_IP": msg.get("MASTER_IP"),
                        "MASTER_PORT": msg.get("MASTER_PORT"),
                    }
                    print(f"[Worker] DISCOVERY: Encontrado {master_name} em {msg.get('MASTER_IP')}:{msg.get('MASTER_PORT')}")
                
                except json.JSONDecodeError:
                    print(f"[Worker] DISCOVERY: Resposta JSON inválida ignorada")
                    continue
            
            except socket.timeout:
                await asyncio.sleep(0.01)  # Yield to event loop
                continue
        
        result = list(discovered.values())
        print(f"[Worker] DISCOVERY: Timeout de {timeout_s}s - Encontrados {len(result)} masters")
        
        return result
    
    finally:
        sock.close()


def election_phase(discovered_masters: list[dict]) -> dict:
    """
    Deterministically elect Master using lexicographic ordering of MASTER_NAME.
    
    Args:
        discovered_masters: List of discovered master dicts with MASTER_NAME, MASTER_IP, MASTER_PORT
    
    Returns:
        Selected master dict (smallest MASTER_NAME lexicographically)
    """
    if not discovered_masters:
        raise ValueError("No masters available for election")
    
    # Sort by MASTER_NAME lexicographically (string comparison)
    sorted_masters = sorted(discovered_masters, key=lambda m: m["MASTER_NAME"])
    
    elected = sorted_masters[0]
    print(f"[Worker] ELECTION: Eleito {elected['MASTER_NAME']} (lexicografia)")
    
    return elected


async def connect_and_handshake(
    master_info: dict,
    timeout_s: float = MASTER_RESPONSE_TIMEOUT_S
) -> tuple:
    """
    Connect to elected Master via TCP and perform ELECTION_ACK handshake.
    
    Returns: (reader, writer) on success
    Raises: ConnectionError, TimeoutError on failure
    """
    master_ip = master_info["MASTER_IP"]
    master_port = master_info["MASTER_PORT"]
    master_name = master_info["MASTER_NAME"]
    
    try:
        print(f"[Worker] CONNECTING: TCP {master_ip}:{master_port}")
        
        # Connect with timeout
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(master_ip, master_port),
            timeout=timeout_s
        )
        
        print(f"[Worker] CONNECTING: Conexão TCP estabelecida")
        
        # Send ELECTION_ACK
        election_ack = {
            "TYPE": "ELECTION_ACK",
            "WORKER_UUID": WORKER_UUID,
            "SELECTED_MASTER": master_name,
        }
        
        await enviar_mensagem(writer, election_ack)
        print(f"[Worker] ELECTION_ACK: Enviado")
        
        # Receive Master's ACK
        try:
            ack_response = await asyncio.wait_for(
                receber_mensagem(reader),
                timeout=timeout_s
            )
        except asyncio.TimeoutError:
            raise TimeoutError("Timeout aguardando ACK do Master")
        
        if not ack_response:
            raise ConnectionError("Master fechou conexão sem responder")
        
        # Validate response
        exigir_campos(ack_response, ["TYPE", "STATUS", "MASTER_NAME"])
        
        if ack_response.get("TYPE") != "ELECTION_ACK":
            raise ProtocolError(f"Resposta não é ELECTION_ACK: {ack_response}")
        
        if ack_response.get("STATUS") != "ACCEPTED":
            raise ProtocolError(f"Master rejeitou eleição: {ack_response}")
        
        if str(ack_response.get("MASTER_NAME")) != master_name:
            raise ProtocolError(f"Master name mismatch: {ack_response}")
        
        print(f"[Worker] ELECTION_ACK: Aceito por {master_name}")
        
        return reader, writer
    
    except Exception as e:
        print(f"[Worker] CONNECTING: Falha - {e}")
        raise



async def iniciar_worker(master_host: str = '127.0.0.1', master_porta: int = 8888):
    """
    Modified to include discovery phase before heartbeat.
    
    Parameters are kept for backward compatibility but are IGNORED in Sprint 2.1.
    """
    while True:
        try:
            # === PHASE 1: DISCOVERY ===
            print(f"[Worker] === FASE 1: DISCOVERY ===")
            discovered_masters = await discovery_phase()
            
            if not discovered_masters:
                print(f"[Worker] DISCOVERY: Nenhum master encontrado. Retry em {RECONNECT_DELAY_S}s")
                await asyncio.sleep(RECONNECT_DELAY_S)
                continue
            
            # === PHASE 2: ELECTION ===
            print(f"[Worker] === FASE 2: ELECTION ===")
            selected_master = election_phase(discovered_masters)
            
            # === PHASE 3: TCP HANDSHAKE ===
            print(f"[Worker] === FASE 3: TCP HANDSHAKE ===")
            reader, writer = None, None
            try:
                reader, writer = await connect_and_handshake(selected_master)
            except Exception as e:
                print(f"[Worker] CONNECTING: Falha com {selected_master['MASTER_NAME']} - tentando próximo")
                # Try next master from discovered list
                for fallback_master in discovered_masters:
                    if fallback_master["MASTER_NAME"] == selected_master["MASTER_NAME"]:
                        continue  # Skip already tried
                    try:
                        print(f"[Worker] FALLBACK: Tentando {fallback_master['MASTER_NAME']}")
                        reader, writer = await connect_and_handshake(fallback_master)
                        break
                    except Exception as fallback_e:
                        print(f"[Worker] FALLBACK: Falha com {fallback_master['MASTER_NAME']}")
                        continue
                
                if reader is None:
                    print(f"[Worker] FALLBACK: Todos os masters falharam. Retry discovery em {RECONNECT_DELAY_S}s")
                    await asyncio.sleep(RECONNECT_DELAY_S)
                    continue
            
            # === PHASE 4: HEARTBEAT (Sprint 1) ===
            print(f"[Worker] === FASE 4: HEARTBEAT LOOP ===")
            
            while True:
                # 1) Apresentação + pedido de tarefa
                payload_alive = {
                    "WORKER": "ALIVE",
                    "WORKER_UUID": WORKER_UUID,
                }
                if WORKER_ORIGIN_SERVER_UUID:
                    payload_alive["SERVER_UUID"] = WORKER_ORIGIN_SERVER_UUID

                await enviar_mensagem(writer, payload_alive)
                print(f"[Worker] Mensagem enviada: {payload_alive}")

                try:
                    resposta = await asyncio.wait_for(receber_mensagem(reader), timeout=MASTER_RESPONSE_TIMEOUT_S)
                except asyncio.TimeoutError:
                    raise TimeoutError("Timeout aguardando resposta do Master")

                if not resposta:
                    raise ConnectionError("Conexão encerrada pelo Master")

                # Compatibilidade Sprint 1 (caso o Master ainda responda heartbeat)
                if resposta.get("TASK") == "HEARTBEAT":
                    if resposta.get("RESPONSE") == "ALIVE":
                        print("[Worker] Status: ALIVE")
                    else:
                        print(f"[Worker] Resposta heartbeat inesperada: {resposta}")
                    await asyncio.sleep(IDLE_WAIT_S)
                    continue

                exigir_campos(resposta, ["TASK"])
                if resposta["TASK"] == "NO_TASK":
                    print("[Worker] Sem tarefa. Aguardando...")
                    await asyncio.sleep(IDLE_WAIT_S)
                    continue

                if resposta["TASK"] != "QUERY":
                    raise ProtocolError("TASK deve ser 'QUERY' ou 'NO_TASK'")
                exigir_campos(resposta, ["TASK", "USER"])
                user = str(resposta["USER"])
                print(f"[Worker] Tarefa recebida: QUERY (USER={user})")

                # 2) Processamento (simulado)
                await asyncio.sleep(random.uniform(PROCESSING_MIN_S, PROCESSING_MAX_S))
                status = "NOK" if random.random() < FAIL_RATE else "OK"

                # 3) Reporte de status
                payload_status = {
                    "STATUS": status,
                    "TASK": "QUERY",
                    "WORKER_UUID": WORKER_UUID,
                }
                await enviar_mensagem(writer, payload_status)
                print(f"[Worker] Status enviado: {payload_status}")

                # 4) Confirmação final (ACK)
                try:
                    ack = await asyncio.wait_for(receber_mensagem(reader), timeout=MASTER_RESPONSE_TIMEOUT_S)
                except asyncio.TimeoutError:
                    raise TimeoutError("Timeout aguardando ACK do Master")

                if not ack:
                    raise ConnectionError("Conexão encerrada pelo Master (sem ACK)")
                exigir_campos(ack, ["STATUS", "WORKER_UUID"])
                if ack.get("STATUS") != "ACK" or str(ack.get("WORKER_UUID")) != WORKER_UUID:
                    raise ProtocolError(f"ACK inválido: {ack}")

                print("[Worker] ACK recebido. Pronto para o próximo ciclo.")

        except Exception as e:
            print(f"[Worker] Status: OFFLINE - Tentando reconectar ({e})")
            await asyncio.sleep(RECONNECT_DELAY_S)
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

if __name__ == "__main__":
    asyncio.run(iniciar_worker())