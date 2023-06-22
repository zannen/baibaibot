class NotConnectedError(Exception):
    def __init__(self):
        super().__init__("Not connected to API server")


class SubclassError(Exception):
    def __init__(self):
        super().__init__("to be implemented in a subclass")
