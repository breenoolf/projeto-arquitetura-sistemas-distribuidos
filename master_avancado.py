import asyncio
import uuid
import random
import sys
from utils import enviar_mensagem, receber_mensagem

class MasterNode:
    def __init__(self, host, porta, vizinho_host=None, vizinho_porta=None):
        self.uuid = str(uuid.uuid4())
        self.host = host
        self.porta = porta
        self.vizinho_host = vizinho_host
        self.vizinho_porta = vizinho_porta
        
        self.carga_atual = 0
        self.threshold = 5 
        self.saturado = False
        self.workers_conectados = []
        
    async def simular_requisicoes(self):
        while True:
            await asyncio.sleep(random.uniform(2, 4))
            # Simula a chegada de novas requisições
            self.carga_atual += random.randint(1, 3)
            
            # SIMULAÇÃO DE PROCESSAMENTO: Se tem workers, a carga diminui!
            capacidade_processamento = len(self.workers_conectados) * 5
            self.carga_atual -= capacidade_processamento
            if self.carga_atual < 0:
                self.carga_atual = 0
                
            print(f"[Master {self.porta}] Carga atual: {self.carga_atual}/{self.threshold}")

    async def monitorar_saturacao(self):
        while True:
            await asyncio.sleep(1)
            # FASE 1: Saturação
            if self.carga_atual > self.threshold and not self.saturado:
                print(f"[Master {self.porta}] ALERTA: Saturação detetada! A iniciar protocolo de socorro...")
                self.saturado = True
                await self.pedir_ajuda_ao_vizinho()
                
            # FASE 2: Normalização (Devolução)
            elif self.carga_atual <= self.threshold and self.saturado:
                print(f"[Master {self.porta}] Carga normalizada. A devolver Worker emprestado...")
                self.saturado = False
                await self.devolver_worker_emprestado()

    async def pedir_ajuda_ao_vizinho(self):
        if not self.vizinho_host or not self.vizinho_porta: return
        try:
            reader, writer = await asyncio.open_connection(self.vizinho_host, self.vizinho_porta)
            await enviar_mensagem(writer, {"type": "request_help", "host_destino": self.host, "porta_destino": self.porta})
            resposta = await receber_mensagem(reader)
            
            if resposta and resposta.get("type") == "response_accepted":
                print(f"[Master {self.porta}] Vizinho ACEITOU! À espera do Worker...")
            else:
                print(f"[Master {self.porta}] Vizinho REJEITOU o pedido.")
            writer.close()
            await writer.wait_closed()
        except Exception: pass

    async def devolver_worker_emprestado(self):
        # Passo 7: Envia o command_release para o Worker
        if len(self.workers_conectados) > 0:
            worker_writer = self.workers_conectados.pop()
            await enviar_mensagem(worker_writer, {"type": "command_release"})
            print(f"[Master {self.porta}] Ordem de libertação (command_release) enviada ao Worker!")
            
            # Passo 9: Avisa o Master original (Master B) que o Worker está a voltar
            try:
                reader, writer = await asyncio.open_connection(self.vizinho_host, self.vizinho_porta)
                await enviar_mensagem(writer, {"type": "notify_worker_returned"})
                print(f"[Master {self.porta}] Notificação de devolução enviada ao vizinho!")
                writer.close()
                await writer.wait_closed()
            except Exception: pass

    async def tratar_conexao(self, reader, writer):
        try:
            while True:
                mensagem = await receber_mensagem(reader)
                if not mensagem: break
                tipo = mensagem.get("type")

                if tipo in ["register_worker", "register_temporary_worker"]:
                    self.workers_conectados.append(writer)
                    print(f"[Master {self.porta}] Um Worker ligou-se! Total de workers: {len(self.workers_conectados)}")

                elif tipo == "request_help":
                    host_destino = mensagem.get("host_destino")
                    porta_destino = mensagem.get("porta_destino")
                    if self.carga_atual < self.threshold and len(self.workers_conectados) > 0:
                        await enviar_mensagem(writer, {"type": "response_accepted"})
                        worker_writer = self.workers_conectados.pop()
                        await enviar_mensagem(worker_writer, {"type": "command_redirect", "novo_host": host_destino, "nova_porta": porta_destino})
                    else:
                        await enviar_mensagem(writer, {"type": "response_rejected"})
                
                # Passo 10: Recebe a notificação de que o seu Worker foi devolvido
                elif tipo == "notify_worker_returned":
                    print(f"[Master {self.porta}] Boa notícia! Um dos meus Workers terminou a ajuda e está a voltar.")

        except Exception: pass
        finally:
            if writer in self.workers_conectados: self.workers_conectados.remove(writer)
            writer.close()
            await writer.wait_closed()

    async def iniciar(self):
        servidor = await asyncio.start_server(self.tratar_conexao, self.host, self.porta)
        print(f"=== Master a rodar na porta {self.porta} ===")
        if self.porta == 8888: asyncio.create_task(self.simular_requisicoes())
        asyncio.create_task(self.monitorar_saturacao())
        async with servidor: await servidor.serve_forever()

if __name__ == "__main__":
    porta_atual = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    porta_vizinho = int(sys.argv[2]) if len(sys.argv) > 2 else None
    master = MasterNode('127.0.0.1', porta_atual, vizinho_host='127.0.0.1', vizinho_porta=porta_vizinho)
    asyncio.run(master.iniciar())