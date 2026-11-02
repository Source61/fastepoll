# fastepoll 2

A multi-process epoll server core for Python on Linux, with an asyncio-compatible protocol API. It serves TCP, Unix stream sockets and UDP from one C++ event loop per worker process. A single `abi3` wheel runs on CPython 3.12 and newer.

## Install

fastepoll is closed source and ships as that one binary wheel, on PyPI. Debian and Ubuntu leave the system Python to apt, so install it into a virtual environment (there, `python3 -m venv` needs the `python3-venv` package):

```sh
python3 -m venv /srv/app/venv
/srv/app/venv/bin/pip install fastepoll
```

- **Python:** CPython 3.12 or newer, tested on 3.12 to 3.15. Debian 12 and Ubuntu 22.04 come with older ones, so get 3.12 first (on Ubuntu from the deadsnakes PPA, anywhere with uv or pyenv). pip won't install the wheel on free-threaded builds (`python3.14t`).
- **System:** Linux 5.3 on x86-64 with glibc 2.34 and OpenSSL 3, or newer: Debian 12, Ubuntu 22.04, RHEL 9 and later. pip won't install it on an older glibc.

## Quick start

```python
import fastepoll

class Echo:
  def connection_made(self, transport):
    self.transport = transport

  def data_received(self, data):
    self.transport.write(data)

fastepoll.run(Echo, "0.0.0.0", 8000)
```

Classes written for `asyncio.Protocol` and `asyncio.DatagramProtocol` work unchanged; subclassing them is optional.

## Internet-facing servers: set the limits

Like asyncio, fastepoll has **no idle timeout and no connection limit by default**, so long-lived connections (chat, websockets) are never cut. A public server must set them, or idle and slowloris clients can hold file descriptors forever until new clients are refused:

```python
fastepoll.run(App, None, 80, idle_timeout=30, max_connections=10_000, shutdown_timeout=10)
```

- `idle_timeout`: seconds without any I/O progress before a connection is dropped (`connection_lost(TimeoutError)`). This includes a client that stops reading a response.
- `max_connections`: per worker; a full worker stops accepting and leaves new clients to the others. The total is `workers × max_connections`, so raise the fd limit to match (`LimitNOFILE=` in systemd).
- Protocol-level deadlines, such as "the HTTP headers must arrive within 10 s", belong in the protocol. Use `call_later()`, see below.

## Endpoints

`run()` serves a single TCP endpoint. `serve()` takes any mix, each with its own protocol factory:

```python
fastepoll.serve([
  fastepoll.TCP(Dns, None, 53),
  fastepoll.UDP(DnsDatagram, None, 53),
  fastepoll.Unix(Admin, "/run/app/admin.sock", mode=0o660),
], workers=0, idle_timeout=30)
```

- `TCP(factory, host=None, port, backlog=1024)`: `host=None` listens on all interfaces, separately for IPv4 and IPv6. It can also be a name, a numeric address or a list. Nothing is bound beyond what you name.
- `Unix(factory, path, backlog=1024, mode=None)`: a stale socket file left by a crash is replaced. A live socket, or a file that isn't a socket, is an error. The file is removed on exit.
  - `path + ".lock"` stops two servers that start at once from taking each other's socket. It is held only until stopping begins, so a new instance can start while the old one drains.
  - The lock file stays behind on purpose. If it belongs to another user, remove it once.
  - `mode` needs `/proc`, as on any normal Linux system.
  - Put sockets in a directory that only the server's user can write, such as `/run/app/`.
