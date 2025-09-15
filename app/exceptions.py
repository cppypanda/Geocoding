"""
Custom exception classes for the application.
"""

class BaseCustomException(Exception):
    """Base class for custom exceptions in this application."""
    pass

class InvalidApiKeyError(BaseCustomException):
    """Raised when an API key is invalid, expired, or disabled."""
    pass

class RateLimitError(BaseCustomException):
    """Raised when an API rate limit has been exceeded."""
    pass

class ThirdPartyAPIError(BaseCustomException):
    """Raised for other errors from a third-party API."""
    pass

class GeocodingError(BaseCustomException):
    """Raised when geocoding fails for a non-API key reason (e.g., no results found)."""
    pass 