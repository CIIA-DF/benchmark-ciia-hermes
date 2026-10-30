"use client";

import Link from "next/link";
import {
  FormEvent,
  Fragment,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import styles from "./chat.module.css";

type Process = {
  process_id: string;
  title: string;
  corpus_version: string;
  requirements_version: string;
  export_completeness: string;
};
type Source = {
  kind?: string;
  document_id?: string;
  chunk_id?: string;
  page?: number;
  process_id?: string;
  corpus_version?: string;
};
type Run = {
  run_id: string;
  status: string;
  executor: string;
  partial_answer: string;
  artifacts: { artifact_id: string; tool: string }[];
  last_event_id: number;
  result?: { answer?: string; sources?: Source[]; error_code?: string };
};
type Message = {
  message_id: string;
  role: string;
  content: string;
  run_id: string;
};
type Conversation = {
  conversation_id: string;
  participant_id: string | null;
  process_id: string;
  corpus_version: string;
  requirements_version: string;
  executor: string;
  created_at: number;
  messages: Message[];
  runs: Run[];
};
type Capabilities = {
  can_write: boolean;
  executors: {
    name: string;
    available: boolean;
    enabled: boolean;
    worker_recent: boolean;
    last_seen_at: number | null;
    model: string | null;
    configuration_known: boolean;
  }[];
};

async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/chat/${path}`, {
    cache: "no-store",
    ...(body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {}),
  });
  const value = await response.json();
  if (!response.ok)
    throw new Error(
      value.message || "Não foi possível concluir a solicitação.",
    );
  return value;
}

const active = (run: Run) =>
  run.status === "queued" || run.status === "running";

const toolProgress: Record<string, string> = {
  consultar_processo: "Consultando o processo",
  buscar_documentos: "Buscando trechos nos documentos",
  ler_documento: "Lendo as fontes",
  consultar_requisitos: "Conferindo o checklist",
  registrar_pendencia: "Registrando a pendência",
  salvar_minuta: "Salvando a minuta",
};

const failureReason: Record<string, string> = {
  adapter_error: "O agente encontrou um erro e encerrou a execução.",
  context_limit: "A conversa atingiu o limite de contexto. Inicie uma nova conversa.",
  model_timeout: "O modelo não respondeu dentro do tempo limite.",
  worker_timeout: "O agente parou de responder e a reserva da execução expirou.",
  queue_timeout: "O tempo de espera na fila expirou antes de um agente iniciar a execução.",
  event_limit: "A execução atingiu o limite de eventos e foi encerrada.",
};

// Reconexões seguidas sem receber evento: espera 1 s, 2 s, 4 s e 8 s antes de desistir.
const MAX_RECONNECTS = 4;

export default function ChatPage() {
  const [participant, setParticipant] = useState("");
  const [processes, setProcesses] = useState<Process[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [selectedProcess, setSelectedProcess] = useState(0);
  const [executor, setExecutor] = useState("simulation");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState("Pronto para conversar");
  const [streamRun, setStreamRun] = useState<Run | null>(null);
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const stream = useRef<EventSource | null>(null);
  const tail = useRef<HTMLDivElement | null>(null);
  const pending = useRef<{
    conversation: string;
    content: string;
    key: string;
  } | null>(null);
  const selectionVersion = useRef(0);
  const streamSnapshot = useRef<Run | null>(null);
  const followResponse = useRef(true);
  const reconnects = useRef(0);

  const loadConversation = useCallback(async (id: string) => {
    const version = ++selectionVersion.current;
    stream.current?.close();
    try {
      const value = await api<Conversation>(`conversations/${id}`);
      if (version !== selectionVersion.current) return;
      reconnects.current = 0;
      setConversation(value);
      const currentRun = value.runs.find(active);
      setStreamRun(currentRun || null);
      setProgress(
        currentRun
          ? currentRun.status === "queued"
            ? "Aguardando agente"
            : "Respondendo"
          : "Pronto para conversar",
      );
      followResponse.current = true;
      window.localStorage.setItem("ciia-conversation", id);
      setError("");
    } finally {
      // Reabre mesmo com IDs iguais; em falha, retoma o snapshot anterior.
      if (version === selectionVersion.current)
        setConnectionAttempt((n) => n + 1);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    let participantId: string;
    try {
      const saved = window.localStorage.getItem("ciia-participant");
      participantId = saved && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(saved)
        ? saved : crypto.randomUUID();
      window.localStorage.setItem("ciia-participant", participantId);
      setParticipant(participantId);
    } catch {
      setError("Permita o armazenamento local para identificar suas conversas neste navegador.");
      return;
    }
    Promise.all([
      api<Process[]>("processos"),
      api<Capabilities>("capabilities"),
      api<Conversation[]>(`conversations?participant_id=${participantId}`),
    ])
      .then(async ([items, caps, history]) => {
        if (!mounted) return;
        setProcesses(items);
        setCapabilities(caps);
        setConversations(history);
        const saved = window.localStorage.getItem("ciia-conversation");
        if (saved && history.some((c) => c.conversation_id === saved))
          await loadConversation(saved);
      })
      .catch((e) => {
        if (mounted) setError(e.message);
      });
    return () => {
      mounted = false;
      stream.current?.close();
    };
  }, [loadConversation]);

  const runId = streamRun?.run_id;
  const conversationId = conversation?.conversation_id;
  useEffect(() => {
    streamSnapshot.current = streamRun;
  }, [streamRun]);
  useEffect(() => {
    const snapshot = streamSnapshot.current;
    if (!runId || !snapshot) return;
    let latest = snapshot.last_event_id;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const source = new EventSource(
      `/api/chat/runs/${runId}/events?after=${latest}`,
    );
    stream.current = source;
    const accept = (event: MessageEvent) => {
      const id = Number(event.lastEventId);
      if (id <= latest) return false;
      latest = id;
      reconnects.current = 0;
      return true;
    };
    source.addEventListener("text_delta", (event) => {
      const item = event as MessageEvent;
      if (!accept(item)) return;
      const value = JSON.parse(item.data);
      setProgress("Respondendo");
      setStreamRun(
        (current) =>
          current && {
            ...current,
            last_event_id: latest,
            partial_answer: current.partial_answer + value.text,
          },
      );
    });
    source.addEventListener("status", (event) => {
      const item = event as MessageEvent;
      if (accept(item)) setProgress(JSON.parse(item.data).text);
    });
    source.addEventListener("tool", (event) => {
      const item = event as MessageEvent;
      if (accept(item))
        setProgress(
          toolProgress[JSON.parse(item.data).tool] ||
            "Processando a solicitação",
        );
    });
    source.addEventListener("done", () => {
      closed = true;
      source.close();
      if (conversationId)
        loadConversation(conversationId).catch((e) => setError(e.message));
      setProgress("Execução encerrada");
    });
    const reconnect = () => {
      source.close();
      if (closed) return;
      if (reconnects.current >= MAX_RECONNECTS) {
        closed = true;
        setProgress("Conexão com a execução perdida");
        setError(
          "Conexão com a execução perdida. Selecione a conversa novamente para retomar o acompanhamento.",
        );
        return;
      }
      const delay = 1000 * 2 ** reconnects.current;
      reconnects.current += 1;
      setProgress("Reconectando à execução…");
      // Reabre a partir de um snapshot consistente de texto + cursor no backend.
      retry = setTimeout(
        () =>
          api<Run>(`runs/${runId}`)
            .then((run) => {
              if (closed) return;
              if (active(run)) {
                setStreamRun(run);
                setConnectionAttempt((n) => n + 1);
              } else if (conversationId)
                loadConversation(conversationId).catch((e) =>
                  setError(e.message),
                );
            })
            .catch((e) => {
              if (!closed) {
                setError(e.message);
                setConnectionAttempt((n) => n + 1);
              }
            }),
        delay,
      );
    };
    source.onerror = reconnect;
    source.addEventListener("stream_error", reconnect);
    return () => {
      closed = true;
      source.close();
      if (retry) clearTimeout(retry);
    };
  }, [runId, conversationId, connectionAttempt, loadConversation]);

  useEffect(() => {
    if (followResponse.current)
      tail.current?.scrollIntoView({ behavior: "instant", block: "end" });
  }, [streamRun?.partial_answer, conversation?.messages.length]);

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || busy || streamRun || !processes.length) return;
    setBusy(true);
    setError("");
    try {
      let target = conversation;
      if (!target) {
        const process = processes[selectedProcess];
        target = await api<Conversation>("conversations", {
          process_id: process.process_id,
          corpus_version: process.corpus_version,
          requirements_version: process.requirements_version,
          executor,
          participant_id: participant,
        });
        setConversation({ ...target, messages: [], runs: [] });
      }
      const content = draft.trim();
      if (
        !pending.current ||
        pending.current.content !== content ||
        pending.current.conversation !== target.conversation_id
      ) {
        pending.current = {
          conversation: target.conversation_id,
          content,
          key: crypto.randomUUID(),
        };
      }
      await api<Run>(`conversations/${target.conversation_id}/messages`, {
        content,
        idempotency_key: pending.current.key,
      });
      pending.current = null;
      setDraft("");
      await loadConversation(target.conversation_id);
      setConversations(await api<Conversation[]>(`conversations?participant_id=${participant}`));
      setProgress("Aguardando agente");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao enviar mensagem.");
    } finally {
      setBusy(false);
    }
  }

  function newConversation() {
    selectionVersion.current++;
    stream.current?.close();
    setConversation(null);
    setStreamRun(null);
    setDraft("");
    setError("");
    pending.current = null;
    setProgress("Pronto para conversar");
    window.localStorage.removeItem("ciia-conversation");
  }

  return (
    <main className={styles.shell}>
      <aside className={styles.sidebar}>
        <Link href="/team" className={styles.brand}>
          CIIA<span>Laboratório de agentes</span>
        </Link>
        <button
          className={styles.newButton}
          onClick={newConversation}
          disabled={busy}
        >
          ＋ Nova conversa
        </button>
        <p className={styles.caption}>CONVERSAS NESTE NAVEGADOR</p>
        <nav aria-label="Conversas anteriores" className={styles.history}>
          {conversations.map((c) => (
            <button
              key={c.conversation_id}
              className={
                conversation?.conversation_id === c.conversation_id
                  ? styles.selected
                  : ""
              }
              disabled={busy}
              onClick={() =>
                loadConversation(c.conversation_id).catch((e) =>
                  setError(e.message),
                )
              }
            >
              <strong>{c.process_id}</strong>
              <span>
                {new Date(c.created_at * 1000).toLocaleString("pt-BR")} ·{" "}
                {c.executor}
              </span>
            </button>
          ))}
          {!conversations.length && <p>Suas conversas aparecerão aqui.</p>}
        </nav>
        <div className={styles.sidebarFooter}>
          Ambiente experimental · sem login
          <br />
          <span title={participant}>Participante: {participant.slice(0, 8) || "…"}</span>
          <br />
          <Link href="/team">Documentação do projeto ↗</Link>
        </div>
      </aside>
      <section className={styles.workspace}>
        <header className={styles.header}>
          <div>
            <p className={styles.eyebrow}>BACKEND & TOOLS</p>
            <h1>Converse com os documentos</h1>
          </div>
          <span className={styles.badge}>
            {(conversation?.executor || executor) === "simulation"
              ? "Demonstração simulada"
              : conversation?.executor || executor}
          </span>
        </header>
        <div className={styles.context}>
          <label>
            Processo
            <select
              value={
                conversation
                  ? processes.findIndex(
                      (p) =>
                        p.process_id === conversation.process_id &&
                        p.corpus_version === conversation.corpus_version,
                    )
                  : selectedProcess
              }
              disabled={!!conversation || busy}
              onChange={(e) => setSelectedProcess(Number(e.target.value))}
            >
              {processes.map((p, i) => (
                <option key={`${p.process_id}:${p.corpus_version}`} value={i}>
                  {p.process_id} · {p.corpus_version}
                </option>
              ))}
              {!processes.length && <option>Nenhum processo disponível</option>}
            </select>
          </label>
          <label>
            Executor
            <select
              value={conversation?.executor || executor}
              disabled={!!conversation || busy}
              onChange={(e) => setExecutor(e.target.value)}
            >
              {(
                capabilities?.executors || [
                  { name: "simulation", available: true, enabled: true, worker_recent: false },
                ]
              ).map((e) => (
                <option key={e.name} value={e.name} disabled={!e.enabled}>
                  {e.name === "simulation" ? "Simulador" : e.name}
                  {!capabilities ? " · carregando estado" : !e.enabled ? " · desabilitado" :
                    e.worker_recent ? " · worker recente" : " · sem presença recente"}
                </option>
              ))}
            </select>
          </label>
          <p>
            {conversation
              ? `${conversation.process_id} · ${conversation.corpus_version}`
              : "Histórico preservado nesta conversa"}
            <br />
            <small>
              {capabilities?.can_write
                ? "Tools de escrita permitidas pelo perfil"
                : "Perfil de leitura"}
            </small>
          </p>
        </div>
        {error && (
          <div className={styles.error} role="alert">
            {error}
          </div>
        )}
        <div
          className={styles.messages}
          role="log"
          aria-label="Mensagens da conversa"
          onScroll={(event) => {
            const element = event.currentTarget;
            followResponse.current =
              element.scrollHeight - element.scrollTop - element.clientHeight <
              80;
          }}
        >
          {!conversation?.messages?.length && (
            <div className={styles.empty}>
              <div>↗</div>
              <h2>Uma pergunta inicia a conversa.</h2>
              <p>
                Explore o processo, consulte evidências e continue de onde
                parou.
              </p>
              <p className={styles.note}>
                O simulador valida a integração e o streaming com dados
                fictícios. Nenhum modelo de IA é chamado nesse modo.
              </p>
              <button
                onClick={() =>
                  setDraft("Quais documentos estão disponíveis neste processo?")
                }
              >
                Quais documentos estão disponíveis? →
              </button>
            </div>
          )}
          {conversation?.runs?.map((run) => (
            <Fragment key={run.run_id}>
              {conversation.messages
                .filter((message) => message.run_id === run.run_id)
                .map((message) => (
                  <article
                    key={message.message_id}
                    className={`${styles.message} ${message.role === "user" ? styles.user : styles.assistant}`}
                  >
                    <span className={styles.messageLabel}>
                      {message.role === "user" ? "Você" : "Assistente"}
                    </span>
                    <div>{message.content}</div>
                    {message.role === "assistant" && (
                      <Sources sources={run.result?.sources || []} />
                    )}
                  </article>
                ))}
              {run.status === "succeeded" &&
                !conversation.messages.some(
                  (m) => m.run_id === run.run_id && m.role === "assistant",
                ) && (
                  // Snapshot anterior à mensagem persistida: o resultado já traz a resposta.
                  <article className={`${styles.message} ${styles.assistant}`}>
                    <span className={styles.messageLabel}>Assistente</span>
                    <div>{run.result?.answer}</div>
                    <Sources sources={run.result?.sources || []} />
                  </article>
                )}
              {!active(run) && run.status !== "succeeded" && (
                <article className={`${styles.message} ${styles.failed}`}>
                  <span className={styles.messageLabel}>
                    Resposta interrompida · {run.status}
                  </span>
                  <div>
                    {run.result?.answer ||
                      run.partial_answer ||
                      "O agente não concluiu esta execução. Você pode enviar uma nova pergunta."}
                  </div>
                  {run.result?.error_code && (
                    <p>
                      <small>
                        {failureReason[run.result.error_code] ||
                          `Código do erro: ${run.result.error_code}`}
                      </small>
                    </p>
                  )}
                  <Sources sources={run.result?.sources || []} />
                </article>
              )}
              <Artifacts items={run.artifacts || []} />
            </Fragment>
          ))}
          {streamRun && (
            <article className={`${styles.message} ${styles.assistant}`}>
              <span className={styles.messageLabel}>
                Assistente · em elaboração
              </span>
              <div>
                {streamRun.partial_answer || "Preparando a resposta…"}
                <span className={styles.cursor} aria-hidden="true">
                  ▍
                </span>
              </div>
            </article>
          )}
          <div ref={tail} />
        </div>
        <footer className={styles.composer}>
          <div className={styles.status} role="status">
            {streamRun ? "● " : "○ "}
            {progress}
          </div>
          <form onSubmit={send}>
            <label className={styles.srOnly} htmlFor="question">
              Sua pergunta
            </label>
            <textarea
              id="question"
              placeholder="Faça uma pergunta sobre o processo…"
              rows={2}
              value={draft}
              maxLength={100000}
              disabled={busy}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <button
              type="submit"
              disabled={
                busy || !!streamRun || !draft.trim() || !processes.length || !participant
              }
            >
              {busy ? "Enviando…" : "Enviar ↑"}
            </button>
          </form>
          <small>
            Confira as fontes. Não localizar um documento não comprova ausência
            no processo original.
          </small>
        </footer>
      </section>
    </main>
  );
}

function Sources({ sources }: { sources: Source[] }) {
  if (!sources.length) return null;
  return (
    <details className={styles.sources}>
      <summary>Fontes · {sources.length}</summary>
      {sources.map((s, i) => (
        <p key={i}>
          {s.kind === "inventory"
            ? `Inventário: ${s.process_id} · ${s.corpus_version}`
            : `${s.document_id} · página ${s.page}`}
          <small>{s.chunk_id}</small>
        </p>
      ))}
    </details>
  );
}


type Artifact = {
  artifact_id: string;
  tool: string;
  payload: { content: string; evidence_note: string; requirement_id?: string };
  receipt: { content_sha256: string; persisted_at: string };
};

function Artifacts({ items }: { items: { artifact_id: string; tool: string }[] }) {
  return <>{items.map((item) => <ArtifactView key={item.artifact_id} item={item} />)}</>;
}

function ArtifactView({ item }: { item: { artifact_id: string; tool: string } }) {
  const [value, setValue] = useState<Artifact | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  return (
    <article className={`${styles.message} ${styles.assistant}`}>
      <strong>{item.tool === "salvar_minuta" ? "Minuta registrada" : "Pendência registrada"}</strong>
      <p><small>{item.artifact_id}</small></p>
      {!value && <button disabled={loading} onClick={async () => {
        setLoading(true); setError("");
        try { setValue(await api<Artifact>(`artifacts/${item.artifact_id}`)); }
        catch (e) { setError(e instanceof Error ? e.message : "Falha ao consultar artefato."); }
        finally { setLoading(false); }
      }}>{loading ? "Consultando…" : "Conferir conteúdo e recibo"}</button>}
      {error && <p role="alert">{error}</p>}
      {value && <>
        <div>{value.payload.content}</div>
        <p>Fundamentação: {value.payload.evidence_note}</p>
        {value.payload.requirement_id && <p>Requisito: {value.payload.requirement_id}</p>}
        <details><summary>Recibo de persistência</summary>
          <p>Gravado em {new Date(value.receipt.persisted_at).toLocaleString("pt-BR")}</p>
          <p>SHA-256: {value.receipt.content_sha256}</p>
        </details>
      </>}
    </article>
  );
}
