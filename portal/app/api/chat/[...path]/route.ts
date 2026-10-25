import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const uuid = "[a-f0-9-]{36}";
const allowedGet = new RegExp(
  `^(processos|capabilities|conversations|conversations/${uuid}|runs/${uuid}|runs/${uuid}/events|artifacts/${uuid})$`,
);
const allowedPost = new RegExp(
  `^(conversations|conversations/${uuid}/messages)$`,
);

async function proxy(
  request: NextRequest,
  { params }: { params: { path: string[] } },
) {
  const route = params.path.join("/");
  const allowed = request.method === "GET" ? allowedGet : allowedPost;
  if (!allowed.test(route))
    return Response.json({ message: "Rota indisponível." }, { status: 404 });
  const host = request.headers.get("host") || "";
  // Este proxy representa um operador local. Não pode ser publicado como autenticação multiusuário.
  if (!/^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(host)) {
    return Response.json(
      { message: "Chat configurado para uso local." },
      { status: 403 },
    );
  }
  const origin = request.headers.get("origin");
  let originHost = "";
  try {
    originHost = origin ? new URL(origin).host : "";
  } catch {
    return Response.json({ message: "Origem inválida." }, { status: 403 });
  }
  if (
    (origin && originHost !== host) ||
    request.headers.get("sec-fetch-site") === "cross-site"
  ) {
    return Response.json(
      { message: "Origem não autorizada." },
      { status: 403 },
    );
  }
  if (request.method === "POST" && !origin) {
    return Response.json({ message: "Origem necessária." }, { status: 403 });
  }
  const token = process.env.BACKEND_OPERATOR_TOKEN;
  if (!token)
    return Response.json(
      { message: "Configure o chat seguindo docs/04-operacoes/chat.md." },
      { status: 503 },
    );
  const headers = new Headers({ Authorization: `Bearer ${token}` });
  const cursor = request.headers.get("last-event-id");
  if (cursor) headers.set("Last-Event-ID", cursor);
  let body: string | undefined;
  if (request.method === "POST") {
    body = await request.text();
    if (Buffer.byteLength(body) > 650_000)
      return Response.json(
        { message: "Mensagem muito grande." },
        { status: 413 },
      );
    headers.set("Content-Type", "application/json");
  }
  try {
    const base = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    const response = await fetch(`${base}/${route}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: request.signal,
    });
    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
      },
    });
  } catch {
    return Response.json(
      { message: "Backend indisponível. Confira os serviços locais." },
      { status: 503 },
    );
  }
}

export { proxy as GET, proxy as POST };
