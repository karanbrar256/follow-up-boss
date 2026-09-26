# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `fub_toolkit`: daily lead follow-up prototype (urgency ranking, overdue tasks, note summaries, buyer-criteria extraction, call list, next-action recommendations) with mock data, CLI (`python -m fub_toolkit` / `fub-daily`) and docs in `docs/FUB_TOOLKIT.md`.
- Read-only FUB client wrapper that blocks POST/PUT/DELETE; live access requires `FUB_TOOLKIT_ALLOW_LIVE=1`.

### Security
- `FollowUpBossApiClient` no longer prints request/response bodies and headers by default (they contain client PII and the `X-System-Key`). Opt in with `FOLLOW_UP_BOSS_DEBUG=1`; the key is masked.

## [0.4.0] - 2024-10-30

### Fixed
- **100% Test Pass Rate**: Fixed all 24 failing unit tests to achieve complete test coverage
- Enhanced API key validation in `RobustApiClient` with explicit error handling
- Improved error propagation in emergency pond filtering methods
- Fixed `_person_in_pond` method to handle invalid data types gracefully
- Updated test mocking to match refactored implementations
- Fixed webhook payload type validation to handle non-dictionary inputs

### Changed
- Updated `last_extraction` initialization to `None` instead of empty string
- Improved `SmartPaginator` to handle Mock objects in strategy classes
- Enhanced error handling with proper exception propagation
- Updated pond extraction methods to use emergency local filtering consistently

### Testing
- All 181 unit tests now passing (100% pass rate)
- Fixed complex pagination strategy mocking scenarios
- Updated verification tests to match emergency mode implementation
- Improved test reliability and maintainability

## [0.3.0] - 2024-10-30

### Added

#### Action Plans Enhancements
- `pause_action_plan(assignment_id, reason=None)`: Convenience method to pause an action plan assignment with optional reason
- `resume_action_plan(assignment_id)`: Convenience method to resume a paused action plan assignment
- `pause_all_for_person(person_id, reason=None, only_active=True)`: Batch pause all action plans for a specific person

#### People Enhancements
- `find_person_id(email=None, phone=None)`: Search for a person by email or phone and return their ID
- `assign_to_user(person_id, user_id)`: Convenience method to assign a person to a user
- `get_person_created_at(person_id)`: Get the creation timestamp for a person with robust format handling
- `_parse_timestamp(value)`: Internal utility to parse various timestamp formats from Follow Up Boss API
- Enhanced `add_tags()` method with `skip_if_created_within` parameter to prevent tagging newly created leads within a specified time window

#### Users Enhancements
- `find_user_by_email(email)`: Search for a user by their email address
- `get_user_id_by_email(email)`: Convenience method to get a user's ID by their email address

#### Webhook Utilities Module
- New `webhook_utils.py` module with comprehensive webhook payload parsing utilities
- `extract_person_id_from_payload(payload, client=None)`: Extract person ID from various webhook payload formats
- `get_event_name(payload)`: Extract the event name from a webhook payload
- `get_resource_by_collection(client, collection, resource_id)`: Fetch resources by collection name

### Changed
- Updated version to 0.3.0
- Enhanced `add_tags()` in People class with optional creation time guard parameter
- Improved timestamp parsing to handle ISO8601, Unix epoch, and nested object formats

### Fixed
- Robust timestamp parsing handles various Follow Up Boss API response formats
- Better error handling in webhook payload parsing

### Testing
- Added comprehensive unit tests for all new features:
  - `test_action_plans_enhancements.py`: 8 tests covering pause/resume functionality
  - `test_people_enhancements.py`: 20 tests covering search, assignment, and timestamp parsing
  - `test_users_enhancements.py`: 9 tests covering user search functionality
  - `test_webhook_utils.py`: 18 tests covering webhook payload parsing

## [0.2.10] - Previous Release

- Previous features and functionality

