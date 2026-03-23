import asyncio
from utils import enviar_mensagem, receber_mensagem

async def iniciar_worker(master_original_host='127.0.0.1', master_original_porta=8889):
    host_atual = master_original_host
    porta_atual = master_original_porta
    
    while True:
        print(f"\n[Worker] A ligar ao Master em {host_atual}:{porta_atual}...")
        try:
            reader, writer = await asyncio.open_connection(host_atual, porta_atual)
            
            if porta_atual == master_original_porta:
                await enviar_mensagem(writer, {"type": "register_worker"})
                print("[Worker] Registado como Worker residente.")
            else:
                await enviar_mensagem(writer, {"type": "register_temporary_worker"})
                print("[Worker] Registado como Worker TEMPORÁRIO para ajudar!")

            while True:
                mensagem = await receber_mensagem(reader)
                if not mensagem:
                    print("[Worker] A ligação com o Master foi encerrada.")
                    break
                
                tipo = mensagem.get("type")
                
                # FASE 1: Redirecionamento (Ida)
                if tipo == "command_redirect":
                    novo_host = mensagem.get("novo_host")
                    nova_porta = mensagem.get("nova_porta")
                    print(f"[Worker] Recebi ordem de redirecionamento para {novo_host}:{nova_porta}! A mudar de Master...")
                    host_atual = novo_host
                    porta_atual = nova_porta
                    break 
                
                # FASE 2: Libertação (Volta)
                elif tipo == "command_release":
                    print("[Worker] Carga normalizada! Recebi ordem para voltar ao Master original...")
                    host_atual = master_original_host
                    porta_atual = master_original_porta
                    break
                
                elif mensagem.get("TASK") == "HEARTBEAT":
                    print(f"[Worker] Recebeu Heartbeat do Master.")

        except Exception as e:
            print(f"[Worker] Erro: {e}. A tentar novamente em 3 segundos...")
            await asyncio.sleep(3)
        finally:
            writer.close()
            await writer.wait_closed()

if __name__ == "__main__":
    asyncio.run(iniciar_worker())