- A leading `"\0"` makes the name abstract. Abstract sockets have no file permissions, so anyone in the network namespace can connect; `mode` is refused for them.
- `sock=` serves an already bound socket, in place of `TCP()`'s host and port or `Unix()`'s path. The port then never goes free between server generations, and no client is refused while one replaces another:
  - from systemd socket activation, where systemd keeps the socket across restarts;
  - from a launcher that keeps the socket and starts each new generation before stopping the old one. The old generation finishes its connections while the new one accepts. Between generations, clients wait in the socket's queue.

  fastepoll makes its copy of the socket when `serve()` starts, before any worker forks, and closes only that copy. It calls `listen()` if nobody has yet, and it never removes the file of a `Unix()` socket passed this way. Making the copy non-blocking also makes the caller's socket non-blocking, as the two share one open file.

  The socket itself stays the caller's, so fastepoll's fork handling leaves it alone. Workers inherit it, and so do processes forked from them. Programs they start inherit it too unless it is non-inheritable. Python's own sockets are non-inheritable; systemd's are not. Once `serve()` has started, the caller may close its socket in any process, workers included, and the server keeps serving from its copies.

  ```python
  # systemd socket activation: a .socket unit's sockets arrive as descriptors 3, 4, ...
  if os.environ.get("LISTEN_PID") != str(os.getpid()):
    raise SystemExit("start this through its systemd .socket unit")
  socks = [socket.socket(fileno=3 + i) for i in range(int(os.environ["LISTEN_FDS"]))]
  for s in socks:
    s.set_inheritable(False) # not passed on to programs the workers start
  fastepoll.serve([fastepoll.Unix(App, sock=s) if s.family == socket.AF_UNIX else fastepoll.TCP(App, sock=s) for s in socks])
  ```
- Bind errors name the address, for example `[Errno 98] Address already in use: '0.0.0.0:443'`.
- `UDP(factory, host=None, port)`: the supervisor keeps one `SO_REUSEPORT` socket per worker for its whole life. The kernel keeps a client on the same worker, also across worker restarts, and no other process can take the port meanwhile. A port already in use is an error.

## TLS

```python
tls = fastepoll.TLS("/etc/letsencrypt/live/example.com/fullchain.pem", "/etc/letsencrypt/live/example.com/privkey.pem", sni={"*.example.org": ("org-chain.pem", "org-key.pem")}, alpn=["http/1.1"])
fastepoll.serve([fastepoll.TCP(Https, None, 443, tls=tls), fastepoll.TCP(Redirect, None, 80)], idle_timeout=30, max_connections=10_000)
```

- **Protocols see plaintext.** `connection_made()` comes after a successful handshake, and failed handshakes (scanners, plain HTTP on port 443) never reach protocol code.
- **Defaults:**
  - TLS 1.2 and newer (`min_version="1.3"` requires 1.3). TLS 1.3 uses OpenSSL's choices, including post-quantum hybrid key exchange where the OpenSSL version has it. TLS 1.2 is limited to forward-secret AEAD suites (ECDHE with AES-GCM or ChaCha20).
  - No renegotiation, no 0-RTT data (it can be replayed), no compression.
  - Private keys must be unencrypted; an encrypted key fails to load rather than prompting for a pass phrase.
