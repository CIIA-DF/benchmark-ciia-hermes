// Execute the actual Next route with synthetic requests and controlled upstreams.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const http = require('node:http');
const root = process.argv[3];
const ts = require(path.join(root, 'portal/node_modules/typescript'));
const { NextRequest } = require(path.join(root, 'portal/node_modules/next/server'));
function load(file) {
  const module = new Module(file);
  module.filename = file;
  module.paths = Module._nodeModulePaths(path.dirname(file));
  module._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, file);
  return module.exports;
}
const route = load(path.join(root, 'portal/app/api/chat/[...path]/route.ts'));
process.env.BACKEND_OPERATOR_TOKEN = 'synthetic-I3-server-credential';
process.env.BACKEND_URL = 'http://127.0.0.1:1';
process.env.BACKEND_PROXY_TIMEOUT_SECONDS = '2';
process.env.BACKEND_PROXY_IDLE_TIMEOUT_SECONDS = '1';
function request(method = 'GET', resource = 'capabilities', options = {}) {
  return new NextRequest(`http://localhost:3000/api/chat/${resource}`, {
    method, ...options,
    headers: { host: 'localhost:3000', ...(method === 'POST' ? { origin: 'http://localhost:3000' } : {}),
      ...options.headers },
  });
}
function proxy(req, resource = 'capabilities') {
  return route[req.method](req, { params: { path: resource.split('/') } });
}
async function upstream(handler) {
  const server = http.createServer(handler);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  process.env.BACKEND_URL = `http://127.0.0.1:${server.address().port}`;
  return async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  };
}
async function waitFor(condition) {
  const deadline = Date.now() + 2000;
  while (!condition()) {
    assert.ok(Date.now() < deadline, 'Upstream did not observe cancellation');
    await new Promise(resolve => setTimeout(resolve, 10));
  }
}

