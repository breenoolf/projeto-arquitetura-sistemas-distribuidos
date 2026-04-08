import asyncio
import os
import random
import uuid

from utils import ProtocolError, exigir_campos, enviar_mensagem, receber_mensagem

# Sprint 2
MASTER_RESPONSE_TIMEOUT_S = float(os.getenv("MASTER_RESPONSE_TIMEOUT_S", "5"))
RECONNECT_DELAY_S = float(os.getenv("RECONNECT_DELAY_S", "3"))
IDLE_WAIT_S = float(os.getenv("IDLE_WAIT_S", "2"))

WORKER_UUID = os.getenv("WORKER_UUID", str(uuid.uuid4()))

# Campo opcional (apenas se o Worker for "emprestado").
# Ex.: WORKER_ORIGIN_SERVER_UUID=Master_B
WORKER_ORIGIN_SERVER_UUID = os.getenv("WORKER_ORIGIN_SERVER_UUID")

# Simulação de processamento
PROCESSING_MIN_S = float(os.getenv("PROCESSING_MIN_S", "0.5"))
PROCESSING_MAX_S = float(os.getenv("PROCESSING_MAX_S", "2.0"))
FAIL_RATE = float(os.getenv("WORKER_FAIL_RATE", "0.0"))


async def iniciar_worker(master_host: str = '127.0.0.1', master_porta: int = 8888):
    while True:
        print(f"[Worker] Conectando ao Master em {master_host}:{master_porta}...")
        writer = None
        try:
            reader, writer = await asyncio.open_connection(master_host, master_porta)

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