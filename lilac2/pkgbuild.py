import re
import fileinput
import tempfile
from subprocess import PIPE, run
from typing import Optional, Iterator, Generator, Dict, List, Union

def unquote_item(s: str) -> Optional[str]:
  m = re.search(r'''[ \t'"]*([^ '"]+)[ \t'"]*''', s)
  if m is not None:
    return m.group(1)
  else:
    return None

def add_into_array(line: str, values: Iterator[str]) -> str:
  l = line.find('(')
  r = line.rfind(')')
  arr_str = line[l+1:r].strip()
  arr = {unquote_item(x) for x in arr_str.split(' ')}.union(values)
  arr_str = '('
  for item in arr:
    if item == None: continue
    arr_str += "'{}' ".format(item)
  arr_str += ')'
  line = line[:l] + arr_str
  return line

def _add_deps(which, extra_deps):
  '''
  Add more values into the dependency array
  '''
  for line in edit_file('PKGBUILD'):
    if line.strip().startswith(which):
      line = add_into_array(line, extra_deps)
    print(line)

def add_depends(extra_deps):
  _add_deps('depends', extra_deps)

def add_makedepends(extra_deps):
  _add_deps('makedepends', extra_deps)

def edit_file(filename: str) -> Generator[str, None, None]:
  with fileinput.input(files=(filename,), inplace=True) as f:
    for line in f:
      yield line.rstrip('\n')

def obtain_array(name: str) -> Optional[List[str]]:
    '''
    Obtain an array variable from PKGBUILD.
    Works by calling bash to source PKGBUILD, writing the array to a temporary file, and reading from the file.
    '''
    with tempfile.NamedTemporaryFile() as output_file:
        command_write_array_out = """printf "%s\\0" "${{{}[@]}}" > {}""".format(name, output_file.name)
        command_export_array = ['bash', '-c', "source PKGBUILD && {}".format(command_write_array_out)]
        run(command_export_array, stderr=PIPE, check=True)
        res = output_file.read().decode()
        if res == '\0':
            return None
        variable = res.split('\0')[:-1]
        return variable

def obtain_depends() -> Optional[List[str]]:
    return obtain_array('depends')

def obtain_makedepends() -> Optional[List[str]]:
    return obtain_array('makedepends')

def obtain_optdepends(parse_dict: bool=True) -> Optional[Union[Dict[str, str], List[str]]]:
    obtained_array = obtain_array('optdepends')
    if not obtained_array:
        return obtained_array
    if parse_dict:
        return {pkg.strip() : desc.strip() for (pkg, desc) in (item.split(':', 1) for item in obtained_array)}
    else:
        return obtained_array

