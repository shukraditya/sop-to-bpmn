"""SOP RawSteps -> ProcessGraph via state machine with deferred-gateway pattern."""

from .core import SimpleSOPParser
from .state import ParserState

__all__ = ["ParserState", "SimpleSOPParser"]
