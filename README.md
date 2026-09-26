# Follow Up Boss API Client

A comprehensive Python client library for the Follow Up Boss API, providing easy access to all Follow Up Boss endpoints with full type safety and thorough documentation.

## Features

- **Complete API Coverage**: Support for all Follow Up Boss API endpoints
- **Type Safety**: Full type hints throughout the library
- **Easy to Use**: Simple, intuitive interface
- **Well Documented**: Comprehensive docstrings and examples
- **Async Support**: Built with modern Python async/await patterns
- **Error Handling**: Robust error handling and validation
- **Extensible**: Easy to extend for custom use cases

## Daily Lead Follow-Up Toolkit (prototype)

`fub_toolkit` turns FUB data into a ranked morning call sheet: who to call first, overdue tasks, recent-note summaries, extracted buyer criteria and a recommended next action for each lead. It runs on mock data by default; live access is read-only and opt-in.

```bash
python -m fub_toolkit daily
```

See [docs/FUB_TOOLKIT.md](docs/FUB_TOOLKIT.md) for usage and the checklist to complete before connecting a live account.

## Installation

```bash
pip install follow-up-boss
```

## Quick Start

```python
from follow_up_boss import FollowUpBossApiClient

# Initialize the client
client = FollowUpBossApiClient(
    api_key="your_api_key",
    x_system="Your-System-Name",
    x_system_key="your_system_key"
)

# Get all people
people = client.people.get_all()

# Create a new person
new_person = client.people.create({
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "555-123-4567"
})

# Update a person
updated_person = client.people.update(person_id, {
    "name": "John Smith"
})

# Add tags to a person (merge with existing, de-duplicated)
from follow_up_boss.people import People
people_api = People(client)
people_api.add_tags(person_id, ["Zillow: Note Logged"])  # merge=True by default

# Replace tags entirely
people_api.add_tags(person_id, ["Only These"], merge=False)

# Delete a person
client.people.delete(person_id)
```

## Environment Variables

Set `FOLLOW_UP_BOSS_DEBUG=1` to print requests and responses while troubleshooting. It is off by default because responses contain client personal information; the `X-System-Key` header is masked either way.

You can also configure the client using environment variables:

```bash
FOLLOW_UP_BOSS_API_KEY=your_api_key
X_SYSTEM=Your-System-Name
X_SYSTEM_KEY=your_system_key
```

```python
from follow_up_boss import FollowUpBossApiClient

# Client will automatically use environment variables
client = FollowUpBossApiClient()
```

## API Resources

The client provides access to all Follow Up Boss API resources:

### Core Resources
- **People**: Manage contacts and leads
- **Deals**: Track real estate transactions ([Commission Field Guide](DEALS_COMMISSION_GUIDE.md))
- **Events**: Handle activities and interactions
- **Tasks**: Manage todo items and follow-ups
- **Notes**: Add and retrieve notes
- **Appointments**: Schedule and manage appointments

### Communication
- **Text Messages**: Send and receive SMS
- **Email Templates**: Manage email templates
- **Text Message Templates**: Manage SMS templates
- **Webhooks**: Configure webhook endpoints
- **Reactions**: Handle message reactions

### Organization
- **Teams**: Manage team structures
- **Users**: Handle user accounts
- **Groups**: Organize contacts into groups
- **Pipelines**: Manage sales pipelines
- **Stages**: Configure pipeline stages
- **Smart Lists**: Dynamic contact lists

### Configuration
- **Custom Fields**: Define custom data fields
- **Action Plans**: Automated workflow templates
- **Appointment Types**: Configure appointment categories
- **Appointment Outcomes**: Track appointment results

### Attachments & Files
- **Person Attachments**: File attachments for contacts
- **Deal Attachments**: File attachments for deals

## Deals API - Commission Fields

The Deals API includes special handling for commission fields. **Important**: Commission fields must be passed as top-level parameters, not in `custom_fields`.

