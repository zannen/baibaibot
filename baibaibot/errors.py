class APIError(Exception):
    def __init__(self, message: str):
        super().__init__(f"API error: {message}")


class NotConnectedError(Exception):
    def __init__(self):
        super().__init__("Not connected to API server")


class SubclassError(Exception):
    def __init__(self):
        super().__init__("to be implemented in a subclass")
