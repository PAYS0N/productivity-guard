"""Canonical test configuration dict used across all test modules.

Must match the schema of config.example.yaml exactly, since main.py accesses
keys without defaults in several places.
"""

FAKE_CONFIG = {
    "api": {
        "host": "127.0.0.1",
        "port": 8800,
    },
    "anthropic": {
        "api_key": "test-fake-key-not-real",
        "model": "claude-test-model",
        "max_tokens": 100,
        "temperature": 0.0,
    },
    "homeassistant": {
        "url": "http://ha.test:8123",
        "token": "fake-ha-token",
    },
    "dnsmasq": {
        "blocked_hosts_path": "/tmp/test_blocked_hosts",
    },
    "domains": {
        # Both bare and www variants — important for domain_to_conditional tests
        "conditional": ["reddit.com", "www.reddit.com", "youtube.com"],
        # twitter.com is always-blocked — used to test the lstrip bug
        "always_blocked": ["twitter.com"],
    },
    "devices": {
        "192.168.1.100": {
            "name": "test-laptop",
            "type": "laptop",
            "bermuda_entity": "sensor.test_laptop_ble_room",
        },
        "192.168.1.101": {
            "name": "test-phone",
            "type": "phone",
            # No bermuda_entity — tests the "no entity" path
        },
    },
    "database": {
        # Use a real file path — main.py passes this to Database()
        # For test_database.py we construct Database(":memory:") directly
        "path": "/tmp/test_productivity_guard.db",
    },
}
