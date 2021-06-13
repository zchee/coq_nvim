from asyncio.events import Handle, get_running_loop
from typing import Any, Mapping, Optional, TypedDict

from pynvim.api.nvim import Nvim
from std2.pickle import DecodeError, decode
from std2.pickle.coders import BUILTIN_DECODERS

from ...registry import autocmd, enqueue_event, rpc
from ..edit import edit
from ..runtime import Stack
from ..types import UserData


class _CompEvent(TypedDict, total=False):
    user_data: Any


@rpc(blocking=True)
def _dir_changed(nvim: Nvim, stack: Stack, event: Mapping[str, Any]) -> None:
    cwd: str = event["cwd"]
    stack.state.cwd = cwd


autocmd("DirChanged") << f"lua {_dir_changed.name}(vim.v.event)"


@rpc(blocking=True)
def _insert_enter(nvim: Nvim, stack: Stack) -> None:
    stack.state.inserting = True


autocmd("InsertEnter") << f"lua {_insert_enter.name}()"


@rpc(blocking=True)
def _insert_leave(nvim: Nvim, stack: Stack) -> None:
    stack.state.inserting = False


autocmd("InsertLeave") << f"lua {_insert_leave.name}()"


@rpc(blocking=True)
def _comp_done_pre(nvim: Nvim, stack: Stack, event: _CompEvent) -> None:
    data = event.get("user_data")
    if data:
        try:
            user_data: UserData = decode(UserData, data, decoders=BUILTIN_DECODERS)
        except DecodeError:
            pass
        else:
            if stack.state.cur:
                ctx, _ = stack.state.cur
                if user_data.uid == ctx.uid:
                    edit(nvim, ctx=ctx, data=user_data)


autocmd("CompleteDonePre") << f"lua {_comp_done_pre.name}(vim.v.completed_item)"


@rpc(blocking=True)
def _vaccum(nvim: Nvim, stack: Stack) -> None:
    stack.db.vaccum()


_handle: Optional[Handle] = None


@rpc(blocking=True)
def _cursor_hold(nvim: Nvim, stack: Stack) -> None:
    global _handle
    if _handle:
        _handle.cancel()

    def cont() -> None:
        enqueue_event(_vaccum)

    loop = get_running_loop()
    _handle = loop.call_later(0.5, cont)


autocmd("CursorHold", "CursorHoldI") << f"lua {_cursor_hold.name}()"