async function main() {
  if (process.argv[2] === 'chunk_body') {
    let pulled = 0;
    global.fetch = () => assert.fail('Oversize must not reach backend');
    const body = new ReadableStream({ pull(controller) {
      pulled++;
      controller.enqueue(new Uint8Array(400_000));
      if (pulled === 10) controller.close();
    }});
    const response = await proxy(request('POST', 'conversations', {
      body, duplex: 'half', headers: { 'content-length': '1' },
    }), 'conversations');
    assert.equal(response.status, 413);
    assert.ok(pulled <= 5, `Read ${pulled} chunks before rejecting`);
  } else if (process.argv[2] === 'body_timeout') {
    let cancelled = false;
    process.env.BACKEND_PROXY_TIMEOUT_SECONDS = '0.03';
    global.fetch = () => assert.fail('Stalled body reached backend');
    const body = new ReadableStream({ cancel() { cancelled = true; } });
    const response = await proxy(request('POST', 'conversations', { body, duplex: 'half' }), 'conversations');
    assert.equal(response.status, 408);
    assert.equal((await response.json()).code, 'request_timeout');
    assert.ok(cancelled);
  } else if (process.argv[2] === 'wire_sse') {
    process.env.BACKEND_PROXY_TIMEOUT_SECONDS = '10';
    process.env.BACKEND_PROXY_IDLE_TIMEOUT_SECONDS = '10';
    const resource = 'runs/11111111-1111-4111-8111-111111111111/events';
    let ended = false, wire, finish;
    const stop = await upstream((req, res) => {
      wire = { url: req.url, headers: req.headers };
      res.writeHead(200, { 'content-type': 'text/event-stream',
        authorization: 'PRIVATE-UPSTREAM', 'set-cookie': 'PRIVATE-COOKIE' });
      res.write('id: 8\nevent: status\ndata: {"text":"Synthetic"}\n\n');
      finish = () => { ended = true; res.end('id: 9\nevent: done\ndata: {"status":"succeeded"}\n\n'); };
    });
    try {
      const response = await proxy(request('GET', resource + '?after=3', { headers: {
        'last-event-id': '7', authorization: 'PRIVATE-BROWSER', cookie: 'PRIVATE-BROWSER',
        'x-run-token': 'PRIVATE-LEASE', 'x-forwarded-for': 'PRIVATE-FORWARDED',
      }}), resource);
      const reader = response.body.getReader();
      const first = await reader.read();
      assert.ok(!ended, 'Proxy buffered SSE until terminal response');
      finish();
      let text = new TextDecoder().decode(first.value);
      while (true) { const item = await reader.read(); if (item.done) break; text += new TextDecoder().decode(item.value); }
      assert.ok(text.includes('id: 8') && text.includes('id: 9') && text.includes('event: done'), text);
      assert.equal(wire.headers.authorization, 'Bearer synthetic-I3-server-credential');
      assert.equal(wire.headers['last-event-id'], '7');
      assert.equal(wire.url, '/' + resource + '?after=3');
      for (const key of ['cookie', 'x-run-token', 'x-forwarded-for']) assert.equal(wire.headers[key], undefined);
      assert.equal(response.headers.get('authorization'), null);
      assert.equal(response.headers.get('set-cookie'), null);
      assert.equal(response.headers.get('cache-control'), 'no-store');
      assert.equal(response.headers.get('x-accel-buffering'), 'no');
    } finally { await stop(); }
  } else if (process.argv[2] === 'header_timeout') {
    const stop = await upstream(() => {});
    process.env.BACKEND_PROXY_TIMEOUT_SECONDS = '0.05';
    try {
      const response = await proxy(request());
      assert.equal(response.status, 503);
      assert.equal((await response.json()).code, 'upstream_timeout');
      assert.equal(response.headers.get('cache-control'), 'no-store');
    } finally { await stop(); }
  } else if (['idle_timeout', 'disconnect', 'request_abort'].includes(process.argv[2])) {
    const resource = 'runs/11111111-1111-4111-8111-111111111111/events';
    let closed = false;
    const stop = await upstream((req, res) => {
      res.writeHead(200, { 'content-type': 'text/event-stream' });
      res.write('event: status\ndata: {"text":"Synthetic"}\n\n');
      res.on('close', () => { closed = true; });
    });
    process.env.BACKEND_PROXY_IDLE_TIMEOUT_SECONDS = process.argv[2] === 'idle_timeout' ? '0.05' : '10';
    const abort = new AbortController();
    try {
      const response = await proxy(request('GET', resource, { signal: abort.signal }), resource);
      assert.equal(response.status, 200);
      const reader = response.body.getReader();
      const first = await reader.read();
      assert.ok(new TextDecoder().decode(first.value).includes('event: status'));
      if (process.argv[2] === 'disconnect') await reader.cancel();
      else {
        if (process.argv[2] === 'request_abort') abort.abort();
        let text = '';
        while (true) { const item = await reader.read(); if (item.done) break; text += new TextDecoder().decode(item.value); }
        assert.equal((text.match(/event: stream_error/g) || []).length, 1);
        assert.ok(text.includes(process.argv[2] === 'idle_timeout' ? 'upstream_timeout' : 'upstream_unavailable'));
      }
      await waitFor(() => closed);
    } finally { await stop(); }
  } else if (process.argv[2] === 'status_headers') {
    global.fetch = async () => new Response(JSON.stringify({ message: 'Synthetic denial' }), {
      status: 401, headers: { 'WWW-Authenticate': 'Bearer', Allow: 'GET', 'Retry-After': '3',
        'content-type': 'application/json', authorization: 'PRIVATE' },
    });
    const response = await proxy(request());
    assert.equal(response.status, 401);
    for (const [key, value] of [['www-authenticate', 'Bearer'], ['allow', 'GET'], ['retry-after', '3']])
      assert.equal(response.headers.get(key), value);
    assert.equal(response.headers.get('authorization'), null);
    await response.json();
  } else if (process.argv[2] === 'blank_timeout') {
    // Empty or blank variables fall back to the documented defaults (20 s / 30 s), not 0.
    global.fetch = async () => new Response(JSON.stringify({ executors: [] }), {
      status: 200, headers: { 'content-type': 'application/json' },
    });
    for (const blank of ['', '   ']) {
      process.env.BACKEND_PROXY_TIMEOUT_SECONDS = blank;
      process.env.BACKEND_PROXY_IDLE_TIMEOUT_SECONDS = blank;
      const response = await proxy(request());
      assert.equal(response.status, 200);
      await response.json();
    }
  } else if (process.argv[2] === 'guards') {
    global.fetch = () => assert.fail('Rejected request reached backend');
    const requests = [request('GET', 'capabilities', { headers: { host: 'external.invalid' } }),
      request('GET', 'capabilities', { headers: { origin: 'https://localhost:3000' } }),
      request('GET', 'capabilities', { headers: { origin: 'http://external.invalid' } }),
      request('GET', 'capabilities', { headers: { 'sec-fetch-site': 'cross-site' } })];
    for (const req of requests) {
      const response = await proxy(req);
      assert.equal(response.status, 403);
      assert.equal(response.headers.get('cache-control'), 'no-store');
    }
    const missing = await proxy(request('POST', 'conversations', { headers: { origin: '' } }), 'conversations');
    assert.equal(missing.status, 403);
    assert.equal((await proxy(request('GET', 'tools/salvar_minuta'), 'tools/salvar_minuta')).status, 404);
  } else if (process.argv[2] === 'declared_size') {
    global.fetch = () => assert.fail('Oversize reached backend');
    const response = await proxy(request('POST', 'conversations', { headers: { 'content-length': '1048577' } }), 'conversations');
    assert.equal(response.status, 413);
  } else if (process.argv[2] === 'exact_limit') {
    global.fetch = async (_url, options) => {
      assert.equal(options.body.byteLength, 1048576);
      assert.equal(options.headers.get('content-type'), 'application/json');
      return Response.json({ status: 'synthetic' });
    };
    const response = await proxy(request('POST', 'conversations', {
      body: new Uint8Array(1048576), headers: { 'content-length': '1' },
    }), 'conversations');
    assert.equal(response.status, 200);
    await response.json();
  } else if (process.argv[2] === 'configuration') {
    global.fetch = () => assert.fail('Invalid configuration reached fetch');
    for (const base of ['file:///PRIVATE', 'http://user:PRIVATE@localhost', 'http://localhost?token=PRIVATE']) {
      process.env.BACKEND_URL = base;
      const response = await proxy(request());
      assert.equal(response.status, 503);
      assert.ok(!(await response.text()).includes('PRIVATE'));
    }
    process.env.BACKEND_URL = 'http://127.0.0.1:1';
    for (const timeout of ['nan', 'Infinity', '0', '-1', '1e100']) {
      process.env.BACKEND_PROXY_TIMEOUT_SECONDS = timeout;
      assert.equal((await proxy(request())).status, 503);
    }
  } else if (process.argv[2] === 'upstream_failure') {
    global.fetch = async () => { throw new Error('PRIVATE synthetic socket details'); };
    const response = await proxy(request());
    assert.equal(response.status, 503);
    assert.ok(!(await response.text()).includes('PRIVATE'));
  } else {
    assert.fail('Unknown synthetic scenario');
  }
  console.log('PASS ' + process.argv[2]);
}
main().catch(error => { console.error(error); process.exitCode = 1; });
