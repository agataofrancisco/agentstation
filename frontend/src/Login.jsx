import { useState } from "react";
import { PERSONAS, api } from "./api.js";

export default function Login({ onLogin }) {
  const [email, setEmail] = useState(PERSONAS[0].email);
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      const data = await api("/auth/login", { method: "POST", body: { email } });
      onLogin({ token: data.access_token, user: data.user });
    } catch (err) {
      setError(err.status === 404 ? "Login demo indisponivel (DEMO_MODE desligado)." : err.message);
    }
  }
  return (
    <form className="card login" onSubmit={submit}>
      <h1>AgentStation</h1>
      <p className="muted">Entrar como persona sintetica (demo, sem palavra-passe).</p>
      <label>
        Persona
        <select value={email} onChange={(e) => setEmail(e.target.value)}>
          {PERSONAS.map((p) => (
            <option key={p.email} value={p.email}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      <button type="submit">Entrar</button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
