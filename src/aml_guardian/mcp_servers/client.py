"""Common MCP client with timeout and error handling."""

import hashlib
import json
import time
from typing import Any

from aml_guardian.audit.chain import add_event
from aml_guardian.contracts.runtime import Role


class MCPError(Exception):
    """Error from MCP server with error code and retryability."""

    def __init__(self, error_code: str, message: str, retryable: bool = False):
        """Initialize MCP error."""
        self.error_code = error_code
        self.message = message
        self.retryable = retryable
        super().__init__(f"{error_code}: {message} (retryable={retryable})")


class MCPClient:
    """Common MCP client for calling data servers with timeout and error handling."""

    def __init__(self, timeout_seconds: int = 2):
        """Initialize MCP client with timeout."""
        self.timeout_seconds = timeout_seconds

    def call(
        self,
        server_name: str,
        function: str,
        params: dict[str, Any],
        alert_id: str | None = None,
    ) -> dict[str, Any] | MCPError:
        """Call an MCP server function with timeout and error handling.

        Args:
            server_name: Name of the MCP server (MCP-01, MCP-02, etc.)
            function: Function name to call
            params: Parameters to pass to function
            alert_id: Alert ID for audit logging

        Returns:
            Response dict or MCPError
        """
        # Calculate hash of input for audit trail
        input_str = json.dumps(params, sort_keys=True, separators=(",", ":"))
        input_hash = hashlib.sha256(input_str.encode()).hexdigest()

        # Log TOOL_CALLED event if alert_id provided
        if alert_id:
            event_key = f"{alert_id}_{server_name}_{function}"
            try:
                add_event(
                    alert_id=alert_id,
                    event_type="TOOL_CALLED",
                    event_key=event_key,
                    actor=Role.SISTEMA,
                    prompt_sha256=input_hash,
                )
            except Exception:
                pass  # Audit logging failure doesn't block tool call

        # Simulate MCP call with timeout behavior
        start_time = time.time()
        try:
            # In a real implementation, this would make an actual MCP call
            # For now, return a structured error for slow responses
            elapsed = time.time() - start_time

            if elapsed > self.timeout_seconds:
                return MCPError(
                    error_code="TIMEOUT",
                    message=f"Server {server_name}.{function} exceeded {self.timeout_seconds}s",
                    retryable=True,
                )

            # Success - return response structure
            return {
                "status": "success",
                "data": None,  # Populated by actual server
                "server": server_name,
                "function": function,
            }
        except Exception as e:
            return MCPError(
                error_code="INTERNAL_ERROR",
                message=str(e),
                retryable=False,
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dict for serialization."""
        return {
            "error_code": self.error_code if isinstance(self, MCPError) else None,
            "retryable": self.retryable if isinstance(self, MCPError) else None,
        }
