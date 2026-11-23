import { useEffect, useRef, useState } from "react";
import { ReactFlow, Background, Controls } from "@xyflow/react";
import { api, streamEvents } from "./api.js";
import { EDGES, NODES, currentNode, nodeStates } from "./graph.js";

function flowNodes(events) {
  const states = nodeStates(events);
  const current = currentNode(events);
  return NODES.map((n) => ({
    id: n.id,
    position: { x: n.x, y: n.y },
    data: { label: n.label },
    className: `gnode ${states[n.id]} ${current === n.id ? "current" : ""}`,
    style: { width: 170 },
  }));
}

export default function TaskDetail({ taskId, session }) {
  const [task, setTask] = useState(null);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  const lastId = useRef(0);
  const controller = useRef(null);

  async function loadTask() {
    try {
      setTask(await api(`/tasks/${taskId}`, { token: session.token }));
    } catch (err) {
      setError(err.message);
    }
  }

  function connect() {
    controller.current?.abort();
    const ctl = new AbortController();
    controller.current = ctl;
    streamEvents({
      taskId,
      token: session.token,
      lastId: lastId.current,
      signal: ctl.signal,
      onEvent: (ev) => {
        lastId.current = Math.max(lastId.current, ev.seq);
        setEvents((prev) => (prev.some((p) => p.seq === ev.seq) ? prev : [...prev, ev]));
      },
    }).catch((err) => {
      if (err.name !== "AbortError") setError(err.message);
    });
  }

  useEffect(() => {
    loadTask();
    connect();
    const id = setInterval(loadTask, 3000);
    return () => {
      clearInterval(id);
      controller.current?.abort();
    };
  }, [taskId]);

  function exportResult() {
    const blob = new Blob([JSON.stringify({ task, events }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${taskId}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const edges = EDGES.map(([s, t]) => ({ id: `${s}-${t}`, source: s, target: t }));

  return (
    <div className="card">
      <h2>
        Tarefa <code>{taskId}</code> {task && <span className={`badge ${task.status}`}>{task.status}</span>}
      </h2>
      {task && <p>{task.request}</p>}
      {error && <p className="error">{error}</p>}
      <div className="flow">
        <ReactFlow
          nodes={flowNodes(events)}
          edges={edges}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <p className="muted">No actual: {currentNode(events) || "nenhum"}</p>
      <div className="row">
        <button onClick={connect}>Atualizar linha temporal</button>
        <button onClick={exportResult} disabled={!task}>
          Exportar JSON
        </button>
      </div>
      <h3>Linha temporal</h3>
      <ol className="timeline">
        {events.map((ev) => (
          <li key={ev.seq}>
            <code>{ev.type}</code>
            {ev.node && <> · {ev.node}</>}
            {ev.tool && <> · ferramenta {ev.tool}</>}
            {ev.duration_ms != null && <> · {ev.duration_ms} ms</>}
            {ev.type !== "node_started" && ev.type !== "node_finished" && ev.payload && (
              <span className="muted"> {JSON.stringify(ev.payload).slice(0, 140)}</span>
            )}
          </li>
        ))}
        {events.length === 0 && <li className="muted">Sem eventos ainda.</li>}
      </ol>
      {task?.pending_approvals?.length > 0 && (
        <p className="notice">Aguarda aprovacao: {task.pending_approvals.join(", ")} (separador Aprovacoes).</p>
      )}
      <p className="muted">Nos verdes: concluidos · azul: activo.</p>
    </div>
  );
}
