* Version 1.0.1: added required bool sync option to run(...) and run_forever(...). Sync set to False makes epoll \[potentially much\] faster, but calls to Python are executed by different threads resulting in different Python states when called by different threads, thus some apps require sync=True, others, like a HTTP server, probably does not.
* Version 1.0.0: first public version
