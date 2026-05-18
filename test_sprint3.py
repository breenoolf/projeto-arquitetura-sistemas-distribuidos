"""
Sprint 3: Test file para validar protocolo Master-to-Master P2P
"""

import asyncio
import sys
import json
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from utils import enviar_mensagem, receber_mensagem
from master_p2p import MasterP2PManager, MasterNeighbor


async def test_master_p2p_manager():
    """Teste básico do MasterP2PManager."""
    print("\n=== TEST: MasterP2PManager ===")
    
    manager = MasterP2PManager(
        master_id="MASTER_A",
        saturation_threshold=100,
        release_threshold=60,
    )
    
    # Test 1: Adicionar vizinho
    print("\nTest 1: Adicionar vizinho")
    manager.add_neighbor("MASTER_B", "127.0.0.1", 8889)
    assert "MASTER_B" in manager.neighbors, "Vizinho não foi adicionado"
    print("✓ Vizinho adicionado com sucesso")
    
    # Test 2: Parse config de vizinhos
    print("\nTest 2: Parse config de vizinhos")
    manager2 = MasterP2PManager("MASTER_A")
    manager2.parse_neighbors_config("MASTER_B:127.0.0.1:8889,MASTER_C:127.0.0.1:8890")
    assert len(manager2.neighbors) == 2, f"Esperava 2 vizinhos, got {len(manager2.neighbors)}"
    assert "MASTER_B" in manager2.neighbors, "MASTER_B não foi adicionado"
    assert "MASTER_C" in manager2.neighbors, "MASTER_C não foi adicionado"
    print("✓ Config de vizinhos parseada com sucesso")
    
    # Test 3: Registrar Workers emprestados
    print("\nTest 3: Registrar Workers emprestados")
    manager.register_borrowed_worker("W-001", "MASTER_B", "127.0.0.1:8888")
    assert manager.is_borrowed_worker("W-001"), "Worker não foi registrado como emprestado"
    assert manager.get_borrowed_workers_count() == 1, "Count de Workers emprestados incorreto"
    print("✓ Worker emprestado registrado com sucesso")
    
    # Test 4: Desregistrar Worker emprestado
    print("\nTest 4: Desregistrar Worker emprestado")
    manager.unregister_borrowed_worker("W-001")
    assert not manager.is_borrowed_worker("W-001"), "Worker ainda está registrado como emprestado"
    assert manager.get_borrowed_workers_count() == 0, "Count de Workers emprestados não foi zerado"
    print("✓ Worker emprestado desregistrado com sucesso")
    
    # Test 5: Get original master
    print("\nTest 5: Get original master de Worker emprestado")
    manager.register_borrowed_worker("W-002", "MASTER_B", "127.0.0.1:8888")
    orig_info = manager.get_borrowed_worker_original_master("W-002")
    assert orig_info == ("MASTER_B", "127.0.0.1:8888"), f"Original master info incorreta: {orig_info}"
    print("✓ Original master info obtida com sucesso")
    
    print("\n=== Todos os testes passaram! ===\n")


async def test_message_formats():
    """Teste formato das mensagens Sprint 3."""
    print("\n=== TEST: Message Formats ===")
    
    # Test 1: request_help format
    print("\nTest 1: request_help format")
    request_help = {
        "type": "request_help",
        "request_id": "12345-abcde",
        "payload": {
            "master_id": "MASTER_A",
            "current_load": 150,
            "capacity": 100,
            "workers_needed": 2,
        }
    }
    assert request_help["type"] == "request_help"
    assert "request_id" in request_help
    assert "payload" in request_help
    print("✓ request_help format válido")
    
    # Test 2: response_accepted format
    print("\nTest 2: response_accepted format")
    response_accepted = {
        "type": "response_accepted",
        "request_id": "12345-abcde",
        "payload": {
            "workers_offered": 2,
            "worker_details": [
                {"id": "B1", "address": "127.0.0.1:9001"},
                {"id": "B2", "address": "127.0.0.1:9002"},
            ]
        }
    }
    assert response_accepted["type"] == "response_accepted"
    assert response_accepted["request_id"] == "12345-abcde"
    assert len(response_accepted["payload"]["worker_details"]) == 2
    print("✓ response_accepted format válido")
    
    # Test 3: command_redirect format
    print("\nTest 3: command_redirect format")
    command_redirect = {
        "type": "command_redirect",
        "request_id": "67890-fghij",
        "payload": {
            "new_master_address": "127.0.0.1:8888"
        }
    }
    assert command_redirect["type"] == "command_redirect"
    assert "new_master_address" in command_redirect["payload"]
    print("✓ command_redirect format válido")
    
    # Test 4: command_release format
    print("\nTest 4: command_release format")
    command_release = {
        "type": "command_release",
        "request_id": "11111-kkkkk",
        "payload": {
            "original_master_address": "127.0.0.1:8889"
        }
    }
    assert command_release["type"] == "command_release"
    assert "original_master_address" in command_release["payload"]
    print("✓ command_release format válido")
    
    print("\n=== Todos os testes passaram! ===\n")


async def main():
    """Run all tests."""
    try:
        await test_master_p2p_manager()
        await test_message_formats()
        print("✅ TODOS OS TESTES PASSARAM COM SUCESSO!")
    except Exception as e:
        print(f"❌ TESTE FALHOU: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
