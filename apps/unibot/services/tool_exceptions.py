class ToolHandlerError(Exception):
    """
    Raised by tools to indicate a handled failure that should be sent to the LLM
    without breaking the request flow.
    """

    def __init__(self, message: str, *, status: str = "ERROR", payload=None):
        super().__init__(message)
        self.status = status or "ERROR"
        self.payload = payload


class ToolHandlerWarning(Exception):
    """
    Raised by tools to indicate a handled warning that should continue the flow.
    """

    def __init__(self, message: str, *, status: str = "WARNING", payload=None):
        super().__init__(message)
        self.status = status or "WARNING"
        self.payload = payload
