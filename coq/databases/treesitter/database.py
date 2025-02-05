from asyncio import CancelledError
from concurrent.futures import Executor
from contextlib import closing
from sqlite3 import Connection, OperationalError
from threading import Lock
from typing import Iterable, Iterator, Mapping

from std2.asyncio import run_in_executor
from std2.sqlite3 import with_transaction

from ...consts import TREESITTER_DB
from ...shared.executor import SingleThreadExecutor
from ...shared.settings import Options
from ...shared.sql import BIGGEST_INT, init_db
from ...shared.timeit import timeit
from ...treesitter.types import Payload, SimplePayload
from .sql import sql


def _init() -> Connection:
    conn = Connection(TREESITTER_DB, isolation_level=None)
    init_db(conn)
    conn.executescript(sql("create", "pragma"))
    conn.executescript(sql("create", "tables"))
    return conn


class TDB:
    def __init__(self, pool: Executor) -> None:
        self._lock = Lock()
        self._ex = SingleThreadExecutor(pool)
        self._conn: Connection = self._ex.submit(_init)

    def _interrupt(self) -> None:
        with self._lock:
            self._conn.interrupt()

    async def new_nodes(self, nodes: Iterable[Payload]) -> None:
        def m1() -> Iterator[Mapping]:
            for node in nodes:
                yield {
                    "word": node.text,
                    "kind": node.kind,
                    "pword": node.parent.text if node.parent else None,
                    "pkind": node.parent.kind if node.parent else None,
                    "gpword": node.grandparent.text if node.grandparent else None,
                    "gpkind": node.grandparent.kind if node.grandparent else None,
                }

        def cont() -> None:
            with self._lock, closing(self._conn.cursor()) as cursor:
                with with_transaction(cursor):
                    cursor.execute(sql("delete", "words"))
                    cursor.executemany(sql("insert", "word"), m1())

        await run_in_executor(self._ex.submit, cont)

    async def select(
        self, opts: Options, word: str, limitless: int
    ) -> Iterator[Payload]:
        def cont() -> Iterator[Payload]:
            try:
                with closing(self._conn.cursor()) as cursor:
                    with with_transaction(cursor):
                        cursor.execute(
                            sql("select", "words"),
                            {
                                "exact": opts.exact_matches,
                                "cut_off": opts.fuzzy_cutoff,
                                "look_ahead": opts.look_ahead,
                                "limit": BIGGEST_INT if limitless else opts.max_results,
                                "word": word,
                            },
                        )
                        rows = cursor.fetchall()

                        def c2() -> Iterator[Payload]:
                            for row in rows:
                                grandparent = (
                                    SimplePayload(
                                        text=row["gpword"], kind=row["gpkind"]
                                    )
                                    if row["gpword"] and row["gpkind"]
                                    else None
                                )
                                parent = (
                                    SimplePayload(text=row["pword"], kind=row["pkind"])
                                    if row["pword"] and row["pkind"]
                                    else None
                                )
                                yield Payload(
                                    text=row["word"],
                                    kind=row["kind"],
                                    parent=parent,
                                    grandparent=grandparent,
                                )

                        return c2()
            except OperationalError:
                return iter(())

        def step() -> Iterator[Payload]:
            self._interrupt()
            return self._ex.submit(cont)

        try:
            return await run_in_executor(step)
        except CancelledError:
            with timeit("INTERRUPT !! TREESITTER"):
                await run_in_executor(self._interrupt)
            raise
