"""
Pytest configuration file.
"""

import os
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock

import pytest
from dotenv import load_dotenv

from follow_up_boss.client import FollowUpBossApiClient
from follow_up_boss.enhanced_client import ConnectionManager, RobustApiClient
from follow_up_boss.enhanced_people import EnhancedPeople
from follow_up_boss.pagination import PondFilterPaginator, SmartPaginator

# Load environment variables from .env file
load_dotenv()


@pytest.fixture(autouse=True)
def _block_live_follow_up_boss(monkeypatch):
    """Keep the test suite away from a real Follow Up Boss account.

    Some older tests call the real API (and even create deals). In a cloud
    environment that injects FUB credentials, that would write to live client
    data. Real network calls to followupboss.com fail unless
    FUB_ALLOW_LIVE_TESTS=1 is set deliberately. Mocked calls are unaffected.
    """
    if os.getenv("FUB_ALLOW_LIVE_TESTS") == "1":
        return
    import requests

    original = requests.sessions.Session.request

    def guarded(self, method, url, *args, **kwargs):
        if "followupboss.com" in str(url):
            raise RuntimeError(
                "Blocked a real Follow Up Boss API call from the test suite. "
                "Set FUB_ALLOW_LIVE_TESTS=1 only against a sandbox account."
            )
        return original(self, method, url, *args, **kwargs)

    monkeypatch.setattr(requests.sessions.Session, "request", guarded)


@pytest.fixture(scope="session")
def client():
    """Create a Follow Up Boss API client for testing with session scope."""
    api_key = os.getenv("FOLLOW_UP_BOSS_API_KEY")
    x_system = os.getenv("X_SYSTEM")
    x_system_key = os.getenv("X_SYSTEM_KEY")

    # Ensure required environment variables are present
    if not api_key:
        pytest.fail("FOLLOW_UP_BOSS_API_KEY environment variable is not set")

    if not x_system:
        pytest.fail("X_SYSTEM environment variable is not set")

    if not x_system_key:
        pytest.fail("X_SYSTEM_KEY environment variable is not set")

    return FollowUpBossApiClient(
        api_key=api_key, x_system=x_system, x_system_key=x_system_key
    )


@pytest.fixture(scope="session")
def robust_client():
    """Create a RobustApiClient for testing with session scope."""
    api_key = os.getenv("FOLLOW_UP_BOSS_API_KEY")
    x_system = os.getenv("X_SYSTEM")
    x_system_key = os.getenv("X_SYSTEM_KEY")

    # Skip if no API key is available (for unit tests)
    if not api_key:
        pytest.skip("FOLLOW_UP_BOSS_API_KEY environment variable is not set")

    return RobustApiClient(
        api_key=api_key, x_system=x_system, x_system_key=x_system_key
    )


@pytest.fixture
def enhanced_people(robust_client):
    """Create an EnhancedPeople instance for testing."""
    return EnhancedPeople(robust_client)


@pytest.fixture
def mock_client():
    """Create a mock API client for unit testing."""
    client = Mock(spec=FollowUpBossApiClient)

    # Configure common mock responses
    client._get.return_value = {
        "_metadata": {"collection": "people", "total": 100},
        "people": [
            {"id": 1, "name": "Test Person 1", "ponds": [{"id": 134}]},
            {"id": 2, "name": "Test Person 2", "ponds": [{"id": 134}]},
            {"id": 3, "name": "Test Person 3", "ponds": [{"id": 135}]},
        ],
    }

    return client


@pytest.fixture
def mock_robust_client():
    """Create a mock RobustApiClient for unit testing."""
    client = Mock(spec=RobustApiClient)

    # Configure common mock responses
    client._get.return_value = {
        "_metadata": {"collection": "people", "total": 100},
        "people": [
            {"id": 1, "name": "Test Person 1", "ponds": [{"id": 134}]},
            {"id": 2, "name": "Test Person 2", "ponds": [{"id": 134}]},
            {"id": 3, "name": "Test Person 3", "ponds": [{"id": 135}]},
        ],
    }

    # Mock session stats
    client.get_session_stats.return_value = {
        "request_count": 10,
        "error_count": 0,
        "session_timeout_count": 0,
        "error_rate": 0.0,
        "last_request_time": 1640995200.0,
    }

    return client


