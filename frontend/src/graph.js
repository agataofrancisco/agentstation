// Topologia do grafo (espelha backend/app/graph/build.py) e estado por no a partir dos eventos.
export const NODES = [
  { id: "supervisor", label: "supervisor", x: 0, y: 120 },
  { id: "triage", label: "triage", x: 220, y: 0 },
  { id: "knowledge_retrieval", label: "knowledge_retrieval", x: 220, y: 120 },
  { id: "reporting", label: "reporting", x: 220, y: 240 },
  { id: "verifier", label: "verifier", x: 440, y: 120 },
  { id: "approval_gate", label: "approval_gate", x: 660, y: 0 },
  { id: "execute_action", label: "execute_action", x: 660, y: 120 },
  { id: "finalize", label: "finalize", x: 880, y: 120 },
];

export const EDGES = [
  ["supervisor", "triage"],
  ["supervisor", "knowledge_retrieval"],
  ["supervisor", "reporting"],
  ["supervisor", "verifier"],
  ["triage", "supervisor"],
  ["knowledge_retrieval", "supervisor"],
  ["reporting", "supervisor"],
  ["verifier", "approval_gate"],
  ["verifier", "finalize"],
  ["approval_gate", "execute_action"],
  ["approval_gate", "finalize"],
  ["execute_action", "finalize"],
];

// Estado de cada no: "active" (iniciado sem fim), "done" (terminou), "idle".
export function nodeStates(events) {
  const state = Object.fromEntries(NODES.map((n) => [n.id, "idle"]));
  for (const ev of events) {
    if (!ev.node || !(ev.node in state)) continue;
    if (ev.type === "node_started") state[ev.node] = "active";
    if (ev.type === "node_finished" && state[ev.node] === "active") state[ev.node] = "done";
  }
  return state;
}

// No actual: o ultimo no iniciado que ainda nao terminou; senao o ultimo terminado.
export function currentNode(events) {
  let current = null;
  for (const ev of events) {
    if (ev.type === "node_started" && ev.node) current = ev.node;
    if (ev.type === "node_finished" && ev.node === current) current = null;
  }
  return current;
}
