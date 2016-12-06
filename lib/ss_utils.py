import httplib
import ssl
import json
import subprocess
import time
import datetime
import threading
import csv

class RestHelper(object):

    def __init__(self, host, port, secure, check_cert=False, auth=None):
        self.host = host
        self.port = port
        self.secure = secure
        self.check_cert = check_cert
        self.auth = auth

    def set_auth(self, auth):
        self.auth = auth

    def request(self, method, uri, data=None, content_type='application/json', headers={}, auth='default', timeout=10):
        if self.secure:
            if self.check_cert:
                conn = httplib.HTTPSConnection(self.host, self.port, timeout=timeout)
            else:
                conn = httplib.HTTPSConnection(self.host, self.port, context=ssl._create_unverified_context(), timeout=timeout)
        else:
            conn = httplib.HTTPConnection(self.host, self.port, timeout=timeout)

        auth = self.auth if auth == 'default' else auth
        headers['Authorization'] = auth
        headers['Content-type'] = content_type
        conn.request(method, uri, data, headers=headers)
        return conn.getresponse()

class TaskTimer(threading.Thread):
    """Thread that executes a task every N seconds"""
    
    def __init__(self, interval, task, *args, **kargs):
        threading.Thread.__init__(self)
        self._finished = threading.Event()
        self._interval = interval
        self.task = task
        self.args = args
        self.kargs = kargs
    
    def shutdown(self):
        """Stop this thread"""
        self._finished.set()
    
    def run(self):
        while 1:
            if self._finished.isSet(): return
            self.task(*self.args, **self.kargs)
            
            # sleep for interval or until shutdown
            self._finished.wait(self._interval)

# shell
def run_cmd(cmd, get_output=False):
    cmd_list = list(csv.reader([cmd], delimiter=' ', quotechar="'", quoting=csv.QUOTE_ALL))[0]
    stdout = subprocess.PIPE if get_output else None
    stderr = subprocess.PIPE if get_output else None
    p = subprocess.Popen(cmd_list, stdout=stdout, stderr=stderr)
    if get_output:
        output = p.communicate()
    else:
        output = None
        p.wait()
    return p.returncode, output


# dicts

def xpath_get(mydict, path):
    elem = mydict
    try:
        for x in path.strip("/").split("/"):
            try:
                x = int(x)
                elem = elem[x]
            except ValueError:
                elem = elem.get(x)
    except:
        pass

    return elem

# time

def get_current_time():
    return datetime.datetime.utcnow()

def get_current_time_numeric():
    return self.get_current_time().strftime('%Y%m%d%H%M%S%f')

# result in milliseconds
def get_time_diff(t1, t2):
    return int((t2 - t1).microseconds/1000)


# string

def get_rand_string(base_name='user'):
    return base_name + Time.get_current_time_numeric()

def load_json_template(path, key_vals):

    f = open(path)
    string = f.read()
    f.close()
    resolved = string % key_vals
    return json.loads(resolved)
