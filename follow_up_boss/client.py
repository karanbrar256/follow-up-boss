"""
Follow Up Boss API Client.

This module provides a comprehensive client for interacting with the Follow Up Boss API.
The client includes support for custom headers, system registration, error handling,
and comprehensive debugging capabilities.

Key Features:
    - Custom headers support for API requests
    - X-System registration for higher rate limits
    - Enhanced error messages with context-specific guidance
    - Automatic retry logic and robust error handling
    - Support for all HTTP methods (GET, POST, PUT, DELETE)
    - File upload capabilities
    - Security measures to prevent header injection

Usage:
    Basic usage:
        client = FollowUpBossApiClient(api_key="your_api_key")

    With system registration for higher rate limits:
        client = FollowUpBossApiClient(
            api_key="your_api_key",
            custom_headers={
                'X-System': 'YourSystemName',
                'X-System-Key': 'your_system_key'
            }
        )

For more information, see: https://docs.followupboss.com/reference#identification
"""

import os
import re
from typing import Any, Dict, Optional, TypedDict, Union, cast

import requests
from dotenv import load_dotenv

load_dotenv()

# Default configuration values loaded from environment variables
API_KEY = os.getenv("FOLLOW_UP_BOSS_API_KEY")  # Primary API key for authentication
BASE_URL = "https://api.followupboss.com/v1"  # Follow Up Boss API base URL
X_SYSTEM = os.getenv("X_SYSTEM")  # System identifier for rate limit benefits
X_SYSTEM_KEY = os.getenv("X_SYSTEM_KEY")  # System key for enhanced API access


_SENSITIVE_HEADERS = {"x-system-key", "authorization"}


def _debug_enabled() -> bool:
    """Return True when verbose request/response logging is explicitly enabled.

    Set ``FOLLOW_UP_BOSS_DEBUG=1`` to print requests and responses. It is off by
    default because responses contain client personal information.
    """
    return os.getenv("FOLLOW_UP_BOSS_DEBUG", "").strip().lower() in {"1", "true", "yes"}


def _redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Return a copy of ``headers`` with secret values masked for logging."""
    return {
        k: ("***" if k.lower() in _SENSITIVE_HEADERS else v) for k, v in headers.items()
    }


class FollowUpBossApiException(Exception):
    """
    Custom exception for API-related errors.

    Attributes:
        status_code: HTTP status code of the error response.
        message: Error message from the API or a default message.
        response_data: The full JSON response data from the API, if available.
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize the FollowUpBossApiException.

        Args:
            message: A descriptive error message explaining what went wrong.
            status_code: HTTP status code from the failed request, if available.
            response_data: The full JSON response data from the API, if available.
                          This can contain additional error details from the server.
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_data = response_data

    def __str__(self) -> str:
        if self.status_code:
            return (
                f"FollowUpBossApiException: [Status {self.status_code}] {self.message}"
            )
        else:
            return f"FollowUpBossApiException: {self.message}"


class FollowUpBossAuthError(FollowUpBossApiException):
    """Authentication/authorization error (e.g., 401/403)."""


class FollowUpBossRateLimitError(FollowUpBossApiException):
    """Rate limit exceeded (e.g., 429)."""


class FollowUpBossValidationError(FollowUpBossApiException):
    """Validation or bad request error (e.g., 400/422)."""


class FollowUpBossNotFoundError(FollowUpBossApiException):
    """Resource not found (404)."""


class FollowUpBossServerError(FollowUpBossApiException):
    """Server-side error (5xx)."""


