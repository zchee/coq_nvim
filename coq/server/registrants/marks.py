from collections import deque
from itertools import chain
from textwrap import dedent
from typing import Iterator, Sequence, Tuple, TypedDict

from pynvim.api.common import NvimError
from pynvim.api.nvim import Buffer, Nvim
from pynvim.api.window import Window
from pynvim_pp.api import (
    ask,
    buf_get_lines,
    buf_linefeed,
    cur_win,
    win_get_buf,
    win_set_cursor,
)
from pynvim_pp.lib import write
from pynvim_pp.logging import log
from pynvim_pp.operators import set_visual_selection

from ...lang import LANG
from ...registry import rpc
from ...shared.types import UTF8, Mark
from ...snippets.consts import MOD_PAD
from ..edit import EditInstruction, apply
from ..mark import NS
from ..rt_types import Stack
from ..state import state


class _MarkDetail(TypedDict):
    end_row: int
    end_col: int


def _ls_marks(nvim: Nvim, ns: str, buf: Buffer) -> Sequence[Mark]:
    marks: Sequence[Tuple[int, int, int, _MarkDetail]] = nvim.api.buf_get_extmarks(
        buf, ns, 0, -1, {"details": True}
    )

    def cont() -> Iterator[Mark]:
        for idx, r1, c1, details in marks:
            r2, c2 = details["end_row"], details["end_col"]
            m = Mark(idx=idx, begin=(r1, c1), end=(r2, c2), text="")
            yield m

    ordered = sorted(
        cont(),
        key=lambda m: (
            m.idx % MOD_PAD,
            m.begin,
            m.end,
        ),
    )
    return ordered


def _single_mark(
    nvim: Nvim, mark: Mark, marks: Sequence[Mark], ns: int, win: Window, buf: Buffer
) -> None:
    (r1, c1), (r2, c2) = mark.begin, mark.end
    try:
        if r1 == r2 and abs(c2 - c1) == 0:
            row, col = r1, min(c1, c2)
            win_set_cursor(nvim, win=win, row=row, col=col)
        else:
            row, col = r1, c1
            set_visual_selection(
                nvim, win=win, mode="v", mark1=(r1, c1), mark2=(r2, c2 - 1)
            )
            nvim.command("norm! c")
            win_set_cursor(nvim, win=win, row=r1, col=c1)
    except NvimError as e:
        msg = f"""
        bad mark location {mark}

        {e}
        """
        log.warn("%s", dedent(msg))
    else:
        nvim.command("startinsert")
        state(inserted=(row, col))
        msg = LANG("applied mark", marks_left=len(marks))
        write(nvim, msg)
    finally:
        nvim.api.buf_del_extmark(buf, ns, mark.idx)


def _trans(new_text: str, marks: Sequence[Mark]) -> Iterator[EditInstruction]:
    new_lines = new_text.splitlines()
    for mark in marks:
        yield EditInstruction(
            primary=False,
            primary_shift=False,
            begin=mark.begin,
            end=mark.end,
            cursor_yoffset=0,
            cursor_xpos=-1,
            new_lines=new_lines,
        )


def _linked_marks(
    nvim: Nvim, mark: Mark, linked: Sequence[Mark], ns: int, buf: Buffer
) -> bool:
    marks = tuple(chain((mark,), linked))

    def preview(mark: Mark) -> str:
        linesep = buf_linefeed(nvim, buf=buf)
        (r1, c1), (r2, c2) = mark.begin, mark.end
        lo, hi = min(r1, r2), max(r1, r2) + 1
        lines = buf_get_lines(nvim, buf=buf, lo=lo, hi=hi)

        def cont() -> Iterator[str]:
            for idx, line in enumerate(lines, start=lo):
                if idx == r1 and idx == r2:
                    yield line.encode(UTF8)[c1:c2].decode(UTF8)
                elif idx == r1:
                    yield line.encode(UTF8)[c1:].decode(UTF8)
                elif idx == r2:
                    yield line.encode(UTF8)[:c2].decode(UTF8)
                else:
                    yield line

        return linesep.join(cont())

    def place_holder() -> str:
        for p in map(preview, marks):
            if p:
                return p
        else:
            return ""

    resp = ask(nvim, question=LANG("expand marks"), default=place_holder())
    if resp is not None:
        apply(nvim, buf=buf, instructions=_trans(resp, marks=marks))
        for mark in marks:
            nvim.api.buf_del_extmark(buf, ns, mark.idx)
        return True
    else:
        return False


@rpc(blocking=True)
def nav_mark(nvim: Nvim, stack: Stack) -> None:
    ns = nvim.api.create_namespace(NS)
    win = cur_win(nvim)
    buf = win_get_buf(nvim, win=win)
    marks = deque(_ls_marks(nvim, ns=ns, buf=buf))

    if marks:
        mark = marks.popleft()
        base_idx = mark.idx % MOD_PAD
        linked = tuple(m for m in marks if m.idx % MOD_PAD == base_idx)

        def single() -> None:
            _single_mark(nvim, mark=mark, marks=marks, ns=ns, win=win, buf=buf)

        if not linked:
            single()
        else:
            edited = _linked_marks(nvim, mark=mark, linked=linked, ns=ns, buf=buf)
            if not edited:
                single()

    else:
        msg = LANG("no more marks")
        write(nvim, msg)
