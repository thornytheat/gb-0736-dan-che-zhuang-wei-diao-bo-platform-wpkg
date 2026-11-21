class DomainError(Exception):
    def __init__(self, code, status=422, **details):
        super().__init__(code)
        self.code = code
        self.status = status
        self.details = details
