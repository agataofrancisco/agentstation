"""Erros de ferramentas. Os codigos sao curtos e nao expoem detalhes internos ao modelo."""


class ToolError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
