"""
Sprint 3: Protocolo Master-to-Master P2P para negociação de Workers emprestados.
"""

import asyncio
import json
import uuid
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

from utils import enviar_mensagem, receber_mensagem, ProtocolError


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MasterNeighbor:
    """Representa um Master vizinho no diretório P2P."""
    
    def __init__(self, master_id: str, ip: str, port: int):
        self.master_id = master_id
        self.ip = ip
        self.port = port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected = False
    
    def address_tuple(self) -> Tuple[str, int]:
        return (self.ip, self.port)
    
    async def connect(self, timeout_s: float = 5.0):
        """Conecta ao Master vizinho via TCP."""
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.ip, self.port),
                timeout=timeout_s
            )
            self.connected = True
            print(f"[MasterP2P] Conectado a {self.master_id} ({self.ip}:{self.port})")
            return True
        except Exception as e:
            print(f"[MasterP2P] Falha conectando a {self.master_id}: {e}")
            self.connected = False
            return False
    
    async def disconnect(self):
        """Desconecta do Master vizinho."""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except:
                pass
        self.connected = False
        self.reader = None
        self.writer = None


class MasterP2PManager:
    """Gerencia negociação P2P entre Masters."""
    
    def __init__(
        self,
        master_id: str,
        saturation_threshold: int = 100,
        release_threshold: int = 60,
    ):
        self.master_id = master_id
        self.saturation_threshold = saturation_threshold
        self.release_threshold = release_threshold
        
        # Diretório de vizinhos
        self.neighbors: Dict[str, MasterNeighbor] = {}
        
        # Registro de Workers emprestados: worker_id -> (master_id_original, master_address)
        self.borrowed_workers: Dict[str, Tuple[str, str]] = {}
        
        # Requisições pendentes em negociação
        self.pending_requests: Dict[str, dict] = {}
        
        # Referência ao dicionário de Workers conectados (será passado pelo Master)
        self.connected_workers_ref: Dict[str, any] = None
    
    def add_neighbor(self, master_id: str, ip: str, port: int):
        """Adiciona um Master vizinho ao diretório."""
        self.neighbors[master_id] = MasterNeighbor(master_id, ip, port)
        print(f"[MasterP2P] Vizinho adicionado: {master_id} ({ip}:{port})")
    
    def parse_neighbors_config(self, neighbors_str: str):
        """
        Parse neighbors config string: "MASTER_B:127.0.0.1:8889,MASTER_C:127.0.0.1:8890"
        """
        if not neighbors_str or neighbors_str.strip() == "":
            return
        
        for neighbor_entry in neighbors_str.split(","):
            parts = neighbor_entry.strip().split(":")
            if len(parts) != 3:
                print(f"[MasterP2P] Config vizinho inválida: {neighbor_entry}")
                continue
            
            master_id, ip, port = parts[0].strip(), parts[1].strip(), int(parts[2].strip())
            self.add_neighbor(master_id, ip, port)
    
    async def request_help(
        self,
        current_load: int,
        capacity: int,
        workers_needed: int,
        timeout_s: float = 5.0
    ) -> Optional[dict]:
        """
        Envia pedido de ajuda para o primeiro vizinho disponível.
        
        Retorna dict com:
        - workers_offered: número de Workers oferecidos
        - worker_details: lista de dicts com {id, address}
        
        Ou None se nenhum vizinho aceitar.
        """
        for neighbor_id, neighbor in self.neighbors.items():
            try:
                result = await self._request_help_to_neighbor(
                    neighbor,
                    current_load,
                    capacity,
                    workers_needed,
                    timeout_s
                )
                if result:
                    return result
            except Exception as e:
                print(f"[MasterP2P] Erro pedindo ajuda a {neighbor_id}: {e}")
                continue
        
        print(f"[MasterP2P] Nenhum vizinho disponível para emprestar Workers")
        return None
    
    async def _request_help_to_neighbor(
        self,
        neighbor: MasterNeighbor,
        current_load: int,
        capacity: int,
        workers_needed: int,
        timeout_s: float = 5.0
    ) -> Optional[dict]:
        """Negocia com um vizinho específico."""
        
        # Conectar se necessário
        if not neighbor.connected:
            if not await neighbor.connect(timeout_s):
                return None
        
        request_id = str(uuid.uuid4())
        
        # Mensagem: request_help
        request_msg = {
            "type": "request_help",
            "request_id": request_id,
            "payload": {
                "master_id": self.master_id,
                "current_load": current_load,
                "capacity": capacity,
                "workers_needed": workers_needed,
            }
        }
        
        try:
            # Enviar
            await enviar_mensagem(neighbor.writer, request_msg)
            print(f"[MasterP2P] request_help enviado para {neighbor.master_id} (request_id={request_id})")
            
            # Receber resposta com timeout
            response = await asyncio.wait_for(
                receber_mensagem(neighbor.reader),
                timeout=timeout_s
            )
            
            if not response:
                print(f"[MasterP2P] {neighbor.master_id} desconectou sem responder")
                neighbor.connected = False
                return None
            
            # Validar response
            if response.get("type") == "response_accepted":
                if response.get("request_id") != request_id:
                    raise ProtocolError(f"request_id mismatch: {response.get('request_id')} != {request_id}")
                
                payload = response.get("payload", {})
                workers_offered = payload.get("workers_offered", 0)
                worker_details = payload.get("worker_details", [])
                
                print(f"[MasterP2P] response_accepted: {workers_offered} Workers oferecidos")
                
                # Armazenar na lista de requisições pendentes para rastreio
                self.pending_requests[request_id] = {
                    "neighbor_id": neighbor.master_id,
                    "workers_offered": workers_offered,
                    "worker_details": worker_details,
                }
                
                return {
                    "workers_offered": workers_offered,
                    "worker_details": worker_details,
                    "neighbor": neighbor,
                    "request_id": request_id,
                }
            
            elif response.get("type") == "response_rejected":
                reason = response.get("payload", {}).get("reason", "unknown")
                print(f"[MasterP2P] response_rejected: {reason}")
                return None
            
            else:
                raise ProtocolError(f"Resposta inesperada: {response.get('type')}")
        
        except asyncio.TimeoutError:
            print(f"[MasterP2P] Timeout aguardando resposta de {neighbor.master_id}")
            neighbor.connected = False
            return None
        except Exception as e:
            print(f"[MasterP2P] Erro na negociação com {neighbor.master_id}: {e}")
            neighbor.connected = False
            raise
    
    def register_borrowed_worker(self, worker_id: str, original_master_id: str, original_address: str):
        """Registra um Worker emprestado."""
        self.borrowed_workers[worker_id] = (original_master_id, original_address)
        print(f"[MasterP2P] Worker emprestado registrado: {worker_id} (original: {original_master_id})")
    
    def unregister_borrowed_worker(self, worker_id: str):
        """Remove registro de Worker emprestado."""
        if worker_id in self.borrowed_workers:
            original_master_id, _ = self.borrowed_workers.pop(worker_id)
            print(f"[MasterP2P] Worker emprestado desregistrado: {worker_id}")
    
    def get_borrowed_worker_original_master(self, worker_id: str) -> Optional[Tuple[str, str]]:
        """Retorna (master_id, address) do Master original do Worker emprestado."""
        return self.borrowed_workers.get(worker_id)
    
    def is_borrowed_worker(self, worker_id: str) -> bool:
        """Verifica se um Worker é emprestado."""
        return worker_id in self.borrowed_workers
    
    def get_borrowed_workers_count(self) -> int:
        """Retorna número de Workers emprestados."""
        return len(self.borrowed_workers)
    
    async def notify_worker_returned(
        self,
        worker_id: str,
        original_master_neighbor: MasterNeighbor,
        timeout_s: float = 5.0
    ):
        """Notifica o Master original que um Worker foi devolvido."""
        
        request_id = str(uuid.uuid4())
        
        message = {
            "type": "notify_worker_returned",
            "request_id": request_id,
            "payload": {
                "worker_id": worker_id,
            }
        }
        
        try:
            # Conectar se necessário
            if not original_master_neighbor.connected:
                await original_master_neighbor.connect(timeout_s)
            
            await enviar_mensagem(original_master_neighbor.writer, message)
            print(f"[MasterP2P] notify_worker_returned enviado para {original_master_neighbor.master_id}")
        except Exception as e:
            print(f"[MasterP2P] Erro notificando devolução: {e}")
    
    async def disconnect_all(self):
        """Desconecta de todos os vizinhos."""
        for neighbor in self.neighbors.values():
            await neighbor.disconnect()
    
    async def send_command_redirect(
        self,
        worker_id: str,
        new_master_address: str,
        connected_workers: Dict[str, any],
        timeout_s: float = 5.0
    ):
        """
        Sprint 3 T04: Envia command_redirect para um Worker específico.
        
        Conectado_workers é um dict {worker_id -> asyncio.StreamWriter}
        """
        if worker_id not in connected_workers:
            print(f"[MasterP2P] Worker {worker_id} não encontrado na lista de conectados")
            return False
        
        writer = connected_workers[worker_id]
        request_id = str(uuid.uuid4())
        
        message = {
            "type": "command_redirect",
            "request_id": request_id,
            "payload": {
                "new_master_address": new_master_address,
            }
        }
        
        try:
            await enviar_mensagem(writer, message)
            print(f"[MasterP2P] command_redirect enviado para {worker_id}")
            return True
        except Exception as e:
            print(f"[MasterP2P] Erro enviando command_redirect para {worker_id}: {e}")
            return False
    
    async def send_command_release(
        self,
        worker_id: str,
        original_master_address: str,
        connected_workers: Dict[str, any],
        timeout_s: float = 5.0
    ):
        """
        Sprint 3 T05: Envia command_release para um Worker.
        """
        if worker_id not in connected_workers:
            print(f"[MasterP2P] Worker {worker_id} não encontrado na lista de conectados")
            return False
        
        writer = connected_workers[worker_id]
        request_id = str(uuid.uuid4())
        
        message = {
            "type": "command_release",
            "request_id": request_id,
            "payload": {
                "original_master_address": original_master_address,
            }
        }
        
        try:
            await enviar_mensagem(writer, message)
            print(f"[MasterP2P] command_release enviado para {worker_id}")
            return True
        except Exception as e:
            print(f"[MasterP2P] Erro enviando command_release para {worker_id}: {e}")
            return False
