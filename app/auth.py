"""API-key authentication.

A lightweight but real security dependency: every request to a protected route must present
a valid key in the `X-API-Key` header, matching the `API_KEY` environment variable (see
`app.config`). This is appropriate for a service-to-service / internal analytics API; a
public-facing product API would typically layer OAuth2/JWT on top, but the pattern here
(a FastAPI dependency that raises `HTTPException` on failure) is the same one you'd extend.

Usage: attach `Depends(require_api_key)` to a route or, more commonly, to an entire
`APIRouter` via `dependencies=[Depends(require_api_key)]`, as done in the routers package.
"""

from fastapi import Header, HTTPException, status

from app.config import get_settings

API_KEY_HEADER_NAME = "X-API-Key"


def require_api_key(x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER_NAME)) -> str:
    """FastAPI dependency enforcing the presence of a valid `X-API-Key` header.

    Raises:
        HTTPException(401): if the header is missing or does not match the configured API key.

    Returns:
        The validated API key (mostly useful for testing / introspection).
    """

    settings = get_settings()

    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing API key. Provide a valid '{API_KEY_HEADER_NAME}' header.",
        )

    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    return x_api_key
