import asyncio
import os
from utils import enviar_mensagem, receber_mensagem

# Sprint 1 (Heartbeat): manter um identificador estável do servidor.
# Pode ser sobrescrito por variável de ambiente para testes.
SERVER_UUID = os.getenv("MASTER_SERVER_UUID", "Master_A")

async def tratar_conexao(reader, writer):
    endereco = writer.get_extra_info('peername')
    print(f"[Master] Nova conexão de {endereco}")
    
    try:
        while True:
            # Escuta contínua por mensagens na conexão
            mensagem = await receber_mensagem(reader)
            if not mensagem:
                break
                
            print(f"[Master] Recebido: {mensagem}")
            
            # Trata o payload oficial de HEARTBEAT
            if mensagem.get("TASK") == "HEARTBEAT":
                resposta = {
                    "SERVER_UUID": SERVER_UUID,
                    "TASK": "HEARTBEAT",
                    "RESPONSE": "ALIVE"
                }
                await enviar_mensagem(writer, resposta)
                print(f"[Master] Resposta enviada: {resposta}")
                
    except Exception as e:
        print(f"[Master] Erro na conexão com {endereco}: {e}")
    finally:
        print(f"[Master] Fechando conexão com {endereco}")
        writer.close()
        await writer.wait_closed()

async def iniciar_master(host='127.0.0.1', porta=8888):
    servidor = await asyncio.start_server(tratar_conexao, host, porta)
    endereco = servidor.sockets[0].getsockname()
    print(f"[Master] Servidor rodando em {endereco} com UUID: {SERVER_UUID}")
    
    async with servidor:
        await servidor.serve_forever()

if __name__ == "__main__":
    asyncio.run(iniciar_master())