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
import traceback

# config
DEBUG = True
CFG_FILE = 'config.json'
ROUTINES = 'routines_tmp/'
DEFAULT_PORT = 8080
CHECK_NAME = 'monitor'


# helpers

def log(msg):
    print(threading.current_thread().name + ': ' + msg)

def debug(msg):
    if DEBUG:
        log('DEBUG: ' + msg)

def get_container_name(container_obj):
    return container_obj['Names'][0][1:]

def get_host(container_obj):

    name = get_container_name(container_obj)
    inspect = CLI.inspect_container(container_obj)
    ip = inspect['NetworkSettings']['IPAddress']

    cfg = {
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

    return routine_runner.HostSet(cfg)

def get_routine(tasks_file):
    with open(tasks_file) as f:
        tasks = json.load(f)
        f.close()
    cfg = {
        'name': 'monitor',
        'tasks': tasks
        }

    return routine_runner.Routine(cfg)

def run_routine(routine, host):
    return routine_runner.Runner(routine, host).run()

def get_check_freq(container_name):

    for freq in CFG['frequencies']:
        if re.match('^'+freq['pattern']+'$', container_name):
            return freq['seconds']
    return None

# actions

def update():

    debug('updating server with current container list state')

    try:
        # get updated list of containers running on this host
        containers = CLI.containers()
        container_names = [ get_container_name(c) for c in containers ]

        # get updated list of clients configured on the server that were created from this host
        all_clients = json.loads(server_conn.request('GET', '/clients').read())
        clients = [ client for client in all_clients if client['address'] == HOSTNAME ]
        client_names = [ client['name'] for client in clients ]

        for container in containers:
            name = get_container_name(container)
            #debug('getting configured check freq for: ' + name)
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

        # unpause all check timers in case any were paused
        for name,timer in CHECK_TIMERS.items():
            timer.paused = False

    except:
        traceback.print_exc()
        log('error in syncing containers running on this host with clients defined in server, pausing all check timer threads until resolved')
        # pause all check timers
        for name,timer in CHECK_TIMERS.items():
            timer.paused = True
        return 1

def delete_client(name):

    resp = server_conn.request('DELETE', '/clients/' + name)
    debug('response: ' + str(resp.status))

def add_client(name):

    data = {
        'name': name,
        'address': HOSTNAME,
        'subscriptions': [],
        'environment': ENV
        }

    resp = server_conn.request('POST', '/clients', data=json.dumps(data))
    debug('response: ' + str(resp.status))

def send_check_result(container_obj, routine_result, warn=None):

    if warn:
        output = warn
        status = 1
    else:
        output = 'OK'
        status = 0
        if routine_result['tasks-failed'] != 0:
            output = json.dumps([ res for res in routine_result['task-results'] if res['result'] not in ('SUCCESS', 'SKIPPED')])
            status = 2

    name = get_container_name(container_obj)
    body = {
        'source': name,
        'name': CHECK_NAME,
        'output': output,
        'status': status
        }

    debug('sending ' + json.dumps(body))
    resp = server_conn.request('POST', '/results', data=json.dumps(body))
    debug('response: ' + str(resp.status))
    if resp.status > 299:
        log('error returned when trying to post check result for ' + name + ':' + resp.read())

def run_check_fake(container_obj):

    send_check_result(container_obj, {'tasks-failed': 1, 'task-results': [{'blah': 'blah', 'result': 'blue'}]})

def run_check(container_obj):

    try:
        name = get_container_name(container_obj)
        container_routine_file = CFG['routine-file']
        routine_file = ROUTINES + name + '.json'
        debug('copying ' + container_routine_file + ' from container ' + name + ' to ' + routine_file)
        cmd = 'docker cp ' + name + ':' + container_routine_file + ' ' + routine_file
        debug('running cmd: ' + cmd)
        cp = ss_utils.run_cmd(cmd.strip())
        if cp[0] != 0:
            log('unable to find ' + container_routine_file + ' for ' + name)
            send_check_result(container_obj, None, warn='unable to find ' + container_routine_file)
            return 1

        host = get_host(container_obj)
        routine = get_routine(routine_file)
    
        res = run_routine(routine, host)

        send_check_result(container_obj, res)
    except:
        traceback.print_exc()
        return 1
    
def create_check_timer(container_obj, freq):

    name = get_container_name(container_obj)
    t = ss_utils.TaskTimer(freq, run_check, container_obj)
    CHECK_TIMERS[name] = t
    t.start()


if __name__ == '__main__':

    log('loading agent config ' + CFG_FILE)
    CFG = ss_utils.load_json_template(CFG_FILE, os.environ)
    HOSTNAME = CFG['hostname']
    ENV = os.environ.get('HOST_ENV', 'dev')
    CLI = client.Client(base_url='unix://var/run/docker.sock')
    if not os.path.exists(ROUTINES):
        log('creating dir: ' + ROUTINES)
        os.mkdir(ROUTINES)
    CHECK_TIMERS = {}

    server_params = CFG['server']
    log('connecting to server: ' + json.dumps(server_params))
    server_conn = ss_utils.RestHelper(server_params['address'], server_params['port'], secure=server_params['secure'])
 
    t = ss_utils.TaskTimer(CFG['update-freq'], update)
    t.start()
