def test_election_lexicographic():
    """Test deterministic lexicographic election."""
    from worker import election_phase
    
    # Mock discovered masters
    discovered = [
        {"MASTER_NAME": "MASTER_3", "MASTER_IP": "192.168.1.30", "MASTER_PORT": 8888},
        {"MASTER_NAME": "MASTER_1", "MASTER_IP": "192.168.1.10", "MASTER_PORT": 8888},
        {"MASTER_NAME": "MASTER_10", "MASTER_IP": "192.168.1.100", "MASTER_PORT": 8888},
        {"MASTER_NAME": "MASTER_2", "MASTER_IP": "192.168.1.20", "MASTER_PORT": 8888},
    ]
    
    elected = election_phase(discovered)
    
    assert elected["MASTER_NAME"] == "MASTER_1", f"Expected MASTER_1, got {elected['MASTER_NAME']}"
    print(f"✓ Elected: {elected['MASTER_NAME']}")
    
    # Test edge case: MASTER_10 should come before MASTER_2 (lexicographic string sort)
    discovered2 = [
        {"MASTER_NAME": "MASTER_10", "MASTER_IP": "192.168.1.100", "MASTER_PORT": 8888},
        {"MASTER_NAME": "MASTER_2", "MASTER_IP": "192.168.1.20", "MASTER_PORT": 8888},
    ]
    
    elected2 = election_phase(discovered2)
    assert elected2["MASTER_NAME"] == "MASTER_10", f"Expected MASTER_10 (lexicographic < MASTER_2), got {elected2['MASTER_NAME']}"
    print(f"✓ Edge case (MASTER_10 < MASTER_2): {elected2['MASTER_NAME']}")

if __name__ == "__main__":
    test_election_lexicographic()
