from typing import Any, Mapping, Sequence

from pynvim.api.nvim import Nvim
from pynvim_pp.api import buf_filetype, buf_name, cur_buf
from std2.pickle import decode

from ...registry import atomic, autocmd, rpc
from ...snippets.types import ParsedSnippet
from ..runtime import Stack


@rpc(blocking=True)
def _dir_changed(nvim: Nvim, stack: Stack, event: Mapping[str, Any]) -> None:
    cwd: str = event["cwd"]
    stack.state.cwd = cwd


autocmd("DirChanged") << f"lua {_dir_changed.name}(vim.v.event)"


@rpc(blocking=True)
def _ft_changed(nvim: Nvim, stack: Stack) -> None:
    buf = cur_buf(nvim)
    name = buf_name(nvim, buf=buf)
    ft = buf_filetype(nvim, buf=buf)
    raw = stack.settings.clients.snippets.snippets.get(ft, ())
    snippets: Sequence[ParsedSnippet] = decode(Sequence[ParsedSnippet], raw)

    stack.bdb.ft_update(name, filetype=ft)
    stack.sdb.populate(ft, snippets=snippets)


autocmd("FileType") << f"lua {_ft_changed.name}()"
atomic.exec_lua(f"{_ft_changed.name}()", ())

