import asyncio, fastepoll, time

timenow = 0
response = b""

class WebServer(asyncio.Protocol):
  def connection_made(self, transport):
    self.transport = transport

  def data_received(self, data: bytes):
    global response, timenow
    newtime = int(time.time())
    if newtime != timenow:
      timenow = newtime
      response = b"""HTTP/1.0 200 OK\r\nServer: nginx/1.22.1\r\nDate: %b\r\nContent-Type: text/html\r\nContent-Length: 615\r\nLast-Modified: Fri, 15 Nov 2024 22:21:58 GMT\r\nConnection: keep-alive\r\nAccept-Ranges: bytes\r\n\r\n<!DOCTYPE html>\n<html>\n<head>\n<title>Welcome to nginx!</title>\n<style>\nhtml { color-scheme: light dark; }\nbody { width: 35em; margin: 0 auto;\nfont-family: Tahoma, Verdana, Arial, sans-serif; }\n</style>\n</head>\n<body>\n<h1>Welcome to nginx!</h1>\n<p>If you see this page, the nginx web server is successfully installed and\nworking. Further configuration is required.</p>\n\n<p>For online documentation and support please refer to\n<a href="http://nginx.org/">nginx.org</a>.<br/>\nCommercial support is available at\n<a href="http://nginx.com/">nginx.com</a>.</p>\n\n<p><em>Thank you for using nginx.</em></p>\n</body>\n</html>\n""" % time.strftime("%a, %d %b %Y %T %Z", time.gmtime(timenow)).encode()
    self.transport.send(response)

  def eof_received(self):
    pass

fastepoll.run_forever(WebServer, ":::80", True)
