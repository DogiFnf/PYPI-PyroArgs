# PyroArgs/utils/DataHolder.py
from typing import Any, Tuple

from pyrogram import Client

PyroArgsObj = None
ClientObj: Client = None
CustomData: Any = None
Trues: Tuple[str] = ('true', '1', 'yes')
Falses: Tuple[str] = ('false', '0', 'no')
