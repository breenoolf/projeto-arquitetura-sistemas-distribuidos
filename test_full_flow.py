import asyncio
import subprocess
import os
import time
import sys

async def test_full_discovery_election_flow():
    """Test complete flow: discovery + election + handshake."""
    
    print("\n" + "="*70)
    print("=== INTEGRATION TEST: Discovery + Election + Handshake ===")
    print("="*70 + "\n")
    
    print("[TEST] Starting Master...")
    master_env = os.environ.copy()
    master_env["MASTER_NAME"] = "MASTER_1"
    master_env["MASTER_IP"] = "127.0.0.1"
    master_env["MASTER_TCP_PORT"] = "8888"
    master_env["DISCOVERY_PORT"] = "5000"
    
    master_proc = subprocess.Popen(
        ["python", "master.py"],
        env=master_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    await asyncio.sleep(2)  # Wait for Master startup
    
    print("\n[TEST] Starting Worker...")
    worker_env = os.environ.copy()
    worker_env["WORKER_UUID"] = "W-INTEGRATION-TEST"
    worker_env["DISCOVERY_TIMEOUT_S"] = "5"
    
    worker_proc = subprocess.Popen(
        ["python", "worker.py"],
        env=worker_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Let them run for 8 seconds
    print("\n[TEST] Waiting for worker to complete discovery and election phases...")
    await asyncio.sleep(8)
    
    try:
        print("\n[TEST] Collecting outputs...")
        worker_proc.terminate()
        master_proc.terminate()
        
        try:
            worker_stdout, _ = worker_proc.communicate(timeout=2)
            master_stdout, _ = master_proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            worker_proc.kill()
            master_proc.kill()
            worker_stdout = "KILLED"
            master_stdout = "KILLED"
        
        print("\n" + "="*70)
        print("WORKER OUTPUT:")
        print("="*70)
        print(worker_stdout[-2000:] if len(worker_stdout) > 2000 else worker_stdout)
        
        print("\n" + "="*70)
        print("MASTER OUTPUT:")
        print("="*70)
        print(master_stdout[-1000:] if len(master_stdout) > 1000 else master_stdout)
        
        # Check for key log markers
        print("\n" + "="*70)
        print("VERIFICATION:")
        print("="*70)
        
        checks = [
            ("DISCOVERY" in worker_stdout, "Worker shows DISCOVERY phase"),
            ("ELECTION" in worker_stdout, "Worker shows ELECTION phase"),
            ("CONNECTING" in worker_stdout, "Worker shows CONNECTING phase"),
            ("DISCOVERY_REPLY" in master_stdout, "Master responds to DISCOVERY"),
            ("ELECTION_ACK" in master_stdout, "Master handles ELECTION_ACK"),
        ]
        
        all_passed = True
        for check, description in checks:
            status = "✓" if check else "✗"
            print(f"{status} {description}")
            all_passed = all_passed and check
        
        print("="*70)
        if all_passed:
            print("\n✓ Full integration test PASSED!")
            return True
        else:
            print("\n✗ Some checks failed - see output above")
            return False
        
    except Exception as e:
        print(f"\n✗ Integration test ERROR: {e}")
        worker_proc.kill()
        master_proc.kill()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_full_discovery_election_flow())
    sys.exit(0 if result else 1)
