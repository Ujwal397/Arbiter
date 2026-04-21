import json

def dumps(obj, *args, **kwargs):
    return json.dumps(obj).encode('utf-8')

def loads(obj, *args, **kwargs):
    return json.loads(obj)

class OrjsonError(Exception):
    pass

JSONDecodeError = json.JSONDecodeError
