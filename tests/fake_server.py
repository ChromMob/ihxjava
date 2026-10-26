#!/usr/bin/env python3
"""Stands in for bin/intellij-server in tests: speaks just enough LSP over stdio."""

import json
import os
import sys

JAR_URI = 'jar:file:///libs/acme-1.0.jar!/com/acme/Foo$Inner.class'


def read():
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        key, _, value = line.decode().partition(':')
        headers[key.lower()] = value.strip()
    return json.loads(sys.stdin.buffer.read(int(headers['content-length'])))


def send(message):
    body = json.dumps(message).encode()
    sys.stdout.buffer.write(b'Content-Length: %d\r\n\r\n' % len(body) + body)
    sys.stdout.buffer.flush()


# What the real launcher prints on start, plus a line that must still reach the editor.
sys.stderr.write('IJ_JAVA_OPTIONS=\nidea.config.path=/x/config\nidea.system.path=/x/system\n'
                 'Log file: /x/system/log/intellij-server.log\nfake server warning\n')
sys.stderr.flush()

opened = []
while (message := read()) is not None:
    method = message.get('method')
    reply = lambda result: send({'jsonrpc': '2.0', 'id': message['id'], 'result': result})
    if method == 'initialize':
        reply({
            'capabilities': {},
            'test': {
                'argv': sys.argv[1:],
                'cwd': os.getcwd(),
                'region': os.environ.get('INTELLIJ_REGION'),
                'dataSharing': os.environ.get('INTELLIJ_DATA_SHARING'),
                'launcherDebug': os.environ.get('IJ_LAUNCHER_DEBUG'),
                'initializationOptions': message['params'].get('initializationOptions'),
            },
        })
    elif method == 'textDocument/definition':
        reply([{'uri': JAR_URI, 'range': {'start': {'line': 3, 'character': 6}, 'end': {'line': 3, 'character': 9}}}])
    elif method == 'workspace/executeCommand' and message['params']['command'] == 'decompile':
        assert message['params']['arguments'] == [JAR_URI]
        reply({'code': 'package com.acme;\nclass Foo { class Inner {} }\n', 'language': 'JAVA'})
    elif method == 'textDocument/didOpen':
        opened.append(message['params']['textDocument']['uri'])
    elif method == 'test/opened':
        reply(opened)
    elif method == 'shutdown':
        reply(None)
    elif method == 'exit':
        sys.exit(0)