@pytest.fixture
def sample_people_data():
    """Sample people data for testing."""
    return [
        {
            "id": 1,
            "name": "John Doe",
            "firstName": "John",
            "lastName": "Doe",
            "emails": [{"value": "john@example.com", "type": "work"}],
            "phones": [{"value": "555-1234", "type": "mobile"}],
            "ponds": [{"id": 134, "name": "Test Pond"}],
            "created": "2023-01-01T00:00:00Z",
            "updated": "2023-01-02T00:00:00Z",
        },
        {
            "id": 2,
            "name": "Jane Smith",
            "firstName": "Jane",
            "lastName": "Smith",
            "emails": [{"value": "jane@example.com", "type": "personal"}],
            "phones": [{"value": "555-5678", "type": "home"}],
            "ponds": [{"id": 134, "name": "Test Pond"}],
            "created": "2023-01-03T00:00:00Z",
            "updated": "2023-01-04T00:00:00Z",
        },
        {
            "id": 3,
            "name": "Bob Johnson",
            "firstName": "Bob",
            "lastName": "Johnson",
            "emails": [{"value": "bob@example.com", "type": "work"}],
            "phones": [{"value": "555-9999", "type": "mobile"}],
            "ponds": [{"id": 135, "name": "Other Pond"}],
            "created": "2023-01-05T00:00:00Z",
            "updated": "2023-01-06T00:00:00Z",
        },
    ]


@pytest.fixture
def large_dataset_response() -> Any:
    """Mock response simulating a large dataset for pagination testing."""

    def generate_people(offset: int, limit: int) -> List[Dict[str, Any]]:
        """Generate mock people data for testing."""
        people = []
        for i in range(offset, min(offset + limit, 10000)):  # Simulate 10k total people
            people.append(
                {
                    "id": i + 1,
                    "name": f"Person {i + 1}",
                    "firstName": f"First{i + 1}",
                    "lastName": f"Last{i + 1}",
                    "emails": [{"value": f"person{i + 1}@example.com", "type": "work"}],
                    "ponds": (
                        [{"id": 134}] if i % 3 == 0 else [{"id": 135}]
                    ),  # Mix of ponds
                    "created": f"2023-01-{(i % 30) + 1:02d}T00:00:00Z",
                }
            )
        return people

    return generate_people


@pytest.fixture
def mock_paginated_responses():
    """Mock responses for testing deep pagination scenarios."""
    responses = []

    # First batch (offset 0-99)
    responses.append(
        {
            "_metadata": {
                "collection": "people",
                "total": 5000,
                "offset": 0,
                "limit": 100,
            },
            "people": [
                {"id": i, "name": f"Person {i}", "ponds": [{"id": 134}]}
                for i in range(1, 101)
            ],
        }
    )

    # Second batch (offset 100-199)
    responses.append(
        {
            "_metadata": {
                "collection": "people",
                "total": 5000,
                "offset": 100,
                "limit": 100,
            },
            "people": [
                {"id": i, "name": f"Person {i}", "ponds": [{"id": 134}]}
                for i in range(101, 201)
            ],
        }
    )

    # Batch near pagination limit (offset 1900-1999)
    responses.append(
        {
            "_metadata": {
                "collection": "people",
                "total": 5000,
                "offset": 1900,
                "limit": 100,
            },
            "people": [
                {"id": i, "name": f"Person {i}", "ponds": [{"id": 134}]}
                for i in range(1901, 2001)
            ],
        }
    )

    return responses


@pytest.fixture
def authentication_error_mock():
    """Mock authentication error for testing retry logic."""
    from follow_up_boss.enhanced_client import AuthenticationError

    return AuthenticationError("Access token has expired. Renew using refresh token")


@pytest.fixture
def deep_pagination_error_mock():
    """Mock deep pagination error for testing pagination strategy switching."""
    from follow_up_boss.client import FollowUpBossApiException

    return FollowUpBossApiException(
        "Deep pagination disabled, use 'nextLink' url", status_code=400
    )


