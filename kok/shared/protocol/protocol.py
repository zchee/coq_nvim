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

from .types import (
    Completion,
    Context,
    ContextualEdit,
    Options,
    RangeEdit,
    SnippetContext,
)

"""
Newline seperated JSON RPC
"""


"""
Basic Layout
"""


@runtime_checkable
class Message(Protocol):
    """
    Messages are not ordered
    """

    @property
    @abstractmethod
    def uid(self) -> int:
        """
        ID must be unique between Request / Response pairs
        """

    @property
    @abstractmethod
    def m_type(self) -> str:
        """
        Must be a Literal
        """


@runtime_checkable
class Notification(Message, Protocol):
    """
    Notifications can be ignored
    """


@runtime_checkable
class Response(Message, Protocol):
    """
    Each Request must receive a Response
    """


@runtime_checkable
class NotSupportedResponse(Response, Protocol):
    """
    Response Can be "Not supported"
    """

    @property
    @abstractmethod
    def not_supported(self) -> Literal[True]:
        ...


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
class Request(Message, Protocol):
    """
    Each Request type has a single vaild Response Type
    """

    resp_type: Annotated[ClassVar[Type], "resp_type is NOT serialized"] = Response


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
================================================================================
================================================================================
================================================================================
Implementation dataclasses
Not part of protocol
"""


@dataclass(frozen=True)
class _HasID:
    uid: int


@dataclass(frozen=True)
class NotSupportedResp(NotSupportedResponse, _HasID):
    not_supported: Literal[True] = True


@dataclass(frozen=True)
class ErrorResp(ErrorResponse, _HasID):
    msg: str
    error: Literal[True]


"""
Hand Shake
"""


@runtime_checkable
class HandShakeMessage(Message, Protocol):
    """
    The first message is always a handshake
    """


@dataclass(frozen=True)
class Acknowledge(HandShakeMessage, ServerSent, Response, _HasID):
    """
    Server must provide options to client
    """

    options: Options

    uid: Literal[0] = 0
    m_type: Literal["ACK"] = "ACK"


@dataclass(frozen=True)
class Hello(HandShakeMessage, ClientSent, Request, _HasID):
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
class CompletionMessage(Message, Protocol):
    ...


@dataclass(frozen=True)
class _HasCtxID:
    ctx_uid: int


@dataclass(frozen=True)
class DeadlinePastNotification(
    CompletionMessage, Broadcast, Notification, _HasCtxID, _HasID
):
    """
    Server must announce when completion is no longer required
    """

    m_type: Literal["DeadlinePastNotification"] = "DeadlinePastNotification"


@dataclass(frozen=True)
class CompletionResponse(CompletionMessage, ClientSent, Response, _HasCtxID, _HasID):
    """
    Client must send completions to server
    """

    has_pending: bool
    completions: Sequence[Completion]

    m_type: Literal["CompletionResponse"] = "CompletionResponse"


@dataclass(frozen=True)
class CompletionRequest(CompletionMessage, Broadcast, Request, _HasCtxID, _HasID):
    """
    Client must send completions to server
    """

    deadline: Annotated[float, "Seconds since UNIX epoch"]
    context: Context

    m_type: Literal["CompletionRequest"] = "CompletionRequest"
    resp_type: ClassVar[Type[Message]] = CompletionResponse


@dataclass(frozen=True)
class FurtherCompletionRequest(
    CompletionMessage, ServerSent, Request, _HasCtxID, _HasID
):
    """
    Client must send completions to server
    """

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
class SnippetAppliedNotification(
    SnippetMessage, ServerSent, Notification, _HasMeta, _HasID
):
    """
    Server must send notif after it applies the edits
    Contains -- `meta`
    """

    m_type: Literal["SnippetAppliedNotification"] = "SnippetAppliedNotification"


@dataclass(frozen=True)
class SnippetEditResponse(SnippetMessage, ClientSent, Response, _HasMeta, _HasID):
    """
    Client must reply to each snippet parse request
    Client can optionally ask the server to apply an edit
    """

    edit: Union[ContextualEdit, RangeEdit, None]

    m_type: Literal["ParseResponse"] = "ParseResponse"


@dataclass(frozen=True)
class SnippetParseRequest(SnippetMessage, Broadcast, Request, _HasID):
    """
    Server will ask all clients to parse / apply snippet
    Clients can reply with
    """

    context: SnippetContext

    m_type: Literal["ParseRequest"] = "ParseRequest"
    resp_type: ClassVar[Type[Message]] = SnippetEditResponse
