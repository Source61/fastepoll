#!/bin/bash

python3 -m build
sudo python3 -m pip uninstall fastepoll --break-system-packages
sudo python3 -m pip install dist/*.whl --break-system-packages
