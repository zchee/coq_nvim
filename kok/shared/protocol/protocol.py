from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import (
    Annotated,
    Any,
    ClassVar,
    Literal,
    Protocol,
    Sequence,
    Type,
    Union,
    runtime_checkable,
)

from .types import Completion, Context, ContextualEdit, Options, RangeEdit, SnippetEdit

"""
Newline seperated JSON RPC
"""


"""
Basic Layout
"""


@runtime_checkable
class HasID(Protocol):
    """
    ID must be unique between Request / Response pairs
    """

    @property
    @abstractmethod
    def uid(self) -> int:
        ...


@dataclass(frozen=True)
class _HasID(HasID):
    uid: int


@runtime_checkable
class Message(Protocol):
    """
    Messages are not ordered
    """

    @property
    @abstractmethod
    def m_type(self) -> Annotated[str, "Must be a Literal"]:
        ...


@runtime_checkable
class Notification(Message, Protocol):
    """
    Notifications can be ignored
    """


@runtime_checkable
class Response(Message, HasID, Protocol):
    """
    Each Request must receive a Response
    """


@runtime_checkable
class ErrorResponse(Response, Protocol):
    """
    Response Can be an Error
    """

    @property
    @abstractmethod
    def error(self) -> Literal[True]:
        ...

    @property
    @abstractmethod
    def msg(self) -> str:
        ...


@runtime_checkable
class Request(Message, HasID, Protocol):
    """
    Each Request type has a single vaild Response Type
    """

    resp_type: ClassVar[Type] = Response


"""
Authorship
"""


@runtime_checkable
class ClientSent(Message, Protocol):
    """
    Can only be sent from client
    """


@runtime_checkable
class ServerSent(Message, Protocol):
    """
    Can only be sent from server
    """


@runtime_checkable
class Broadcast(ServerSent, Protocol):
    """
    Sent to all clients
    """


"""
Hand Shake
"""


@runtime_checkable
class HandShakeMessage(Protocol):
    ...


@dataclass(frozen=True)
class Acknowledge(HandShakeMessage, ServerSent, Response):
    """
    Server must provide options to client
    """

    options: Options

    uid: Literal[0] = 0
    m_type: Literal["ACK"] = "ACK"


@dataclass(frozen=True)
class Hello(HandShakeMessage, ClientSent, Request):
    """
    Client must make first request to server
    """

    uid: Literal[0] = 0
    m_type: Literal["HELO"] = "HELO"
    resp_type: ClassVar[Type[Message]] = Acknowledge


"""
Completion Request / Response
"""


@runtime_checkable
class CompletionMessage(Protocol):
    ...


@dataclass(frozen=True)
class _HasCtxID:
    ctx_uid: int


@dataclass(frozen=True)
class DeadlinePastNotification(CompletionMessage, Broadcast, Notification, _HasCtxID):
    m_type: Literal["DeadlinePastNotification"] = "DeadlinePastNotification"


@dataclass(frozen=True)
class CompletionResponse(CompletionMessage, ClientSent, Response, _HasID, _HasCtxID):
    has_pending: bool
    completions: Sequence[Completion]

    m_type: Literal["CompletionResponse"] = "CompletionResponse"


@dataclass(frozen=True)
class CompletionRequest(CompletionMessage, Broadcast, Request, _HasID, _HasCtxID):
    deadline: Annotated[float, "Seconds since UNIX epoch"]
    context: Context

    m_type: Literal["CompletionRequest"] = "CompletionRequest"
    resp_type: ClassVar[Type[Message]] = CompletionResponse


@dataclass(frozen=True)
class FurtherCompletionRequest(
    CompletionMessage, ServerSent, Request, _HasID, _HasCtxID
):
    deadline: Annotated[float, "Seconds since UNIX epoch"]

    m_type: Literal["FurtherCompletionRequest"] = "FurtherCompletionRequest"
    resp_type: ClassVar[Type[Message]] = CompletionResponse


"""
Snippet Request / Response
"""


@runtime_checkable
class SnippetMessage(Protocol):
    ...


@dataclass(frozen=True)
class _HasMeta:
    meta: Any


@dataclass(frozen=True)
class ParseResponse(SnippetMessage, ClientSent, Response, _HasMeta, _HasID):
    edit: Union[ContextualEdit, RangeEdit, None]

    m_type: Literal["ParseResponse"] = "ParseResponse"


@dataclass(frozen=True)
class ParseRequest(SnippetMessage, Broadcast, Request, _HasID):
    snippet: SnippetEdit

    m_type: Literal["ParseRequest"] = "ParseRequest"
    resp_type: ClassVar[Type[Message]] = ParseResponse


@dataclass(frozen=True)
class SnippetAppliedNotification(SnippetMessage, ServerSent, Notification, _HasMeta):
    m_type: Literal["SnippetAppliedNotification"] = "SnippetAppliedNotification"
