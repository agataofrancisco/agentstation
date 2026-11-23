import { useEffect, useState } from "react";
import { api } from "./api.js";
import TaskDetail from "./TaskDetail.jsx";

export default function Tasks({ session }) {
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [text, setText] = useState(
    "classifica o ticket T-101, encontra o procedimento aplicavel e prepara uma resposta",
  );
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const data = await api("/tasks", { token: session.token });
      setItems(data.items);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, []);

  async function create(e) {
    e.preventDefault();
    setError("");
    try {
      const r = await api("/tasks", { token: session.token, method: "POST", body: { request: text } });
      await refresh();
      setSelected(r.task_id);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="split">
      <section className="card">
        <h2>Nova tarefa</h2>
        <form onSubmit={create}>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={2000} />
          <button type="submit">Criar</button>
        </form>
        {error && <p className="error">{error}</p>}
        <h2>Tarefas</h2>
        <ul className="list">
          {items.map((t) => (
            <li key={t.id}>
              <button className={selected === t.id ? "active" : "ghost"} onClick={() => setSelected(t.id)}>
                <span className={`badge ${t.status}`}>{t.status}</span> {t.request.slice(0, 60)}
              </button>
            </li>
          ))}
          {items.length === 0 && <li className="muted">Sem tarefas.</li>}
        </ul>
      </section>
      <section>
        {selected ? (
          <TaskDetail key={selected} taskId={selected} session={session} />
        ) : (
          <p className="muted card">Selecione ou crie uma tarefa.</p>
        )}
      </section>
    </div>
  );
}
