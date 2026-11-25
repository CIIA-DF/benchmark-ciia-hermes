import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const uuid = "[a-f0-9-]{36}";
const allowedGet = new RegExp(
  `^(processos|capabilities|conversations|conversations/${uuid}|runs/${uuid}|runs/${uuid}/events|artifacts/${uuid})$`,
);
const allowedPost = new RegExp(`^(conversations|conversations/${uuid}/messages)$`);
const maxBodyBytes = 1024 * 1024;
class BodyLimitError extends Error {}
class BodyTimeoutError extends Error {}

type ProxyCode = "not_found" | "forbidden" | "validation_error" |
  "payload_too_large" | "request_timeout" | "proxy_unavailable" | "upstream_timeout" | "upstream_unavailable";

function failure(status: number, message: string, code: ProxyCode) {
  return Response.json({ message, code }, { status, headers: { "Cache-Control": "no-store" } });
}

function timeoutMilliseconds(name: string, fallback: number): number {
  // Empty or blank value means unset, like ${VAR:-default} in infra/compose.yml.
  const raw = process.env[name]?.trim();
  const seconds = raw ? Number(raw) : fallback;
  const milliseconds = seconds * 1000;
  if (!Number.isFinite(milliseconds) || milliseconds <= 0 || milliseconds > 2_147_483_647)
    throw new Error("Invalid proxy timeout configuration");
  return milliseconds;
}

async function boundedBody(request: NextRequest, timeout: number): Promise<ArrayBuffer> {
  const declared = request.headers.get("content-length");
  if (declared && /^\d+$/.test(declared) && Number(declared) > maxBodyBytes)
    throw new BodyLimitError();
  if (!request.body) return new ArrayBuffer(0);
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new BodyTimeoutError()), timeout);
  });
  try {
    while (true) {
      const item = await Promise.race([reader.read(), deadline]);
      if (item.done) break;
      size += item.value.byteLength;
      if (size > maxBodyBytes) throw new BodyLimitError();
      chunks.push(item.value);
    }
  } catch (error) {
    void reader.cancel().catch(() => {});
    throw error;
  } finally {
    clearTimeout(timer);
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes.buffer;
}

async function proxy(
  request: NextRequest,
  { params }: { params: { path: string[] } },
) {
  const route = params.path.join("/");
  const allowed = request.method === "GET" ? allowedGet : allowedPost;
  if (!allowed.test(route)) return failure(404, "Rota indisponível.", "not_found");
  const host = request.headers.get("host") || "";
  // Este proxy representa um operador local. Não pode ser publicado como autenticação multiusuário.
  if (!/^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(host))
    return failure(403, "Chat configurado para uso local.", "forbidden");
  const origin = request.headers.get("origin");
  try {
    if (origin && (new URL(origin).host !== host || new URL(origin).protocol !== request.nextUrl.protocol))
      return failure(403, "Origem não autorizada.", "forbidden");
  } catch {
    return failure(403, "Origem inválida.", "forbidden");
  }
  if (request.headers.get("sec-fetch-site") === "cross-site")
    return failure(403, "Origem não autorizada.", "forbidden");
  if (request.method === "POST" && !origin)
    return failure(403, "Origem necessária.", "forbidden");
  const token = process.env.BACKEND_OPERATOR_TOKEN;
  if (!token) return failure(503, "Configure o chat seguindo docs/04-operacoes/chat.md.", "proxy_unavailable");
  const headers = new Headers({ Authorization: `Bearer ${token}` });
  const cursor = request.headers.get("last-event-id");
  if (cursor) headers.set("Last-Event-ID", cursor);
  let base: URL;
  let headerTimeout: number;
  let idleTimeout: number;
  try {
    base = new URL(process.env.BACKEND_URL || "http://127.0.0.1:8000");
    if (!["http:", "https:"].includes(base.protocol) || base.username || base.password || base.search || base.hash)
      throw new Error("Invalid backend URL");
    headerTimeout = timeoutMilliseconds("BACKEND_PROXY_TIMEOUT_SECONDS", 20);
    idleTimeout = timeoutMilliseconds("BACKEND_PROXY_IDLE_TIMEOUT_SECONDS", 30);
  } catch {
    return failure(503, "Configuração de transporte inválida.", "proxy_unavailable");
  }
  let body: ArrayBuffer | undefined;
  if (request.method === "POST") {
    try {
      body = await boundedBody(request, headerTimeout);
    } catch (error) {
      if (error instanceof BodyLimitError)
        return failure(413, "Mensagem muito grande.", "payload_too_large");
      if (error instanceof BodyTimeoutError)
        return failure(408, "Tempo de leitura da mensagem excedido.", "request_timeout");
      return failure(400, "Não foi possível ler a mensagem.", "validation_error");
    }
    headers.set("Content-Type", "application/json");
  }
  const abort = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let timedOut = false;
  const cancel = () => abort.abort();
  const arm = (duration: number) => {
    clearTimeout(timer);
    timer = setTimeout(() => { timedOut = true; abort.abort(); }, duration);
  };
  const cleanup = () => {
    clearTimeout(timer);
    request.signal.removeEventListener("abort", cancel);
  };
  request.signal.addEventListener("abort", cancel, { once: true });
  if (request.signal.aborted) cancel();
  arm(headerTimeout);
  try {
    const response = await fetch(`${base.toString().replace(/\/$/, "")}/${route}${request.nextUrl.search}`, {
      method: request.method, headers, body, cache: "no-store", redirect: "manual", signal: abort.signal,
    });
    const responseHeaders = new Headers({
      "Content-Type": response.headers.get("content-type") || "application/json",
      "Cache-Control": "no-store", "X-Accel-Buffering": "no",
    });
    for (const name of ["WWW-Authenticate", "Allow", "Retry-After"]) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    if (!response.body) {
      cleanup();
      return new Response(null, { status: response.status, headers: responseHeaders });
    }
    const reader = response.body.getReader();
    const sse = responseHeaders.get("content-type")?.includes("text/event-stream");
    arm(idleTimeout);
    let finished = false;
    const stream = new ReadableStream<Uint8Array>({
      async pull(controller) {
        try {
          const item = await reader.read();
          if (finished) return;
          if (item.done) {
            finished = true;
            cleanup();
            controller.close();
          } else {
            arm(idleTimeout);
            controller.enqueue(item.value);
          }
        } catch {
          if (finished) return;
          finished = true;
          cleanup();
          abort.abort();
          if (sse) {
            const code: ProxyCode = timedOut ? "upstream_timeout" : "upstream_unavailable";
            controller.enqueue(new TextEncoder().encode(
              `event: stream_error\ndata: ${JSON.stringify({ message: "Fluxo interrompido.", code })}\n\n`,
            ));
            controller.close();
          } else controller.error(new Error("Backend indisponível."));
        }
      },
      async cancel() {
        finished = true;
        cleanup();
        abort.abort();
        await reader.cancel().catch(() => {});
      },
    });
    return new Response(stream, { status: response.status, headers: responseHeaders });
  } catch {
    cleanup();
    abort.abort();
    return failure(503, "Backend indisponível. Confira os serviços locais.",
      timedOut ? "upstream_timeout" : "upstream_unavailable");
  }
}

export { proxy as GET, proxy as POST };
