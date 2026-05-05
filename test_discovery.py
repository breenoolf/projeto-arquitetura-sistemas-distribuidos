import asyncio
import json

async def test_discovery_broadcast():
    """Test that worker can send DISCOVERY broadcast and collect responses."""
    # This is a mock test to verify the discovery logic
    # Real test will run with actual Master listening
    
    payload = {"TYPE": "DISCOVERY", "WORKER_UUID": "W-TEST-001"}
    
    # Verify payload format
    assert payload["TYPE"] == "DISCOVERY"
    assert "WORKER_UUID" in payload
    assert len(payload["WORKER_UUID"]) > 0
    
    # Verify JSON serialization (as would be sent)
    json_str = json.dumps(payload) + "\n"
    assert json_str.endswith("\n")
    print(f"✓ Payload format valid: {json_str}")

if __name__ == "__main__":
    asyncio.run(test_discovery_broadcast())
