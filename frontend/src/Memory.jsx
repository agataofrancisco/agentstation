import { useEffect, useState } from "react";
import { api } from "./api.js";

export default function Memory({ session }) {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      setItems((await api("/memory", { token: session.token })).items);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function remove(id) {
    try {
      await api(`/memory/${id}`, { token: session.token, method: "DELETE" });
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="card">
      <h2>Memoria</h2>
      <p className="muted">Memorias de longo prazo (opt-in). Pode eliminar qualquer uma.</p>
      {error && <p className="error">{error}</p>}
      {items.length === 0 && <p className="muted">Sem memorias activas para esta persona.</p>}
      <ul className="list">
        {items.map((m) => (
          <li key={m.id}>
            <span>{m.text}</span> <span className="muted">origem {m.source_task}</span>{" "}
            <button className="ghost" onClick={() => remove(m.id)}>
              Eliminar
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
