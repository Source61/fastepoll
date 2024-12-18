# Description
Fast epoll server for Python3 (asyncio and uvloop server replacement) w/ Linux and TCP-support only (for now).
Main feature: It is able to handle more than 1M requests per second on regular physical hardware (e.g. a $1k laptop with an Intel Core Ultra 7 155H).

# HTTP benchmarks
Hardware: laptop on a 50% underclocked Intel Core Ultra 7 with 22 CPU threads.
Tools used: wrk with the parameters 120 connections over 8 threads for 1s (same results for longer durations).

| Name | Requests per second | Connection type |
| --- | --- | --- |
| Asyncio | 14466 | close |
| Uvloop | 30608 | close |
| Fastepoll | 76072 | close |
| Asyncio | 109428 | keep-alive |
| Uvloop | 134465 | keep-alive |
| Nginx | 347217 | keep-alive |
| Fastepoll | 408639 | keep-alive |
| Fastepoll | 645017 | keep-alive + desync |
| Fastepoll (100% CPU clock) | 1203882 | keep-alive + desync (100% CPU speed) |

# Example code
For benchmark code check the /bench directory out. This is just basic sample code.

```python
import fastepoll

class Test:
	def connection_made(self, transport):
		self.transport = transport

	def data_received(self, data):
		self.transport.send(b"HTTP/1.0 200 OK\r\n\r\nHello World")
		self.transport.close()

	def eof_received(self):
		pass

fastepoll.run_forever(Test, ":::8080")
```