@pytest.fixture(scope="function")
def temp_csv_file(tmp_path):
    """Create a temporary CSV file for export testing."""
    csv_file = tmp_path / "test_export.csv"
    return str(csv_file)


@pytest.fixture(scope="function")
def temp_json_file(tmp_path):
    """Create a temporary JSON file for export testing."""
    json_file = tmp_path / "test_export.json"
    return str(json_file)


# Pytest markers for different test categories
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: marks tests as unit tests (no API calls)")
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (requires API access)"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (may take a long time)"
    )
    config.addinivalue_line(
        "markers", "pagination: marks tests related to pagination functionality"
    )
    config.addinivalue_line(
        "markers", "enhanced: marks tests for enhanced functionality"
    )


@pytest.fixture(scope="function")
def resource_tracker(client):
    """Track created resources and clean them up after tests."""
    from follow_up_boss.appointments import Appointments
    from follow_up_boss.calls import Calls
    from follow_up_boss.deals import Deals
    from follow_up_boss.events import Events
    from follow_up_boss.notes import Notes
    from follow_up_boss.people import People
    from follow_up_boss.tasks import Tasks

    tracker = {
        "people": [],
        "deals": [],
        "tasks": [],
        "notes": [],
        "calls": [],
        "appointments": [],
        "events": [],
    }

    yield tracker

    # Cleanup in reverse order of dependencies
    # Events don't have delete endpoint, skip them

    # Clean up appointments
    if tracker["appointments"]:
        appointments_api = Appointments(client)
        for appointment_id in tracker["appointments"]:
            try:
                appointments_api.delete_appointment(appointment_id)
                print(f"Cleaned up appointment {appointment_id}")
            except Exception as e:
                print(f"Failed to cleanup appointment {appointment_id}: {e}")

    # Clean up calls
    if tracker["calls"]:
        calls_api = Calls(client)
        for call_id in tracker["calls"]:
            try:
                # Calls API might not have delete, check if it does
                if hasattr(calls_api, "delete_call"):
                    calls_api.delete_call(call_id)
                    print(f"Cleaned up call {call_id}")
            except Exception as e:
                print(f"Failed to cleanup call {call_id}: {e}")

    # Clean up notes
    if tracker["notes"]:
        notes_api = Notes(client)
        for note_id in tracker["notes"]:
            try:
                notes_api.delete_note(note_id)
                print(f"Cleaned up note {note_id}")
            except Exception as e:
                print(f"Failed to cleanup note {note_id}: {e}")

    # Clean up tasks
    if tracker["tasks"]:
        tasks_api = Tasks(client)
        for task_id in tracker["tasks"]:
            try:
                tasks_api.delete_task(task_id)
                print(f"Cleaned up task {task_id}")
            except Exception as e:
                print(f"Failed to cleanup task {task_id}: {e}")

    # Clean up deals
    if tracker["deals"]:
        deals_api = Deals(client)
        for deal_id in tracker["deals"]:
            try:
                deals_api.delete_deal(deal_id)
                print(f"Cleaned up deal {deal_id}")
            except Exception as e:
                print(f"Failed to cleanup deal {deal_id}: {e}")

    # Clean up people last (they might be referenced by other resources)
    if tracker["people"]:
        people_api = People(client)
        for person_id in tracker["people"]:
            try:
                people_api.delete_person(person_id)
                print(f"Cleaned up person {person_id}")
            except Exception as e:
                print(f"Failed to cleanup person {person_id}: {e}")


@pytest.fixture(autouse=True)
def cleanup_test_files():
    """Clean up any test files created during testing."""
    yield
    # Cleanup logic can be added here if needed
    import glob
    import os

    # Remove any test CSV/JSON files that might have been created
    for pattern in ["test_*.csv", "test_*.json", "*_test_*.csv", "*_test_*.json"]:
        for file in glob.glob(pattern):
            try:
                os.remove(file)
            except (OSError, FileNotFoundError):
                pass
