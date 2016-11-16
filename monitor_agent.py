#!/usr/bin/python -u

import sys
sys.path.append('lib/')
import os
import routine_runner
import ss_utils
import json
from docker import client
import re
import socket
import threading

# config
DEBUG = True
CFG_FILE = 'config.json'
ROUTINES = 'routines/'
DEFAULT_PORT = 8080
CHECK_NAME = 'monitor'

'''
the below check needs to be configured on the sensu server:

  "checks": {
    "monitor": {
      "command": "",
      "standalone": true,
      "publish": false
    }
  }
'''



# helpers

def log(msg):
    print(msg)

def debug(msg):
    if DEBUG:
        log('DEBUG: ' + msg)

def get_container_name(container_obj):
    return container_obj['Names'][0][1:]

def get_host_cfg(container_obj):

    name = get_container_name(container_obj)
    inspect = CLI.inspect_container(container_obj)
    ip = inspect['NetworkSettings']['IPAddress']

    host = {
            'name': name,
            'hosts': [
                {
                    'name': name,
                    'hostname': ip,
                    'port': DEFAULT_PORT,
                    'container-name': name
                }
            ]
            }

    return host

def get_check_freq(container_name):

    for freq in CFG['frequencies']:
        if re.match('^'+freq['pattern']+'$', container_name):
            return freq['seconds']
    return None

# actions

def update():

    debug('updating server with current container list state')

    containers = CLI.containers()
    container_names = [ get_container_name(c) for c in containers ]

    clients = json.loads(server_conn.request('GET', '/clients').read())
    client_names = [ client['name'] for client in clients ]

    for container in containers:
        name = get_container_name(container)
        debug('getting configured check freq for: ' + name)
        freq = get_check_freq(name)
        if not freq:
            debug('frequency for container ' + name + ' is null, skipping')
            continue
        # add clients that don't exist on the server
        if name not in client_names:
            log('new container found: ' + name)
            log('posting client ' + name + ' to server')
            add_client(name)
        # add check timers that don't exist
        if name not in CHECK_TIMERS:
            log('creating check timer for ' + name + ' with freq: ' + str(freq))
            create_check_timer(container, freq)
            

    # delete clients that don't exist locally
    for client in clients:
        if client['address'] == HOSTNAME:
            client_name = client['name']
            if client_name not in container_names:
                log('container for client ' + client_name + ' no longer exists')
                log('deleting client')
                delete_client(client_name)
                log('canceling check timer for container: ' + client_name)
                CHECK_TIMERS.pop(client_name).shutdown()

def delete_client(name):

    resp = server_conn.request('DELETE', '/clients/' + name)

def add_client(name):

    data = {
        'name': name,
        'address': HOSTNAME,
        'subscriptions': [],
        'environment': ENV
        }

    server_conn.request('POST', '/clients', data=json.dumps(data))

def send_check_result(container_obj, routine_result):

    output = 'OK'
    status = 0
    if routine_result['tasks-failed'] != 0:
        output = json.dumps([ res for res in routine_result['task-results'] if res['result'] not in ('SUCCESS', 'SKIPPED')])
        status = 2

    body = {
        'source': get_container_name(container_obj),
        'name': CHECK_NAME,
        'output': output,
        'status': status
        }

    debug('sending ' + json.dumps(body))
    resp = server_conn.request('POST', '/results', data=json.dumps(body))
    debug(str(resp.status))
    if resp.status > 299:
        log(resp.read())

def run_check2(container_obj):

    send_check_result(container_obj, {'tasks-failed': 1, 'task-results': [{'blah': 'blah', 'result': 'blue'}]})

def run_check(container_obj):

    name = get_container_name(container_obj)
    container_routine_file = CFG['routine-file']
    routine_file = ROUTINES + name + '.json'
    debug('copying ' + container_routine_file + ' from container ' + name + ' to ' + routine_file)
    cmd = 'docker cp ' + name + ':' + container_routine_file + ' ' + routine_file
    debug('running cmd: ' + cmd)
    cp = ss_utils.run_cmd(cmd)
    if cp != 0:
        log('unable to find ' + container_routine_file + ' for ' + name)
        return 1

    host_cfg = get_host_cfg(container_obj)
    host = routine_runner.Host(host_cfg)
    routine = routine_runner.Routine(json.load(open(routine_file)))

    
    runner = routine_runner.Runner(routine, host)

    res = runner.run()

    send_check_result(container_obj, res)
    
def create_check_timer(container_obj, freq):

    name = get_container_name(container_obj)
    t = ss_utils.TaskTimer(freq, run_check, container_obj)
    CHECK_TIMERS[name] = t
    t.start()


if __name__ == '__main__':

    CFG = json.load(open('config.json'))
    HOSTNAME = socket.gethostname()
    ENV = os.environ.get('HOST_ENV', 'dev')
    CLI = client.Client(base_url='unix://var/run/docker.sock')
    CHECK_TIMERS = {}

    server_params = CFG['server']
    log('connecting to server: ' + json.dumps(server_params))
    server_conn = ss_utils.RestHelper(server_params['address'], server_params['port'], secure=server_params['secure'])
 
    t = ss_utils.TaskTimer(CFG['update-freq'], update)
    t.start()
