"""End-to-end tests of `ihxjava lsp` against tests/fake_server.py.

Run with: python3 -m unittest discover tests
The Neovim test runs when `nvim` (0.11+) is on PATH, or when $NVIM_BIN points at one.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent / 'ihxjava'
NVIM = os.environ.get('NVIM_BIN') or shutil.which('nvim')


class Client:
    def __init__(self, env, cwd):
        self.proc = subprocess.Popen(
            [sys.executable, str(TOOL), 'lsp'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=cwd,
        )
        self.next_id = 0

    def send(self, message):
        body = json.dumps(message).encode()
        self.proc.stdin.write(b'Content-Length: %d\r\n\r\n' % len(body) + body)
        self.proc.stdin.flush()

    def read(self):
        headers = {}
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise EOFError(self.proc.stderr.read().decode())
            line = line.strip()
            if not line:
                break
            key, _, value = line.decode().partition(':')
            headers[key.lower()] = value.strip()
        return json.loads(self.proc.stdout.read(int(headers['content-length'])))

    def request(self, method, params=None):
        self.next_id += 1
        self.send({'jsonrpc': '2.0', 'id': self.next_id, 'method': method, 'params': params})
        response = self.read()
        assert response['id'] == self.next_id, response
        return response

    def notify(self, method, params):
        self.send({'jsonrpc': '2.0', 'method': method, 'params': params})

    def close(self):
        self.request('shutdown')
        self.notify('exit', None)
        code = self.proc.wait(timeout=10)
        self.stderr = self.proc.stderr.read().decode()
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            stream.close()
        return code


class BridgeTest(unittest.TestCase):
    def setUp(self):
        # Resolved, because macOS puts temporary directories behind a /var -> /private/var symlink.
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.env = dict(os.environ)
        for var in ('XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
            self.env[var] = str(self.tmp / var.lower())
        self.env['IJ_LAUNCHER_DEBUG'] = '1'
        self.project = self.tmp / 'my project'
        self.project.mkdir()

        server = self.tmp / 'xdg_data_home' / 'ihxjava' / 'server' / '1.0'
        (server / 'bin').mkdir(parents=True)
        launcher = server / 'bin' / 'intellij-server'
        shutil.copy(HERE / 'fake_server.py', launcher)
        launcher.chmod(0o755)
        eula = server / 'EULA.txt'
        eula.write_text('Agreement text\n')
        self.eula_hash = hashlib.sha256(eula.read_bytes()).hexdigest()[:16]
        self.write(self.tmp / 'xdg_data_home' / 'ihxjava' / 'installed.json', {
            'serverVersion': '1.0', 'extensionVersion': '1.0', 'target': 'linux-x64',
            'serverDir': str(server), 'launcher': str(launcher), 'eula': str(eula),
        })

    def tearDown(self):
        for f in self.tmp.rglob('*'):
            if f.is_file():
                f.chmod(0o644)
        shutil.rmtree(self.tmp)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def configure(self, **config):
        self.write(self.tmp / 'xdg_config_home' / 'ihxjava' / 'config.json', config)

    def initialize(self, client, options=None):
        params = {'rootUri': self.project.as_uri(), 'capabilities': {}}
        if options is not None:
            params['initializationOptions'] = options
        return client.request('initialize', params)

    def test_launch_arguments_environment_and_options(self):
        self.configure(eulaAccepted=self.eula_hash, region='europe', dataSharing='anonymous')
        client = Client(self.env, self.tmp)
        info = self.initialize(client, {'buildTool': 'maven', 'defaultSdk': '/jdk'})['result']['test']

        argv = info['argv']
        self.assertEqual(argv[:3], ['--stdio', '--eula', self.eula_hash])
        self.assertEqual(argv[3], '--system-path')
        self.assertTrue(argv[4].startswith(str(self.tmp / 'xdg_cache_home' / 'ihxjava' / 'system' / '1.0')))
        self.assertEqual(Path(info['cwd']), self.project)
        self.assertEqual(info['region'], 'europe')
        self.assertEqual(info['dataSharing'], 'anonymous')
        self.assertIsNone(info['launcherDebug'])
        self.assertEqual(info['initializationOptions'], {
            'buildTools': {self.project.as_uri(): 'maven'},
            'projects': [],
            'disableRocksDBWriteAheadLog': False,
            'lazyIntentions': True,
            'defaultSdk': '/jdk',
        })
        self.assertEqual(client.close(), 0)
        self.assertEqual(client.stderr, 'fake server warning\n')

    def test_library_locations_become_decompiled_files(self):
        self.configure(eulaAccepted=self.eula_hash, region='europe')
        client = Client(self.env, self.tmp)
        self.initialize(client)

        location = client.request('textDocument/definition', {})['result'][0]
        self.assertTrue(location['uri'].startswith('file://'), location)
        path = Path(location['uri'][len('file://'):])
        self.assertEqual(path.name, 'Foo_Inner.java')
        self.assertIn('class Foo', path.read_text())
        self.assertFalse(os.access(path, os.W_OK))
        self.assertEqual(location['range']['start']['line'], 3)

        # Helix opens the file; the server must see the original jar: URI, however Helix encodes it.
        client.notify('textDocument/didOpen', {'textDocument': {
            'uri': location['uri'].replace('_', '%5F'), 'languageId': 'java', 'version': 0,
            'text': path.read_text(),
        }})
        self.assertEqual(client.request('test/opened')['result'],
                         ['jar:file:///libs/acme-1.0.jar!/com/acme/Foo$Inner.class'])
        self.assertEqual(client.close(), 0)

    def test_setup_problems_are_reported_to_helix(self):
        self.configure(region='europe')
        client = Client(self.env, self.tmp)
        response = self.initialize(client)
        self.assertIn('ihxjava setup', response['error']['message'])
        self.assertEqual(client.proc.wait(timeout=10), 1)
        for stream in (client.proc.stdin, client.proc.stdout, client.proc.stderr):
            stream.close()

    @unittest.skipUnless(NVIM, 'nvim is not installed')
    def test_neovim_plugin(self):
        self.configure(eulaAccepted=self.eula_hash, region='europe')
        (self.project / 'settings.gradle').write_text('')
        (self.project / 'src').mkdir()
        (self.project / 'src' / 'Main.java').write_text('class Main { Foo.Inner x; }\n')
        result = subprocess.run(
            [NVIM, '--headless', '--clean', '-l', str(HERE / 'nvim_test.lua'),
             str(HERE.parent), str(self.project), sys.executable, str(TOOL)],
            env=self.env, cwd=self.project, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == '__main__':
    unittest.main()
