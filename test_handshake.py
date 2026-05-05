import json
from utils import ProtocolError, exigir_campos

def test_election_ack_payload():
    """Test ELECTION_ACK payload validation."""
    
    # Worker payload (send to Master)
    worker_ack = {
        "TYPE": "ELECTION_ACK",
        "WORKER_UUID": "W-101",
        "SELECTED_MASTER": "MASTER_1"
    }
    
    # Verify required fields
    exigir_campos(worker_ack, ["TYPE", "WORKER_UUID", "SELECTED_MASTER"])
    assert worker_ack["TYPE"] == "ELECTION_ACK"
    print(f"✓ Worker ELECTION_ACK valid: {json.dumps(worker_ack)}")
    
    # Master payload (send to Worker)
    master_ack = {
        "TYPE": "ELECTION_ACK",
        "STATUS": "ACCEPTED",
        "MASTER_NAME": "MASTER_1"
    }
    
    exigir_campos(master_ack, ["TYPE", "STATUS", "MASTER_NAME"])
    assert master_ack["STATUS"] == "ACCEPTED"
    print(f"✓ Master ELECTION_ACK valid: {json.dumps(master_ack)}")
    
    # Test strict parsing: missing SELECTED_MASTER should fail
    incomplete = {"TYPE": "ELECTION_ACK", "WORKER_UUID": "W-101"}
    try:
        exigir_campos(incomplete, ["TYPE", "WORKER_UUID", "SELECTED_MASTER"])
        assert False, "Should have raised ProtocolError"
    except ProtocolError as e:
        print(f"✓ Strict parsing caught missing field: {e}")

if __name__ == "__main__":
    test_election_ack_payload()
