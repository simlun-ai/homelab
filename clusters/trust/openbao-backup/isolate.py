"""Deny outbound socket operations in the disposable OpenBao process."""

import ctypes
import errno
import os
import platform
import sys

# Linux audit architecture and syscall numbers for connect, sendto, sendmsg,
# sendmmsg, and io_uring_setup. The server can still accept loopback HTTPS/HTTP
# and write replies on those connections. No sockets are inherited.
LINUX_ABIS = {
    "x86_64": (0xC000003E, (42, 44, 46, 307, 425)),
    "aarch64": (0xC00000B7, (203, 206, 211, 269, 425)),
}
ALLOW = 0x7FFF0000
DENY = 0x00050000 | errno.EPERM
KILL = 0x80000000


class Instruction(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint),
    ]


class Filter(ctypes.Structure):
    _fields_ = [
        ("len", ctypes.c_ushort),
        ("filter", ctypes.POINTER(Instruction)),
    ]


def block_outbound() -> None:
    architecture, denied = LINUX_ABIS[platform.machine()]
    # Classic BPF: load architecture, fail closed on another ABI, then
    # inspect the syscall number. Also reject the x32 syscall flag.
    rules = [
        Instruction(0x20, 0, 0, 4),
        Instruction(0x15, 1, 0, architecture),
        Instruction(0x06, 0, 0, KILL),
        Instruction(0x20, 0, 0, 0),
        Instruction(0x45, 0, 1, 0x40000000),
        Instruction(0x06, 0, 0, KILL),
    ]
    for syscall in denied:
        rules.extend([Instruction(0x15, 0, 1, syscall), Instruction(0x06, 0, 0, DENY)])
    rules.append(Instruction(0x06, 0, 0, ALLOW))
    instructions = (Instruction * len(rules))(*rules)
    program = Filter(len(rules), instructions)
    libc = ctypes.CDLL(None, use_errno=True)
    if (
        libc.prctl(38, 1, 0, 0, 0) != 0  # PR_SET_NO_NEW_PRIVS
        or libc.prctl(22, 2, ctypes.byref(program), 0, 0) != 0  # PR_SET_SECCOMP
    ):
        raise OSError(ctypes.get_errno(), "Could not isolate rehearsal OpenBao")


if __name__ == "__main__":
    block_outbound()
    os.execv(sys.argv[1], sys.argv[1:])
