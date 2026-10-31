class DomainError(ValueError):
    """Input the maths cannot work with. Services map it to a 422 response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
