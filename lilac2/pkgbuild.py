import re
import lilaclib

def unquote_item(s):
    m = re.search(r'''[ \t'"]*([^ '"]+)[ \t'"]*''', s)
    if m != None:
        return m.group(1)
    else:
        return None

def add_into_array(line, values):
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
    for line in lilaclib.edit_file('PKGBUILD'):
        if line.strip().startswith(which):
            line = add_into_array(line, extra_deps)
        print(line)

def add_depends(extra_deps):
    _add_deps('depends', extra_deps)

def add_makedepends(extra_deps):
    _add_deps('makedepends', extra_deps)
