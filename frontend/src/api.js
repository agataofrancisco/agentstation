// Cliente da API. O token fica so em memoria (sem localStorage: menos exposicao a XSS).
export const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:18100";

export const PERSONAS = [
  { email: "ines@nimbo", label: "Ines (requester, nimbo)" },
  { email: "joao@nimbo", label: "Joao (requester, nimbo)" },
  { email: "rui@nimbo", label: "Rui (reviewer, nimbo)" },
  { email: "ada@nimbo", label: "Ada (admin, nimbo)" },
  { email: "marta@atlas", label: "Marta (requester, atlas)" },
];

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export async function api(path, { token, method = "GET", body, headers = {} } = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data.detail || `erro ${res.status}`);
  return data;
}

// EventSource nao envia cabecalhos Authorization; usa-se fetch com leitura incremental do stream SSE.
export async function streamEvents({ taskId, token, lastId, signal, onEvent }) {
  const headers = { Authorization: `Bearer ${token}` };
  if (lastId) headers["Last-Event-ID"] = String(lastId);
  const res = await fetch(`${API_BASE}/tasks/${taskId}/events`, { headers, signal });
  if (!res.ok || !res.body) throw new ApiError(res.status, "stream indisponivel");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
      if (!dataLine) continue;
      try {
        onEvent(JSON.parse(dataLine.slice(6)));
      } catch {
        // linha mal formada: ignorada (nunca derruba o painel)
      }
    }
  }
}