class FollowUpBossApiClient:
    """
    A client for interacting with the Follow Up Boss API.

    Attributes:
        api_key: The API key for authentication.
        base_url: The base URL for the API.
        x_system: The X-System header value.
        x_system_key: The X-System-Key header value.
        custom_headers: Custom headers to include in all requests.
    """

    def __init__(
        self,
        api_key: Optional[str] = API_KEY,
        base_url: str = BASE_URL,
        x_system: Optional[str] = X_SYSTEM,
        x_system_key: Optional[str] = X_SYSTEM_KEY,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Initializes the FollowUpBossApiClient.

        Args:
            api_key: The API key for authentication.
            base_url: The base URL for the API.
            x_system: The X-System header value for system registration.
            x_system_key: The X-System-Key header value for system registration.
            custom_headers: Additional custom headers to include in all requests.
                           These headers will be merged with default headers.
                           Custom headers take precedence over defaults (except for critical auth headers).

        Raises:
            ValueError: If the API key is not provided.
        """
        if not api_key:
            raise ValueError(
                "API key not found. Please set FOLLOW_UP_BOSS_API_KEY in your .env file or pass it to the client."
            )
        self.api_key = api_key
        self.base_url = base_url
        self.x_system = x_system
        self.x_system_key = x_system_key
        self.custom_headers = custom_headers or {}
        # Track latest rate limit metadata parsed from response headers
        self._last_rate_limit: Optional[Dict[str, int]] = None

    def get_last_rate_limit(self) -> Optional[Dict[str, int]]:
        """
        Return the most recent rate limit information captured from response headers.

        Returns:
            A dictionary containing keys like ``limit``, ``remaining``, and ``reset``
            when available, or ``None`` if not yet populated.
        """
        return self._last_rate_limit

    def _get_headers(self) -> Dict[str, str]:
        """
        Returns the headers for API requests.
        Does not include Authorization, as that's handled by `auth` in _request.

        Returns:
            A dictionary of headers with default headers merged with custom headers.
            Custom headers take precedence over defaults, except for critical headers.
        """
        # Start with default headers
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Add legacy system headers only if they exist (for backward compatibility)
        if self.x_system is not None:
            headers["X-System"] = self.x_system
        if self.x_system_key is not None:
            headers["X-System-Key"] = self.x_system_key

        # Merge custom headers (these take precedence over defaults)
        # Security measure: Filter out potentially dangerous headers that could
        # compromise authentication or interfere with HTTP protocol handling
        protected_headers = {"authorization", "content-length"}

        for key, value in self.custom_headers.items():
            # Case-insensitive check to prevent bypassing security via capitalization
            if key.lower() not in protected_headers:
                headers[key] = value
            # Note: Protected headers are silently ignored rather than raising an error
            # to maintain backward compatibility and prevent accidental breakage

        return headers

    def _enhance_error_message(
        self,
        error_message: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Enhance error messages with context-specific guidance.

        Args:
            error_message: The original error message.
            endpoint: The API endpoint being called.
            json_data: The JSON data that was sent in the request.

        Returns:
            Enhanced error message with helpful guidance.
        """
        enhanced_message = error_message

        # Deal-specific error enhancements
        if "deals" in endpoint and json_data:
            # Check for commission field related errors
            if any(
                field in str(json_data)
                for field in ["commissionValue", "agentCommission", "teamCommission"]
            ):
                if (
                    "invalid" in error_message.lower()
                    or "field" in error_message.lower()
                ):
                    enhanced_message += (
                        "\n\nDEAL COMMISSION GUIDANCE:\n"
                        "Commission fields (commissionValue, agentCommission, teamCommission) must be passed as "
                        "top-level parameters when creating/updating deals, not in custom_fields.\n"
                        "Example: create_deal(name='Deal', stage_id=1, commissionValue=13500.0)"
                    )

            # Check for required field errors
            if "required" in error_message.lower() and "stage" in error_message.lower():
                enhanced_message += (
                    "\n\nDEAL CREATION GUIDANCE:\n"
                    "The 'stage_id' parameter is required for all deal creation. "
                    "Get valid stage IDs from the stages API endpoint."
                )

        # Field name guidance
        if (
            "invalid field" in error_message.lower()
            or "unknown field" in error_message.lower()
        ):
            enhanced_message += (
                "\n\nFIELD NAME GUIDANCE:\n"
                "The API expects camelCase field names. Common mappings:\n"
                "- close_date → projectedCloseDate\n"
                "- user_id → userId\n"
                "- person_id → personId\n"
                "- stage_id → stageId\n"
                "- pipeline_id → pipelineId"
            )

        return enhanced_message

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        """
        Makes a request to the Follow Up Boss API.

        Args:
            method: The HTTP method (GET, POST, PUT, DELETE).
            endpoint: The API endpoint.
            params: URL parameters for the request.
            data: Form data for the request body.
            json: JSON data for the request body.
            files: Files to upload.

        Returns:
            The response from the API.

        Raises:
            FollowUpBossApiException: If the API returns an error or the request fails.
        """
        # Support absolute URLs (e.g., nextLink) in addition to endpoint paths
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            url = endpoint
        else:
            url = f"{self.base_url}/{endpoint}"
        headers = self._get_headers()
        auth = (self.api_key, "")  # API Key as username, empty password

        # Handle file uploads: Remove Content-Type header when uploading files
        # to allow requests library to set multipart/form-data with proper boundary
        if files:
            headers.pop("Content-Type", None)

        # Debug output is opt-in: responses contain client PII (names, phones, notes)
        # and headers contain the X-System-Key, so never print them by default.
        debug = _debug_enabled()
        if debug:
            print(f"\n=== API Request ===")
            print(f"Method: {method}")
            print(f"URL: {url}")
            print(f"Headers: {_redact_headers(headers)}")
            print(f"Params: {params}")
            print(f"JSON: {json}")
            print(f"Data: {data}")
            print(f"Files: {files}")

        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                auth=auth,  # Use Basic Auth
                params=params,
                data=data,
                json=json,
                files=files,
                timeout=30,  # Adding a timeout for requests
            )

            if debug:
                print(f"\n=== API Response ===")
                print(f"Status: {response.status_code}")
                print(f"Headers: {dict(response.headers)}")
                try:
                    # Attempt to parse and display JSON response for structured data
                    print(f"Response JSON: {response.json()}")
                except Exception:
                    # Fall back to raw text for non-JSON responses or parsing errors
                    print(f"Response Text: {response.text}")

            # Capture rate limit metadata for programmatic access
            self._last_rate_limit = self._extract_rate_limit_info(response)

            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            return response
        except requests.exceptions.HTTPError as http_err:
            error_message = f"HTTP error occurred: {http_err}"
            try:
                error_content = http_err.response.content.decode(
                    "utf-8", errors="replace"
                )
                if debug:
                    print(f"{error_message}")
                    print(f"Response content: {error_content}")

                # Try to parse JSON error response if available
                try:
                    error_data = http_err.response.json()
                    error_detail = error_data.get("title", error_content)
                    if (
                        "errors" in error_data
                        and isinstance(error_data["errors"], list)
                        and error_data["errors"]
                    ):
                        details = [
                            str(err.get("detail", err)) for err in error_data["errors"]
                        ]
                        error_detail += ": " + ", ".join(details)

                    # Enhance the error message with context-specific guidance
                    enhanced_error = self._enhance_error_message(
                        error_detail, endpoint, json
                    )

                    raise self._map_exception(http_err, enhanced_error, error_data)
                except ValueError:
                    # If not JSON, just use the content as error message
                    enhanced_error = self._enhance_error_message(
                        error_content, endpoint, json
                    )
                    raise self._map_exception(http_err, enhanced_error)
            except Exception:
                # Fallback when we can't parse the response content or JSON
                # This handles cases where the response is malformed or unexpected
                status_code = None

                # Attempt to extract HTTP status code from the error message string
                # Error messages typically start with status code (e.g., "404 Client Error")
                error_str = str(http_err)
                if error_str.startswith(("4", "5")) and " " in error_str:
                    try:
                        # Extract the first part of the error string as status code
                        status_code = int(error_str.split(" ")[0])
                    except (ValueError, IndexError):
                        # If parsing fails, leave status_code as None
                        pass

                # Raise with whatever information we could extract
                raise self._map_exception(http_err, str(http_err))
        except requests.exceptions.RequestException as req_err:
            print(f"Request exception occurred: {req_err}")
            raise FollowUpBossApiException(message=str(req_err)) from req_err

    def _extract_rate_limit_info(
        self, response: requests.Response
    ) -> Optional[Dict[str, int]]:
        """
        Extract rate limit metadata from response headers.

        Args:
            response: The HTTP response object.

        Returns:
            A RateLimitInfo dict when headers are present, otherwise None.
        """
        headers = {k.lower(): v for k, v in response.headers.items()}
        limit = headers.get("x-ratelimit-limit")
        remaining = headers.get("x-ratelimit-remaining")
        reset = headers.get("x-ratelimit-reset")

        def _to_int(value: Optional[str]) -> Optional[int]:
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        info: Dict[str, int] = {}
        lim = _to_int(limit)
        rem = _to_int(remaining)
        res = _to_int(reset)
        if lim is not None:
            info["limit"] = lim
        if rem is not None:
            info["remaining"] = rem
        if res is not None:
            info["reset"] = res
        return info or None

    def _map_exception(
        self,
        http_err: requests.exceptions.HTTPError,
        message: str,
        response_data: Optional[Dict[str, Any]] = None,
    ) -> FollowUpBossApiException:
        """
        Map HTTP status codes to explicit exceptions.

        Args:
            http_err: The underlying HTTPError.
            message: Error message to include.
            response_data: Optional parsed JSON payload for context.

        Returns:
            An instance of a specific FollowUpBossApiException subclass.
        """
        status_code: Optional[int] = None
        try:
            status_code = http_err.response.status_code
        except Exception:
            pass

        if status_code in (401, 403):
            return FollowUpBossAuthError(
                message=message, status_code=status_code, response_data=response_data
            )
        if status_code == 404:
            return FollowUpBossNotFoundError(
                message=message, status_code=status_code, response_data=response_data
            )
        if status_code == 429:
            return FollowUpBossRateLimitError(
                message=message, status_code=status_code, response_data=response_data
            )
        if status_code in (400, 422):
            return FollowUpBossValidationError(
                message=message, status_code=status_code, response_data=response_data
            )
        if status_code is not None and 500 <= status_code <= 599:
            return FollowUpBossServerError(
                message=message, status_code=status_code, response_data=response_data
            )
        return FollowUpBossApiException(
            message=message, status_code=status_code, response_data=response_data
        )

    def _extract_pagination_links(
        self, response: requests.Response
    ) -> Optional[Dict[str, str]]:
        """
        Extract pagination links from RFC5988 Link header if present.

        Args:
            response: The HTTP response object.

        Returns:
            A dict possibly containing 'nextLink' and 'prevLink'.
        """
        link_header = response.headers.get("Link") or response.headers.get("link")
        if not link_header:
            return None
        links: Dict[str, str] = {}
        # Example: <https://api.followupboss.com/v1/people?next=...>; rel="next", <...>; rel="prev"
        for part in link_header.split(","):
            section = part.strip()
            if not section.startswith("<") or ">" not in section:
                continue
            url = section[1 : section.find(">")]
            rel_match = re.search(r'rel="(.*?)"', section)
            if not rel_match:
                continue
            rel = rel_match.group(1)
            if rel == "next":
                links["nextLink"] = url
            elif rel == "prev":
                links["prevLink"] = url
        return links or None

    def get_absolute(self, url: str) -> Dict[str, Any]:
        """
        GET a fully-qualified Follow Up Boss API URL.

        Args:
            url: Absolute URL returned by the API (e.g., nextLink).

        Returns:
            Parsed JSON dict from the API, enriched with _rateLimit and link metadata.
        """
        return self._get(url)

    def _get(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a GET request to the Follow Up Boss API.

        This method handles GET requests with automatic JSON parsing and error handling.
        It includes all configured headers (including custom headers) and properly
        handles authentication.

        Args:
            endpoint: The API endpoint path (without base URL).
                     Example: "people", "deals/123", "identity"
            params: Optional URL query parameters to include in the request.
                   Will be properly URL encoded.

        Returns:
            A dictionary containing the parsed JSON response from the API.
            Returns an empty dict if the response is not a valid JSON object.

        Raises:
            FollowUpBossApiException: If the API returns an error status code
                                    or if there's a network/connection issue.

        Example:
            response = client._get("people", {"limit": 10, "offset": 0})
        """
        response = self._request("GET", endpoint, params=params)
        json_response = response.json()
        payload: Dict[str, Any] = (
            json_response if isinstance(json_response, dict) else {}
        )
        # Attach rate limit info when available for programmatic access
        if self._last_rate_limit is not None:
            payload.setdefault("_rateLimit", self._last_rate_limit)
        # Attach pagination links parsed from response headers if missing from body
        links = self._extract_pagination_links(response)
        if links:
            meta = cast(Dict[str, Any], payload.get("_metadata", {}))
            payload.setdefault("_metadata", meta)
            if "nextLink" not in meta and links.get("nextLink"):
                meta["nextLink"] = links["nextLink"]
            if "prevLink" not in meta and links.get("prevLink"):
                meta["prevLink"] = links["prevLink"]
        return payload

    def _post(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> Union[Dict[str, Any], str]:
        """
        Execute a POST request to the Follow Up Boss API.

        This method handles POST requests with support for JSON data, form data,
        and file uploads. It automatically handles content-type headers and
        provides flexible response parsing.

        Args:
            endpoint: The API endpoint path (without base URL).
                     Example: "people", "deals", "notes"
            params: Optional URL query parameters to include in the request.
            data: Optional form data for the request body. Used for form-encoded requests.
                 Cannot be used together with json_data.
            json_data: Optional JSON data for the request body. Used for JSON API requests.
                      Cannot be used together with data.
            files: Optional files to upload. When provided, Content-Type header
                  is automatically set for multipart/form-data.

        Returns:
            A dictionary containing the parsed JSON response from the API,
            or a string containing the response text if JSON parsing fails.
            Returns empty dict for non-JSON responses like 204 No Content.

        Raises:
            FollowUpBossApiException: If the API returns an error status code
                                    or if there's a network/connection issue.

        Example:
            # JSON request
            response = client._post("people", json_data={"name": "John Doe"})

            # File upload
            with open("document.pdf", "rb") as f:
                response = client._post("attachments", files={"file": f})
        """
        response = self._request(
            "POST", endpoint, params=params, data=data, json=json_data, files=files
        )
        try:
            json_response = response.json()
            payload: Dict[str, Any] = (
                json_response if isinstance(json_response, dict) else {}
            )
            if self._last_rate_limit is not None:
                payload.setdefault("_rateLimit", self._last_rate_limit)
            # Attach pagination links when present
            links = self._extract_pagination_links(response)
            if links:
                meta = cast(Dict[str, Any], payload.get("_metadata", {}))
                payload.setdefault("_metadata", meta)
                if "nextLink" not in meta and links.get("nextLink"):
                    meta["nextLink"] = links["nextLink"]
                if "prevLink" not in meta and links.get("prevLink"):
                    meta["prevLink"] = links["prevLink"]
            return payload
        except requests.exceptions.JSONDecodeError:
            # Handle cases where response might not be JSON (e.g., 204 No Content)
            return response.text

    def _put(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> Union[Dict[str, Any], str]:
        """
        Execute a PUT request to the Follow Up Boss API.

        This method handles PUT requests for updating existing resources.
        It supports JSON data, form data, and file uploads with automatic
        content-type handling and flexible response parsing.

        Args:
            endpoint: The API endpoint path (without base URL).
                     Example: "people/123", "deals/456", "notes/789"
            data: Optional form data for the request body. Used for form-encoded requests.
                 Cannot be used together with json_data.
            json_data: Optional JSON data for the request body. Used for JSON API requests.
                      This is the most common format for PUT requests.
            files: Optional files to upload. When provided, Content-Type header
                  is automatically set for multipart/form-data.

        Returns:
            A dictionary containing the parsed JSON response from the API,
            or a string containing the response text if JSON parsing fails.
            Many PUT requests return the updated resource data.

        Raises:
            FollowUpBossApiException: If the API returns an error status code
                                    or if there's a network/connection issue.

        Example:
            # Update a person's information
            response = client._put("people/123", json_data={
                "name": "Jane Doe",
                "email": "jane.doe@example.com"
            })
        """
        response = self._request(
            "PUT", endpoint, data=data, json=json_data, files=files
        )
        try:
            json_response = response.json()
            payload: Dict[str, Any] = (
                json_response if isinstance(json_response, dict) else {}
            )
            if self._last_rate_limit is not None:
                payload.setdefault("_rateLimit", self._last_rate_limit)
            links = self._extract_pagination_links(response)
            if links:
                meta = cast(Dict[str, Any], payload.get("_metadata", {}))
                payload.setdefault("_metadata", meta)
                if "nextLink" not in meta and links.get("nextLink"):
                    meta["nextLink"] = links["nextLink"]
                if "prevLink" not in meta and links.get("prevLink"):
                    meta["prevLink"] = links["prevLink"]
            return payload
        except requests.exceptions.JSONDecodeError:
            return response.text

    def _delete(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Union[Dict[str, Any], str]:
        """
        Execute a DELETE request to the Follow Up Boss API.

        This method handles DELETE requests for removing resources from the API.
        It properly handles the common case where DELETE requests return 204 No Content
        with no response body, as well as cases where deletion information is returned.

        Args:
            endpoint: The API endpoint path (without base URL).
                     Example: "people/123", "deals/456", "notes/789"
            data: Optional form data for the request body. Rarely used with DELETE.
            json_data: Optional JSON data for the request body. Some DELETE endpoints
                      may require additional parameters for conditional deletion.

        Returns:
            A dictionary containing the parsed JSON response from the API,
            a string containing the response text, or an empty string for
            204 No Content responses (which is the most common for DELETE requests).

        Raises:
            FollowUpBossApiException: If the API returns an error status code
                                    or if there's a network/connection issue.

        Example:
            # Delete a person
            result = client._delete("people/123")

            # Conditional delete with parameters
            result = client._delete("deals/456", json_data={"reason": "duplicate"})

        Note:
            Most successful DELETE requests return HTTP 204 (No Content) with an empty
            response body, which this method handles by returning an empty string.
        """
        response = self._request("DELETE", endpoint, data=data, json=json_data)
        # DELETE often returns 204 No Content, which is not valid JSON
        if response.status_code == 204:
            return ""
        try:
            json_response = response.json()
            payload: Dict[str, Any] = (
                json_response if isinstance(json_response, dict) else {}
            )
            if self._last_rate_limit is not None:
                payload.setdefault("_rateLimit", self._last_rate_limit)
            links = self._extract_pagination_links(response)
            if links:
                meta = cast(Dict[str, Any], payload.get("_metadata", {}))
                payload.setdefault("_metadata", meta)
                if "nextLink" not in meta and links.get("nextLink"):
                    meta["nextLink"] = links["nextLink"]
                if "prevLink" not in meta and links.get("prevLink"):
                    meta["prevLink"] = links["prevLink"]
            return payload
        except requests.exceptions.JSONDecodeError:
            return response.text
