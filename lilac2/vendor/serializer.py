from __future__ import annotations

import os
import abc

import pickle

from .myutils import safe_overwrite

class Serializer(metaclass=abc.ABCMeta):
  def __init__(self, fname, readonly=False, default=None):
    '''
    Reading file fname.
    readonly specifies that the data will not be stored back when it is destructed
    If the data is locked, a SerializerError exception will be occur
    default indicates the data if the file does not exist or is empty

    Notice:
      To write back data correctly, you need to ensure that the object still exists when it needs to be written back or use the `with` statement
      Storing itself into its data attribute is not feasible considering unknown reasons
    '''
    self.fname = os.path.abspath(fname)
    if readonly:
      self.lock = None
    else:
      dir, file = os.path.split(self.fname)
      self.lock = os.path.join(dir, '.%s.lock' % file)
      for i in (1,):
        # 处理文件锁
        if os.path.exists(self.lock):
          try:
            pid = int(open(self.lock).read())
          except ValueError:
            break

          try:
            os.kill(pid, 0)
          except OSError:
            break
          else:
            self.lock = None
            raise SerializerError('Data is locked')
        with open(self.lock, 'w') as f:
          f.write(str(os.getpid()))

    try:
      self.load()
    except EOFError:
      self.data = default
    except IOError as e:
      if e.errno == 2 and not readonly: #文件不存在
        self.data = default
      else:
        raise

  def __del__(self):
    '''If it\'s needed, delete lock，save file(s)'''
    if self.lock:
      self.save()
      os.unlink(self.lock)

  def __enter__(self):
    return self.data

  def __exit__(self, exc_type, exc_value, traceback):
    pass

  @abc.abstractmethod
  def load(self):
    pass

  @abc.abstractmethod
  def save(self):
    pass

class PickledData(Serializer):
  def save(self):
    data = pickle.dumps(self.data)
    safe_overwrite(self.fname, data, mode='wb')

  def load(self):
    self.data = pickle.load(open(self.fname, 'rb'))

class SerializerError(Exception): pass

if __name__ == '__main__':
  # For testing purpose
  import tempfile
  f = tempfile.mkstemp()[1]
  testData = {'sky': 1000, 'kernel': -1000}
  try:
    with PickledData(f, default=testData) as p:
      print(p)
      p['space'] = 10000
      print(p)
  finally:
    os.unlink(f)