- **Handshake limits:** clients get `handshake_timeout` seconds (a `serve()` option, default 10) to finish. A stalled handshake costs about 60 KB and an fd until then, so public servers should also set `max_connections`.
- **Connection details:** `get_extra_info()` adds `tls_version`, `cipher`, `alpn_protocol`, `server_name` (the client's SNI) and `ktls`. SNI is limited to printable ASCII at the handshake.
- **Who reads the certificate files:** only the supervisor, at startup, on SIGHUP (`systemctl reload`) and at every ticket-key rotation. Workers load what passed its checks, also after a crash restart, so a half-written renewal is never served.
- **Certificate renewal:** new connections get the new certificates and existing ones keep theirs. If the new files don't load, the previous certificates stay in use and the error is printed. For certbot: `--deploy-hook "systemctl reload yourservice"`.
- **SIGHUP** only ever reloads; it never stops the server, not even when a terminal closes.
- **Session resumption:** TLS 1.3 sessions resume on any worker. The ticket keys are shared, rotate every `ticket_lifetime` seconds (default 3600) and on every reload, and tickets stay valid for one more rotation. TLS 1.2 clients get no tickets, as a TLS 1.2 ticket would carry the session's master secret. Only those that don't ask for tickets resume (from the worker's own session cache), so most TLS 1.2 clients do a full handshake each time.
- **Truncation:** a peer that closes without TLS's `close_notify` looks like a normal EOF. Protocols should delimit their messages, as HTTP does with `Content-Length`.
- **Kernel TLS:** the kernel does the encryption, and `sendfile()` stays zero-copy, where TLS 1.3 key updates work with it. That needs the kernel's `tls` module, a kernel that takes new keys on a live connection (Linux 6.14, or a backport; fastepoll tries it at startup), and OpenSSL 3.2 or newer. Otherwise OpenSSL encrypts, and `sendfile()` reads files in 64 KiB chunks.
  - Debian 13's stock 6.12 kernel and RHEL 9's can't take new keys; a 6.14+ kernel, such as Debian's from trixie-backports, can.
  - OpenSSL 3.0, as on Debian 12 and Ubuntu 22.04 and 24.04, never hands the kernel the new keys. Only root can make the kernel load the module on demand, so put `tls` into `/etc/modules-load.d/` for servers that don't run as root.
  - Kernel TLS sends files faster but writes from memory slower: in a loopback benchmark, `sendfile()` ran 60–85% faster and 2–16 KB writes 13–36% slower. `TLS(..., ktls=False)` can pay off for an endpoint that mostly sends generated content.
- **No half-close**, as in asyncio: `can_write_eof()` is false and `write_eof()` raises `NotImplementedError`.
- **OpenSSL** is the system library (`libssl.so.3`), so the distribution's security updates apply to fastepoll as well.

## Transports

Stream transports provide the asyncio methods:
- writing: `write`, `writelines`, `write_eof`, `can_write_eof`
- closing: `close`, `abort`, `is_closing`
- flow control: `pause_reading`, `resume_reading`, `is_reading`, `get_write_buffer_size`, `get_write_buffer_limits`, `set_write_buffer_limits`, with `pause_writing`/`resume_writing` on the protocol
- the rest: `get_extra_info("peername" | "sockname")`, `get_protocol`, `set_protocol`

They also offer:
- `transport.sendfile(file, offset=0, count=None)`: zero-copy sending of a regular file range, queued in order with writes. `file` is a file object or a file descriptor, and may be closed as soon as the call returns.
  - If the file shrinks before its bytes are sent, the connection is aborted with `OSError(EIO)`: the peer sees it end early, never a short file followed by later output. Replacing a file by renaming a new one over it is safe, since the queued copy keeps the old one.
  - Queued file bytes count toward the write buffer, so `pause_writing()` tells the protocol to stop taking requests.
  - More than 16 queued files on one connection, or more than a quarter of the fd limit across a worker, raise `OSError(ENOBUFS)`.
  - Protocols that serve files must honour `pause_writing()`, by calling `pause_reading()` until `resume_writing()`. Otherwise clients that never read can use up that worker-wide quota.
  - Reading a file that isn't in the page cache blocks the worker on disk I/O, as any read would.

As in asyncio, `write()` sends at once, so each call costs a system call (and with TLS, a record). Hand over pieces produced together, such as HTTP/2 frames, in one `write()` or `writelines()`: in a benchmark, a reply made of 21 small writes ran 10× slower than the same bytes in one.

Datagram transports provide `sendto(data, addr)`, `close`, `abort`, `is_closing`, `get_write_buffer_size` and `get_extra_info("sockname")`.

Differences from asyncio:

- **No event loop object or coroutines.** Everything is a callback, plus `call_later()` and `call_soon_threadsafe()`.
- **An optional `shutdown_requested()`** on the protocol is called when the server stops (see [shutdown](#processes-signals-and-shutdown)).
- **Exceptions in a protocol callback** print a traceback. They abort that connection, or drop that datagram; the worker keeps running. Only `SystemExit` and `KeyboardInterrupt` stop the worker, also from the program's own signal handlers, which run in workers as they would anywhere else.
- **Traceback output is rate-limited:** at most 10 tracebacks per 10 s per worker. The rest are counted, and the count is printed later, so clients can't flood the log.
- **`connection_lost()` can come up to 5 s after `close()`** (or after `idle_timeout`, if that's shorter). The server sends FIN and waits for the client to close, because closing with unread input would make the kernel reset the connection and cut off the response.
- **`sendto()` takes numeric addresses only**, because name resolution would block the loop. The send queue is capped at 1 MiB; beyond that, `error_received(OSError(ENOBUFS))` is called instead.

## Timers and threads

```python
class Http:
  def connection_made(self, transport):
    self.transport = transport
    self.headerTimer = fastepoll.call_later(10, transport.abort) # slowloris guard

  def data_received(self, data):
    ...
    if headersComplete:
      self.headerTimer.cancel()
```

Transports and `call_later()` belong to the worker's loop thread, and calls that act on a connection raise `RuntimeError` from another thread. Plain getters such as `get_protocol()` and `get_extra_info("peername")` work anywhere. A worker thread (for example, one making a blocking database call) hands its result back like this:

```python
fastepoll.call_soon_threadsafe(transport.write, result)
```

## Processes, signals and shutdown

- **Workers:** `workers=0` starts one process per CPU the server may run on (its CPU affinity, as `taskset` or a container sets it); `workers=1` runs in the calling process, which is handy for debugging. Workers share nothing, like PHP-FPM, so shared state belongs in Redis, a database or similar.
- **Accepting:** TCP and Unix listeners are shared by all workers, and only an idle worker is woken for a new connection.
- **Crashes:** a worker that crashes is logged and restarted. Workers also exit if the supervisor dies.
- **Forking:** a process `fork()`ed from a worker (a background job, `multiprocessing`) closes all of the server's sockets in itself. So it can't keep the port, or client connections, alive after the server is done with them.
  - Such a child must end with `os._exit()`. One that returns into the server loop instead (say, because its job raised) is ended there with a message, rather than running the rest of the program.
- **Shutdown:**
  - SIGTERM or SIGINT stops accepting, and each connection's protocol gets `shutdown_requested()` if it has that method. The protocol then finishes its work and closes the connection itself. An HTTP server, for example, closes idle connections right away, and the others after the response in progress. A connection accepted just before stopping began may still have its first request on the way, so closing it as idle loses that request. TLS handshakes under way may still finish within `handshake_timeout`. Their protocols then get `connection_made()`, any data that came with the handshake, and `shutdown_requested()`. Timers and `call_soon_threadsafe()` keep working meanwhile.
  - Connections whose protocol lacks `shutdown_requested()` are closed: their buffered output is delivered first.
  - Whatever remains after `shutdown_timeout` is aborted.
  - A second signal, or SIGQUIT, aborts immediately.
  - A worker stuck in a handler is killed 2 s after the deadline. With `workers=1` there's no supervisor to do that, so the third signal ends a stuck process (as does systemd's SIGKILL after `TimeoutStopSec`).
- **Stopping the supervisor alone:** a SIGTERM sent only to the supervisor stops all its workers and lets them drain.
- **systemd:** the default `KillMode=control-group` is fine; workers drain gracefully even though systemd also signals them directly. `KillMode=mixed` works too: systemd then sends SIGTERM to the supervisor alone, and the final SIGKILL reaches any worker still running after `TimeoutStopSec`.
- **Launchers:** a process may import fastepoll and then fork the processes that call `serve()`, for example one per server generation. fastepoll's fork handling affects only processes that are serving, or were forked from one.

```ini
[Service]
ExecStart=/srv/app/venv/bin/python /srv/app/server.py
LimitNOFILE=65536
TimeoutStopSec=20
```

## Not included yet

- HTTP, including HTTP/2, belongs in a layer on top. ALPN is supported for it.
- TLS client certificates (mTLS) and OCSP stapling.
- A threads mode, for free-threaded Python.
- Platforms other than Linux on x86-64.
