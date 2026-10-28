"""Domain exceptions. Routers translate these to HTTP; the agent uses them to
decide whether a failure is worth a correction attempt."""


class QueryChatError(Exception):
    """Base class for expected, user-presentable errors."""


class UnsupportedDatabaseError(QueryChatError):
    """URL scheme is a vector store, unknown, or blocked by policy."""


class DatabaseConnectionError(QueryChatError):
    """Could not reach / authenticate to the user's database. Not retryable."""


class QueryValidationError(QueryChatError):
    """Generated query is malformed or unsafe. Retryable unless a security violation."""


class SecurityViolationError(QueryValidationError):
    """Generated query tries to write or use a forbidden operator. Never retried."""


class QueryExecutionError(QueryChatError):
    """Database rejected or failed the query. Retryable with the error as feedback."""


class AuthenticationError(QueryChatError):
    pass


class ConflictError(QueryChatError):
    pass


class RateLimitError(QueryChatError):
    pass


class NotFoundError(QueryChatError):
    pass
