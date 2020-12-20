#!/bin/python
import os
import json
from pathlib import Path
from djangorm import DjangORM

if 'RECORDER_DATABASE' in os.environ:
    database = json.loads(os.environ['RECORDER_DATABASE'])
else:
    database = None

db = DjangORM(module_name=Path(__file__).parent.name, database=database, module_path=Path(__file__).parent.parent)
db.configure()
db.migrate()
