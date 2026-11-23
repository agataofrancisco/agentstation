import { useEffect, useState } from "react";
import { api } from "./api.js";

export default function Approvals({ session }) {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [comment, setComment] = useState({});
  const [days, setDays] = useState({});

  async function refresh() {
    try {
      setItems((await api("/approvals?status_filter=pending", { token: session.token })).items);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, []);

  async function resolve(a, decision) {
    setError("");
    const body = { decision, comment: comment[a.id] || null };
    if (decision === "edit") {
      body.params = { ...a.params, days: Number(days[a.id] ?? a.params.days) };
    }
    try {
      await api(`/approvals/${a.id}/resolve`, { token: session.token, method: "POST", body });
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="card">
      <h2>Fila de aprovacoes</h2>
      {error && <p className="error">{error}</p>}
      {items.length === 0 && <p className="muted">Nenhuma aprovacao pendente.</p>}
      {items.map((a) => (
        <article key={a.id} className="approval">
          <h3>
            {a.action} <span className="muted">({a.reason})</span>
          </h3>
          <p>{a.justification}</p>
          <p>
            <code>{JSON.stringify(a.params)}</code>
          </p>
          <p className="muted">
            Tarefa {a.task_id} · pedido por {a.requester_id}
          </p>
          <input
            placeholder="Comentario (opcional)"
            value={comment[a.id] || ""}
            onChange={(e) => setComment({ ...comment, [a.id]: e.target.value })}
          />
          {a.action === "suspend_account" && (
            <label>
              Dias (editar antes de aprovar)
              <input
                type="number"
                min={1}
                max={365}
                value={days[a.id] ?? a.params.days}
                onChange={(e) => setDays({ ...days, [a.id]: e.target.value })}
              />
            </label>
          )}
          <div className="row">
            <button onClick={() => resolve(a, "approve")}>Aceitar</button>
            <button className="ghost" onClick={() => resolve(a, "reject")}>
              Rejeitar
            </button>
            {a.action === "suspend_account" && (
              <button className="ghost" onClick={() => resolve(a, "edit")}>
                Editar e aprovar
              </button>
            )}
          </div>
        </article>
      ))}
    </section>
  );
}
