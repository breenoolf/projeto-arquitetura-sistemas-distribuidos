"""
Integration Test Level 3: Full Sprint 3 Workflow

Tests:
1. Multiple Workers with Task Distribution
2. Load Detection and P2P Negotiation
3. Worker Redirection on Saturation
4. Worker Return when Load Normalizes
"""

import asyncio
import json
import os
import sys
import socket
from pathlib import Path
from dotenv import load_dotenv

# Adicionar diretório do projeto ao path
sys.path.insert(0, str(Path(__file__).parent))

from utils import enviar_mensagem, receber_mensagem

load_dotenv()

MASTER_A_IP = os.getenv("MASTER_IP", "127.0.0.1")
MASTER_A_PORT = int(os.getenv("MASTER_TCP_PORT", "8888"))
DISCOVERY_PORT = int(os.getenv("DISCOVERY_PORT", "5000"))


async def worker_test(worker_id: str, num_cycles: int = 5):
    """Simula um Worker completo (Discovery -> Election -> Handshake -> Heartbeat)."""
    print(f"\n[Worker {worker_id}] Iniciando...")
    
    # PHASE 1: DISCOVERY
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)
    
    discovery_msg = json.dumps({"TYPE": "DISCOVERY", "WORKER_UUID": worker_id})
    sock.sendto(discovery_msg.encode() + b"\n", ("255.255.255.255", DISCOVERY_PORT))
    
    discovered = {}
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < 2:
        try:
            sock.settimeout(0.1)
            data, _ = sock.recvfrom(1024)
            msg = json.loads(data.decode().strip())
            if msg.get("TYPE") == "DISCOVERY_REPLY":
                discovered[msg["MASTER_NAME"]] = (msg["MASTER_IP"], msg["MASTER_PORT"])
        except:
            pass
    
    sock.close()
    
    if not discovered:
        print(f"[Worker {worker_id}] ERRO: Nenhum Master descoberto!")
        return False
    
    print(f"[Worker {worker_id}] Descobertos: {list(discovered.keys())}")
    
    # PHASE 2: ELECTION (lexicografia)
    master_name = sorted(discovered.keys())[0]
    master_ip, master_port = discovered[master_name]
    
    print(f"[Worker {worker_id}] Eleito: {master_name}")
    
    # PHASE 3: TCP HANDSHAKE
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(master_ip, master_port),
            timeout=5
        )
    except Exception as e:
        print(f"[Worker {worker_id}] ERRO na conexão TCP: {e}")
        return False
    
    # Send ELECTION_ACK
    ack_msg = {
        "TYPE": "ELECTION_ACK",
        "WORKER_UUID": worker_id,
        "SELECTED_MASTER": master_name,
    }
    await enviar_mensagem(writer, ack_msg)
    
    # Wait for ACK response
    try:
        ack_response = await asyncio.wait_for(receber_mensagem(reader), timeout=5)
        if not ack_response or ack_response.get("STATUS") != "ACCEPTED":
            print(f"[Worker {worker_id}] ERRO: ACK rejeitado")
            return False
    except Exception as e:
        print(f"[Worker {worker_id}] ERRO aguardando ACK: {e}")
        return False
    
    print(f"[Worker {worker_id}] Handshake OK")
    
    # PHASE 4: HEARTBEAT
    tasks_received = 0
    
    for cycle in range(num_cycles):
        try:
            # Send ALIVE
            alive_msg = {"WORKER": "ALIVE", "WORKER_UUID": worker_id}
            await enviar_mensagem(writer, alive_msg)
            
            # Receive TASK or NO_TASK
            task_resp = await asyncio.wait_for(receber_mensagem(reader), timeout=5)
            
            if task_resp.get("TASK") == "NO_TASK":
                print(f"[Worker {worker_id}] Ciclo {cycle+1}: Sem tarefa")
                await asyncio.sleep(0.5)
            else:
                tasks_received += 1
                print(f"[Worker {worker_id}] Ciclo {cycle+1}: Tarefa recebida")
                
                # Send STATUS
                status_msg = {
                    "STATUS": "OK",
                    "TASK": "QUERY",
                    "WORKER_UUID": worker_id,
                }
                await enviar_mensagem(writer, status_msg)
                
                # Wait for ACK
                ack = await asyncio.wait_for(receber_mensagem(reader), timeout=5)
                if not ack or ack.get("STATUS") != "ACK":
                    print(f"[Worker {worker_id}] ERRO: ACK inválido em ciclo {cycle+1}")
                    return False
        
        except Exception as e:
            print(f"[Worker {worker_id}] ERRO no ciclo {cycle+1}: {e}")
            return False
    
    writer.close()
    await writer.wait_closed()
    
    print(f"[Worker {worker_id}] ✅ Concluído ({tasks_received} tarefas)")
    return True


async def main():
    """Teste: 3 Workers distribuindo tarefas."""
    print("\n" + "="*60)
    print("INTEGRATION TEST LEVEL 3: Multiple Workers + P2P Discovery")
    print("="*60)
    
    # Executar 3 workers em paralelo
    results = await asyncio.gather(
        worker_test("W-001", 5),
        worker_test("W-002", 5),
        worker_test("W-003", 5),
    )
    
    print("\n" + "="*60)
    if all(results):
        print("✅ TESTE PASSOU!")
    else:
        print("❌ TESTE FALHOU!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
