import builtins
import collections
import ctypes
import errno
import functools
import heapq
import itertools
import json
import math
import operator
import os
import random
import resource
import sys

from backend.training.bots import decide_bot
from backend.training.protocol import REQUEST_LIMIT, encode, error, validate_result

FILENAME = "<алгоритм>"
MODULES = {
    module.__name__: module
    for module in (collections, functools, heapq, itertools, math, operator, random)
}


def restrict():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (96 * 1024**2, 96 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
    lib = ctypes.CDLL("libseccomp.so.2")
    lib.seccomp_init.argtypes = (ctypes.c_uint32,)
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = (ctypes.c_char_p,)
    lib.seccomp_rule_add.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
    )
    lib.seccomp_load.argtypes = (ctypes.c_void_p,)
    lib.seccomp_release.argtypes = (ctypes.c_void_p,)
    context = lib.seccomp_init(0x80000000)  # SCMP_ACT_KILL_PROCESS
    if not context:
        raise RuntimeError("seccomp_init")
    try:
        for name in (
            "read",
            "write",
            "close",
            "exit",
            "exit_group",
            "brk",
            "mmap",
            "munmap",
            "mremap",
            "mprotect",
            "madvise",
            "futex",
            "clock_gettime",
            "getrandom",
            "rt_sigreturn",
        ):
            number = lib.seccomp_syscall_resolve_name(name.encode())
            if number < 0 or lib.seccomp_rule_add(context, 0x7FFF0000, number, 0) != 0:
                raise RuntimeError("seccomp_rule_add")
        # CPython пытается перечитать имя исходника для текста SyntaxError.
        # Возвращаем отказ ядра без открытия файлов.
        openat = lib.seccomp_syscall_resolve_name(b"openat")
        if (
            openat < 0
            or lib.seccomp_rule_add(context, 0x00050000 | errno.EACCES, openat, 0) != 0
        ):
            raise RuntimeError("seccomp_rule_add")
        if lib.seccomp_load(context) != 0:
            raise RuntimeError("seccomp_load")
    finally:
        lib.seccomp_release(context)


def import_module(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name not in MODULES:
        raise ImportError(f"Модуль {name[:80]} недоступен.")
    return MODULES[name]


def evaluate(job: dict) -> dict:
    namespace = {
        "__name__": "__algorithm__",
        "__builtins__": {
            **vars(builtins),
            "__import__": import_module,
            "print": lambda *args, **kwargs: None,
        },
    }
    try:
        code = compile(job["source"], FILENAME, "exec")
    except SyntaxError as exc:
        return error("syntax", f"Синтаксическая ошибка: {exc.msg}", exc.lineno)
    try:
        exec(code, namespace)  # noqa: S102 — процесс уже ограничен seccomp.
        decide = namespace.get("decide")
        if not callable(decide):
            return error("missing_decide", "Добавьте функцию decide(state, memory).")
        allowed = tuple(job["state"]["self"]["allowed_directions"])
        result = decide(job["state"], job["memory"])
        return validate_result(result, allowed)
    except MemoryError:
        return error("resource", "Алгоритм превысил лимит оперативной памяти.")
    except (Exception, SystemExit, KeyboardInterrupt, GeneratorExit) as exc:  # noqa: BLE001 — ошибка пользовательского кода.
        line = None
        stack = exc.__traceback__
        while stack is not None:
            if stack.tb_frame.f_code.co_filename == FILENAME:
                line = stack.tb_lineno
            stack = stack.tb_next
        if isinstance(exc, PermissionError):
            return error("restricted", "Алгоритм запросил недоступную операцию.", line)
        message = str(exc)[:300]
        return error("runtime", f"{type(exc).__name__}: {message}", line)


def main():
    job = json.loads(sys.stdin.buffer.readline(REQUEST_LIMIT))
    # CPython загружает хеширование при первом строковом seed.
    random.Random("snake-arena")
    restrict()
    output = sys.stdout.buffer
    output.write(b"ready\n")
    output.flush()
    state = job["state"]
    if "bot" in job:
        response = validate_result(
            {"direction": decide_bot(job["bot"], state, job["seed"]), "memory": None},
            state["self"]["allowed_directions"],
        )
    else:
        response = evaluate(job)
    output.write(encode(response) + b"\n")
    output.flush()
    # После ответа завершаем одноразовый процесс без финализации CPython.
    os._exit(0)
