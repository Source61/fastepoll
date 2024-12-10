# Description
Fast epoll server for Python3 (asyncio and uvloop server replacement) w/ Linux and TCP-support only (for now).

# HTTP benchmarks
Tools used: wrk with the parameters 120 connections over 6 threads.
Hardware: server running on a 50% underclocked Intel Core Ultra 7 with 22 CPU threads.

| Name | Requests per second | Connection type |
| --- | --- | --- |
| Asyncio | 14466 | close |
| Uvloop | 30608 | close |
| Fastepoll | 76072 | close |
| Asyncio | 109428 | keep-alive |
| Uvloop | 134465 | keep-alive |
| Nginx | 347217 | keep-alive |
| Fastepoll | 408639 | keep-alive |

# Example code
Note: this code won't reach benchmark performance above due to wrk being picky about required missing HTTP headers such as the date field. For the exact benchmark code used above check out bench directory.

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
