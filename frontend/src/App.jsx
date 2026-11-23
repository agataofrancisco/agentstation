import { useState } from "react";
import Login from "./Login.jsx";
import Tasks from "./Tasks.jsx";
import Approvals from "./Approvals.jsx";
import Memory from "./Memory.jsx";

export default function App() {
  const [session, setSession] = useState(null); // { token, user }
  const [tab, setTab] = useState("tasks");

  if (!session) return <Login onLogin={setSession} />;

  const isReviewer = session.user.role === "reviewer" || session.user.role === "admin";
  const tabs = [
    ["tasks", "Tarefas"],
    ...(isReviewer ? [["approvals", "Aprovacoes"]] : []),
    ["memory", "Memoria"],
  ];
  return (
    <div className="app">
      <header>
        <strong>AgentStation</strong>
        <nav>
          {tabs.map(([id, label]) => (
            <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>
        <span className="muted">
          {session.user.email} · {session.user.role} · {session.user.tenant_id}
        </span>
        <button className="ghost" onClick={() => setSession(null)}>
          Sair
        </button>
      </header>
      <main>
        {tab === "tasks" && <Tasks session={session} />}
        {tab === "approvals" && isReviewer && <Approvals session={session} />}
        {tab === "memory" && <Memory session={session} />}
      </main>
    </div>
  );
}
