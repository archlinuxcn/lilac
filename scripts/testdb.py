#!/usr/bin/python3

import sqlalchemy

from lilac2 import db

def main():
  engine = sqlalchemy.create_engine('postgresql:///')
  db.setup(engine)

  with db.get_session() as s:
    b = db.Batch(event='start')
    s.add(b)

if __name__ == '__main__':
  main()