```python
from follow_up_boss import Deals, DealsValidationError

deals_api = Deals(client)

# ✅ Correct - Commission fields as top-level parameters
deal = deals_api.create_deal(
    name="123 Main Street",
    stage_id=26,
    price=450000,
    commissionValue=13500.0,
    agentCommission=9450.0,
    teamCommission=4050.0
)

# ❌ Incorrect - This will raise DealsValidationError
try:
    deal = deals_api.create_deal(
        name="Deal Name",
        stage_id=26,
        custom_fields={'commissionValue': 13500}  # This fails
    )
except DealsValidationError as e:
    print(f"Validation error: {e}")
```

### Commission Helper Methods

```python
# Set commission using helper method
commission_data = {
    'total': 15000.0,
    'agent': 10500.0,
    'team': 4500.0
}

updated_deal = deals_api.set_deal_commission(deal_id, commission_data)
```

For complete commission field documentation, see the [Commission Field Guide](DEALS_COMMISSION_GUIDE.md).

## Advanced Usage

### Error Handling

```python
from follow_up_boss import FollowUpBossApiClient
from follow_up_boss.exceptions import ApiError, AuthenticationError

try:
    client = FollowUpBossApiClient(api_key="invalid_key")
    people = client.people.get_all()
except AuthenticationError:
    print("Invalid API credentials")
except ApiError as e:
    print(f"API Error: {e}")
```

### Pagination

```python
# Get all people with pagination
all_people = []
page = 1

while True:
    response = client.people.get_all(page=page, limit=100)
    people = response.get('people', [])
    
    if not people:
        break
        
    all_people.extend(people)
    page += 1
```

### Get people in a Follow Up Boss list

```python
from follow_up_boss import FollowUpBossApiClient
from follow_up_boss.people import People

client = FollowUpBossApiClient(
    api_key="your_api_key",
    x_system="Your-System-Name",
    x_system_key="your_system_key",
)

people_api = People(client)

# Single page filtered by Smart List ID
page = people_api.list_people_by_list_id(154, limit=50)

# Fetch all pages (follows _metadata.next)
all_people = people_api.fetch_all_people_by_list_id(154, limit=100)
```

Note: Cursor pagination uses the `_metadata.next` token returned by the API.

### Iterate all people with automatic pagination

The `People.iter_people()` helper yields people across all pages. It prefers cursor-based pagination via `_metadata.next` when available (e.g., when using `listId`) and automatically falls back to offset-based pagination.

```python
from follow_up_boss.people import People

people_api = People(client)

# Iterate with a saved list filter (cursor-based)
for person in people_api.iter_people({"listId": 154, "limit": 200}):
    print(person.get("id"))

# Iterate with offset-based pagination (no cursor)
for person in people_api.iter_people({"limit": 100, "offset": 0, "stage": "New"}):
    process(person)
```

### Using nextLink for deep pagination

The client supports absolute-URL traversal via `_metadata.nextLink` to avoid deep pagination errors:

```python
first = people_api.list_people({"listId": 154, "limit": 200})
meta = first.get("_metadata", {})
next_link = meta.get("nextLink")

while next_link:
    page = people_api.list_people_next(next_link)
    for person in page.get("people", []):
        process(person)
    next_link = page.get("_metadata", {}).get("nextLink")
```

### Consistent list_people shape

`People.list_people(params)` always returns a dictionary that includes at least:

```python
{"people": [...], "count": int}
```

This provides a stable structure for downstream clients even when the API omits certain fields.

### Rate limit metadata and explicit exceptions

The client exposes rate limit headers parsed from responses:

```python
from follow_up_boss import FollowUpBossApiClient

client = FollowUpBossApiClient(api_key="...", x_system="...", x_system_key="...")
resp = client._get("people", params={"limit": 1})
print(resp.get("_rateLimit"))  # {'limit': 120, 'remaining': 119, 'reset': 1710000000}

# Or access the last seen info directly
print(client.get_last_rate_limit())
```

Explicit exceptions simplify handling and retries:

```python
from follow_up_boss import (
    FollowUpBossApiClient,
    FollowUpBossAuthError,
    FollowUpBossRateLimitError,
    FollowUpBossValidationError,
)

client = FollowUpBossApiClient(api_key="...")
try:
    client._get("people", {"limit": 1})
except FollowUpBossRateLimitError as e:
    # backoff/retry using e.status_code and rate limit info
    pass
except FollowUpBossAuthError as e:
    # refresh credentials
    pass
except FollowUpBossValidationError as e:
    # fix request
    pass
```

### Custom Headers

```python
# Add custom headers to requests
client = FollowUpBossApiClient(
    api_key="your_key",
    custom_headers={
        "X-Custom-Header": "custom_value"
    }
)
```

## Development

### Setup

```bash
git clone https://github.com/theperrygroup/follow-up-boss.git
cd follow-up-boss
pip install -e ".[dev]"
```

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black follow_up_boss tests
isort follow_up_boss tests
```

### Type Checking

```bash
mypy follow_up_boss
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for your changes
5. Ensure all tests pass (`pytest`)
6. Format your code (`black` and `isort`)
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For questions, issues, or feature requests, please:

1. Check the [documentation](https://github.com/theperrygroup/follow-up-boss#readme)
2. Search [existing issues](https://github.com/theperrygroup/follow-up-boss/issues)
3. Create a [new issue](https://github.com/theperrygroup/follow-up-boss/issues/new) if needed

## Changelog

### Version 0.2.0
- **Major Commission Field Improvements**: Added comprehensive commission field handling with validation
- **Enhanced Error Messages**: Context-specific error guidance for common mistakes
- **New Validation System**: `DealsValidationError` for deals-specific validation
- **Commission Helper Methods**: `set_deal_commission()` for easier commission management
- **Field Name Normalization**: Consistent field naming between requests and responses
- **Comprehensive Documentation**: New commission field guide with examples and troubleshooting
- **Enhanced Testing**: Complete test coverage for all commission field scenarios
- **Improved Developer Experience**: Better error messages, helper properties, and validation

### Version 0.2.6
- **People.add_tags helper**: Official method to append/replace tags using PUT /people/{id}
  - Merge behavior with de-duplication and optional case-insensitive matching
  - Avoids unsupported POST /people/{id}/tags endpoint (404)
- **Docs**: README examples updated for tag operations
- **Tooling**: Formatting and type checks updated

### Version 0.2.7
- **People**: Added `list_people_by_list_id` and `fetch_all_people_by_list_id` supporting cursor pagination via `_metadata.next`.

### Version 0.2.8
- **People**: Added `iter_people(params)` iterator (cursor-first, offset fallback).
- **People**: `list_people(params)` now guarantees a consistent shape: `{"people": [...], "count": int}`.
- **Typing**: Introduced `ListPeopleParams`, `Person`, and `PeopleListResponse` TypedDicts.

### Version 0.2.9
- **Client**: Added explicit exception subclasses for auth, rate limit, validation, not-found, and server errors.
- **Client**: Expose `_rateLimit` metadata on responses and `get_last_rate_limit()`.

### Version 0.2.10
- **Client**: Parse RFC5988 Link headers and surface `_metadata.nextLink`/`_metadata.prevLink`.
- **Client**: Support absolute URL GET via `get_absolute(url)` and auto-detect absolute endpoints.
- **People**: `iter_people` prefers `nextLink`, falls back to `next` token or offset.
- **People**: `list_people_next(next_link)` helper to fetch subsequent pages.

### Version 0.1.2
- Removed appointment test log file logging

### Version 0.1.1
- Updated website URL to https://theperry.group

### Version 0.1.0
- Initial release
- Complete API coverage for all Follow Up Boss endpoints
- Full type safety with comprehensive type hints
- Comprehensive test suite
- Documentation and examples

## Related Projects

- [Follow Up Boss API Documentation](https://followupboss.com/api/)
- [Follow Up Boss](https://followupboss.com/) - The official Follow Up Boss platform

---

Made with ❤️ by [The Perry Group](https://theperry.group) 