from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Any
from ..ast import Circuit

@dataclass
class Token:
    """Represents a lexical token."""
    type: str  # e.g., 'IDENTIFIER', 'NUMBER', 'KEYWORD', 'NEWLINE'
    value: str
    line: int
    column: int

class ParseError(Exception):
    def __init__(self, message: str, line: int, column: int, file: str = None):
        self.message = message
        self.line = line
        self.column = column
        self.file = file
        super().__init__(f"Parse error at {file}:{line}:{column} - {message}")

class BaseParser(ABC):
    """Abstract base class for all dialect parsers."""

    def __init__(self):
        self.circuit = Circuit(name="top")
        self.current_file = None

    @abstractmethod
    def parse(self, content: str, filename: str = "<string>") -> Circuit:
        """Parses the given content and returns a Circuit AST."""
        pass
    
    @abstractmethod
    def parse_file(self, filepath: str) -> Circuit:
        """Parses a file from disk."""
        pass
