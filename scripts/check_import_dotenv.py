import sys
import importlib

print(sys.executable)
try:
    m = importlib.import_module('dotenv')
    print('dotenv module path:', getattr(m, '__file__', 'unknown'))
    print('dotenv import: OK')
except Exception as e:
    print('dotenv import FAILED:', repr(e))

