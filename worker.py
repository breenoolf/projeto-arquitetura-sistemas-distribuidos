import asyncio
import os
from utils import enviar_mensagem, receber_mensagem

# Sprint 1 (Heartbeat)
HEARTBEAT_INTERVAL_S = float(os.getenv("HEARTBEAT_INTERVAL_S", "30"))
HEARTBEAT_TIMEOUT_S = float(os.getenv("HEARTBEAT_TIMEOUT_S", "5"))
RECONNECT_DELAY_S = float(os.getenv("RECONNECT_DELAY_S", "3"))
TARGET_SERVER_UUID = os.getenv("TARGET_SERVER_UUID", "Master_A")


async def iniciar_worker(master_host: str = '127.0.0.1', master_porta: int = 8888):
    while True:
        print(f"[Worker] Conectando ao Master em {master_host}:{master_porta}...")
        writer = None
        try:
            reader, writer = await asyncio.open_connection(master_host, master_porta)

            # Mantém a conexão e envia heartbeat periodicamente.
            while True:
                payload_heartbeat = {
                    "SERVER_UUID": TARGET_SERVER_UUID,
                    "TASK": "HEARTBEAT",
                }
                await enviar_mensagem(writer, payload_heartbeat)
                print(f"[Worker] Mensagem enviada: {payload_heartbeat}")

                try:
                    resposta = await asyncio.wait_for(receber_mensagem(reader), timeout=HEARTBEAT_TIMEOUT_S)
                except asyncio.TimeoutError:
                    raise TimeoutError("Timeout aguardando resposta do Master")

                if not resposta:
                    raise ConnectionError("Conexão encerrada pelo Master")

                if resposta.get("TASK") == "HEARTBEAT" and resposta.get("RESPONSE") == "ALIVE":
                    print("[Worker] Status: ALIVE")
                else:
                    print(f"[Worker] Resposta inesperada: {resposta}")

                await asyncio.sleep(HEARTBEAT_INTERVAL_S)

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