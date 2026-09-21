"use client";

import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ReactFlow,
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  useReactFlow,
  addEdge,
  Connection,
  Node,
  Edge,
  NodeTypes,
  Handle,
  Position,
  ReactFlowProvider,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

/* Override React Flow default node wrapper */
const rfOverrides = `
  .react-flow__node { background: transparent !important; border: none !important; border-radius: 0 !important; box-shadow: none !important; padding: 0 !important; }
  .react-flow__node.selected { box-shadow: none !important; }
`;
import {
  getWorkflow,
  updateWorkflow,
  runWorkflow,
  runWorkflowJob,
  listWorkflowRuns,
  uploadWorkflowTemplate,
  inputFieldsOf,
  GraphJSON,
  InputField,
  RunResult,
  WorkflowRunRow,
} from "@/lib/api/workflows";
import { listDatasets } from "@/lib/api/datasets";
import { listTools, testTool, ToolResponse } from "@/lib/api/tools";
import { downloadArtifact, formatBytes } from "@/lib/api/artifacts";

/* ═══════════════════════════════════════════
   NODE STYLES
   ═══════════════════════════════════════════ */

const NODE_STYLES: Record<string, { color: string; bg: string; icon: string; label: string }> = {
  input:             { color: "#22c55e", bg: "rgba(34,197,94,0.10)",  icon: "▶",  label: "Start" },
  retrieve:          { color: "#3b82f6", bg: "rgba(59,130,246,0.10)",  icon: "🔍", label: "Knowledge Retrieval" },
  compose_prompt:    { color: "#f59e0b", bg: "rgba(245,158,11,0.10)", icon: "📝", label: "Compose Prompt" },
  llm_generate:      { color: "#a855f7", bg: "rgba(168,85,247,0.10)", icon: "🤖", label: "LLM" },
  parameter_extract: { color: "#14b8a6", bg: "rgba(20,184,166,0.10)", icon: "📋", label: "Parameter Extract" },
  http_request:      { color: "#f97316", bg: "rgba(249,115,22,0.10)", icon: "🌐", label: "HTTP Request" },
  code_execute:      { color: "#6366f1", bg: "rgba(99,102,241,0.10)", icon: "⚡", label: "Code Execute" },
  tool_call:         { color: "#0ea5e9", bg: "rgba(14,165,233,0.10)", icon: "🔧", label: "Gọi công cụ" },
  render_document:   { color: "#84cc16", bg: "rgba(132,204,22,0.10)", icon: "📄", label: "Xuất tài liệu" },
  if_else:           { color: "#6b7280", bg: "rgba(107,114,128,0.10)", icon: "🔀", label: "If / Else" },
  answer:            { color: "#ec4899", bg: "rgba(236,72,153,0.10)", icon: "💬", label: "Answer" },
  output:            { color: "#ef4444", bg: "rgba(239,68,68,0.10)",  icon: "⏹",  label: "End" },
};

/* ═══════════════════════════════════════════
   CUSTOM NODE COMPONENT
   ═══════════════════════════════════════════ */

function WorkflowNode({ data, type, selected }: NodeProps) {
  const style = NODE_STYLES[type || "input"] || NODE_STYLES.input;
  const isIfElse = type === "if_else";
  const label = typeof data?.label === "string" ? data.label : "";

  return (
    <div
      style={{
        background: "var(--card)",
        border: `2px solid ${selected ? style.color : "rgba(255,255,255,0.08)"}`,
        borderRadius: 12,
        padding: "12px 18px",
        minWidth: 180,
        boxShadow: selected
          ? `0 0 0 3px ${style.bg}, 0 4px 16px rgba(0,0,0,0.3)`
          : "0 2px 8px rgba(0,0,0,0.25)",
        transition: "all 0.15s ease",
      }}
    >
      {type !== "input" && (
        <Handle type="target" position={Position.Top} style={{ background: style.color, width: 10, height: 10, border: "2px solid var(--card)" }} />
      )}
      <div className="flex items-center gap-2.5">
        <div
          className="flex items-center justify-center rounded-lg"
          style={{ width: 28, height: 28, background: style.bg, fontSize: 14, flexShrink: 0 }}
        >
          {style.icon}
        </div>
        <div className="min-w-0">
          <div className="text-[11px] font-bold tracking-wide" style={{ color: style.color }}>{style.label}</div>
          {label && label !== style.label && (
            <div className="text-[10px] mt-0.5 truncate" style={{ color: "var(--muted)", maxWidth: 120 }}>
              {label}
            </div>
          )}
        </div>
      </div>
      {type !== "output" && !isIfElse && (
        <Handle type="source" position={Position.Bottom} style={{ background: style.color, width: 10, height: 10, border: "2px solid var(--card)" }} />
      )}
      {isIfElse && (
        <>
          <div className="flex justify-between mt-2 text-[9px] font-bold" style={{ color: "var(--muted)" }}>
            <span style={{ color: "#22c55e" }}>TRUE</span>
            <span style={{ color: "#ef4444" }}>FALSE</span>
          </div>
          <Handle type="source" position={Position.Bottom} id="true" style={{ background: "#22c55e", width: 10, height: 10, border: "2px solid var(--card)", left: "30%" }} />
          <Handle type="source" position={Position.Bottom} id="false" style={{ background: "#ef4444", width: 10, height: 10, border: "2px solid var(--card)", left: "70%" }} />
        </>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════
   MAIN
   ═══════════════════════════════════════════ */

export default function WorkflowCanvasPage() {
  return (
    <ReactFlowProvider>
      <WorkflowCanvasInner />
    </ReactFlowProvider>
  );
}

function WorkflowCanvasInner() {
  const params = useParams();
  const router = useRouter();
  const workflowId = params.workflowId as string;
  const { screenToFlowPosition } = useReactFlow();

  const [workflowName, setWorkflowName] = useState("...");
  const [workflowType, setWorkflowType] = useState("chatflow");
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([] as Node[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([] as Edge[]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [runModal, setRunModal] = useState(false);
  const [runQuery, setRunQuery] = useState("");
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [datasets, setDatasets] = useState<Array<{ id: string; name: string }>>([]);
  const [tools, setTools] = useState<ToolResponse[]>([]);
  const [runInputs, setRunInputs] = useState<Record<string, any>>({});
  const [queueMsg, setQueueMsg] = useState<string | null>(null);
  const [runsOpen, setRunsOpen] = useState(false);
  const [runs, setRuns] = useState<WorkflowRunRow[]>([]);
  const [inputFields, setInputFields] = useState<InputField[]>([]);
  const [mcpTools, setMcpTools] = useState<Record<string, string[]>>({});   // tool id → tool names on that MCP server
  const nodeIdCounter = useRef(1);

  const nodeTypes: NodeTypes = useMemo(
    () => Object.fromEntries(Object.keys(NODE_STYLES).map((t) => [t, WorkflowNode])),
    []
  );

  // Load
  useEffect(() => {
    (async () => {
      try {
        const wf = await getWorkflow(workflowId);
        setWorkflowName(wf.name);
        setWorkflowType(wf.type || "chatflow");
        const graph = wf.graph_json;
        if (graph.nodes?.length) {
          setNodes(graph.nodes.map((n) => ({ ...n, type: n.type, data: n.data || {} })) as Node[]);
          setEdges((graph.edges || []).map((e) => ({
            ...e, animated: true,
            style: { stroke: e.sourceHandle === "false" ? "#ef4444" : "var(--accent)", strokeWidth: 2 },
          })) as Edge[]);
          nodeIdCounter.current = Math.max(...graph.nodes.map((n) => parseInt(n.id.replace(/\D/g, "")) || 0)) + 1;
        }
      } catch { router.push("/workflows"); }
    })();
  }, [workflowId]); // eslint-disable-line

  useEffect(() => { listDatasets().then(setDatasets).catch(() => {}); }, []);
  useEffect(() => { listTools().then(setTools).catch(() => {}); }, []);

  // The input node's fields drive the run form, so keep them in sync with the canvas.
  useEffect(() => {
    const fields = inputFieldsOf({ nodes: nodes.map((n) => ({ id: n.id, type: n.type || "input", position: n.position, data: n.data as Record<string, any> })), edges: [] });
    setInputFields(fields);
    setRunInputs((prev) => {
      const next: Record<string, any> = {};
      fields.forEach((f) => { next[f.name] = prev[f.name] ?? f.default ?? (f.type === "boolean" ? false : ""); });
      return next;
    });
  }, [nodes]);

  // An MCP row is one server; the node picks which of its tools to call, so list them.
  useEffect(() => {
    const toolId = selectedNode?.type === "tool_call" ? (selectedNode.data?.tool_id as string) : "";
    if (!toolId || mcpTools[toolId]) return;
    const tool = tools.find((t) => t.id === toolId);
    if (tool?.kind !== "mcp") return;
    testTool(toolId, {}).then((r) => {
      const names = Array.isArray(r.result) ? (r.result as any[]).map((x) => String(x.name).split("__").pop()!) : [];
      setMcpTools((prev) => ({ ...prev, [toolId]: names }));
    }).catch(() => setMcpTools((prev) => ({ ...prev, [toolId]: [] })));
  }, [selectedNode, tools, mcpTools]);

  const loadRuns = useCallback(async () => {
    try { setRuns(await listWorkflowRuns(workflowId)); } catch { /* silent */ }
  }, [workflowId]);

  useEffect(() => {
    if (!runsOpen) return;
    loadRuns();
    const t = setInterval(loadRuns, 4000);  // a queued report finishes in the background
    return () => clearInterval(t);
  }, [runsOpen, loadRuns]);

  const onConnect = useCallback((c: Connection) => {
    const isIfElseFalse = c.sourceHandle === "false";
    setEdges((eds) => addEdge({
      ...c, animated: true,
      style: { stroke: isIfElseFalse ? "#ef4444" : "var(--accent)", strokeWidth: 2 },
    }, eds));
  }, [setEdges]);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => setSelectedNode(node), []);
  const onPaneClick = useCallback(() => setSelectedNode(null), []);

  const addNode = (type: string) => {
    const id = `node_${nodeIdCounter.current++}`;
    const style = NODE_STYLES[type];
    const d: Record<string, any> = { label: style?.label || type };
    if (type === "retrieve") { d.dataset_ids = []; d.top_k = 5; }
    if (type === "compose_prompt") { d.template = "{{system_prompt}}\n\nContext:\n{{context}}\n\nQuestion: {{query}}"; }
    if (type === "llm_generate") { d.model = ""; d.temperature = 0.7; d.max_tokens = 4096; }
    if (type === "parameter_extract") { d.schema = { name: "User's full name", email: "User's email address" }; }
    if (type === "http_request") { d.url = ""; d.method = "POST"; d.headers = { "Content-Type": "application/json" }; d.body_template = '{"name":"{{name}}","email":"{{email}}"}'; }
    if (type === "if_else") { d.variable = "extracted_params.name"; d.operator = "not_empty"; d.value = ""; }
    if (type === "answer") { d.template = ""; }
    if (type === "tool_call") { d.tool_id = ""; d.alias = "ket_qua"; d.args = {}; }
    if (type === "render_document") {
      d.format = "markdown"; d.title = "Báo cáo {{ today }}"; d.filename = "bao-cao-{{ today }}";
      d.audience = "admin"; d.template = "# Báo cáo {{ today }}\n\n{{ answer }}\n"; d.vars = {};
    }
    if (type === "input") { d.fields = []; }
    if (type === "code_execute") { d.code = "def main(args):\n    # args: query, inputs, answer, extracted_params, retrieved_chunks, http_response\n    data = args['extracted_params']\n    return {'answer': f'Processed: {data}'}\n"; }

    // Place node at the center of the current viewport
    const canvasEl = document.querySelector('.react-flow');
    const w = canvasEl?.clientWidth ?? 800;
    const h = canvasEl?.clientHeight ?? 600;
    const center = screenToFlowPosition({ x: w / 2 + 170, y: h / 2 + 52 }); // offset for palette + toolbar

    setNodes((nds) => [...nds, { id, type, position: { x: center.x - 90, y: center.y - 20 + (nds.length % 3) * 80 }, data: d } as Node]);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const graph: GraphJSON = {
        nodes: nodes.map((n) => ({ id: n.id, type: n.type || "input", position: n.position, data: n.data as Record<string, any> })),
        edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle || undefined })),
      };
      await updateWorkflow(workflowId, { name: workflowName, type: workflowType, graph_json: graph });
      setSaved(true); setTimeout(() => setSaved(false), 2000);
    } catch (err: any) { alert(err?.message || "Save failed"); }
    finally { setSaving(false); }
  };

  const handleRun = async () => {
    setRunning(true); setRunResult(null); setQueueMsg(null);
    try { setRunResult(await runWorkflow(workflowId, runQuery || workflowName, runInputs)); }
    catch (err: any) { setRunResult({ answer: `Lỗi: ${err?.message || "Chạy thất bại"}`, extracted_params: {}, retriever_resources: [], artifacts: [] }); }
    finally { setRunning(false); }
  };

  /** Reports run on the jobs worker: the request returns at once and the run shows up in "Lần chạy". */
  const handleQueue = async () => {
    setRunning(true); setRunResult(null); setQueueMsg(null);
    try {
      await runWorkflowJob(workflowId, runInputs);
      setQueueMsg("Đã xếp hàng chạy nền. Theo dõi ở mục “Lần chạy”.");
      setRunModal(false);
      setRunsOpen(true);
    } catch (err: any) { setQueueMsg(`Lỗi: ${err?.message || "Không xếp được hàng đợi"}`); }
    finally { setRunning(false); }
  };

  const updateFieldAt = (index: number, patch: Partial<InputField>) => {
    const fields = [...(((selectedNode?.data?.fields as InputField[]) || []))];
    fields[index] = { ...fields[index], ...patch };
    updateNodeData("fields", fields);
  };

  const updateNodeData = (key: string, value: any) => {
    if (!selectedNode) return;
    setNodes((nds) => nds.map((n) => {
      if (n.id === selectedNode.id) {
        const updated = { ...n, data: { ...n.data, [key]: value } };
        setSelectedNode(updated);
        return updated;
      }
      return n;
    }));
  };

  return (
    <div style={{ position: "fixed", inset: 0, display: "flex", flexDirection: "column", background: "var(--background)", zIndex: 50 }}>
      <style dangerouslySetInnerHTML={{ __html: rfOverrides }} />
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 gap-3"
        style={{ height: 52, borderBottom: "1px solid var(--border)", background: "var(--card)", flexShrink: 0 }}>
        <div className="flex items-center gap-3">
          <button onClick={() => router.push("/workflows")} className="rounded-lg p-1.5" style={{ color: "var(--muted)" }}>
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M12 3L6 9L12 15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
          <div className="group/title flex items-center gap-1.5 rounded-lg px-2 py-1 -ml-2 transition-all"
            style={{ border: "1px solid transparent" }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.background = "var(--background)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = "transparent"; e.currentTarget.style.background = "transparent"; }}>
            <input value={workflowName} onChange={(e) => setWorkflowName(e.target.value)}
              className="text-sm font-semibold bg-transparent border-none outline-none cursor-text"
              style={{ color: "var(--foreground)", width: 200 }} />
            <svg className="opacity-0 group-hover/title:opacity-50 transition-opacity" width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ color: "var(--muted)", flexShrink: 0 }}>
              <path d="M8.5 1.5L10.5 3.5M1 11L1.5 8.5L9 1L11 3L3.5 10.5L1 11Z" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full"
            style={{ background: workflowType === "chatflow" ? "rgba(236,72,153,0.12)" : "rgba(168,85,247,0.12)",
                     color: workflowType === "chatflow" ? "#ec4899" : "#a855f7" }}>
            {workflowType}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setRunsOpen((v) => !v)}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium"
            style={{ background: runsOpen ? "var(--accent-glow)" : "var(--background)", color: runsOpen ? "var(--accent)" : "var(--foreground)", border: "1px solid var(--border)" }}
            data-testid="runs-toggle">
            📊 Lần chạy
          </button>
          <button onClick={() => { setRunModal(true); setRunResult(null); setQueueMsg(null); }}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium"
            style={{ background: "rgba(34,197,94,0.12)", color: "#22c55e" }}
            data-testid="run-open">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M3 2L10 6L3 10V2Z" fill="currentColor" /></svg>
            {workflowType === "report" ? "Chạy báo cáo" : "Test Run"}
          </button>
          <button onClick={handleSave} disabled={saving}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium"
            style={{ background: "var(--accent)", color: "#fff" }}>
            {saving ? "..." : saved ? "✓ Saved" : "Save"}
          </button>
        </div>
      </div>

      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Palette */}
        <div className="flex flex-col gap-1 p-2.5"
          style={{ width: 170, borderRight: "1px solid var(--border)", background: "var(--card)", overflowY: "auto", flexShrink: 0 }}>
          <p className="text-[10px] font-bold uppercase tracking-wider mb-1 px-1" style={{ color: "var(--muted)" }}>Nodes</p>
          {Object.entries(NODE_STYLES).map(([type, s]) => (
            <button key={type} onClick={() => addNode(type)}
              className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-[11px] font-medium text-left transition-all"
              style={{ background: s.bg, color: s.color, border: "1px solid transparent" }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = s.color; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = "transparent"; }}>
              <span style={{ fontSize: 12 }}>{s.icon}</span>{s.label}
            </button>
          ))}
        </div>

        {/* Canvas */}
        <div style={{ flex: 1 }}>
          <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
            onConnect={onConnect} onNodeClick={onNodeClick} onPaneClick={onPaneClick}
            nodeTypes={nodeTypes} fitView colorMode="dark"
            defaultEdgeOptions={{ animated: true, style: { stroke: "var(--accent)", strokeWidth: 2 } }}>
            <Background variant={BackgroundVariant.Cross} gap={24} size={2} color="rgba(255,255,255,0.06)" />
            <Controls style={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} showInteractive={false} />
          </ReactFlow>
        </div>

        {/* Properties Panel */}
        {selectedNode && (
          <div className="flex flex-col gap-3 p-4"
            style={{ width: 280, borderLeft: "1px solid var(--border)", background: "var(--card)", overflowY: "auto", flexShrink: 0 }}>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold flex items-center gap-1.5" style={{ color: NODE_STYLES[selectedNode.type || ""]?.color }}>
                {NODE_STYLES[selectedNode.type || ""]?.icon} {NODE_STYLES[selectedNode.type || ""]?.label}
              </h3>
              <button onClick={() => setSelectedNode(null)} className="text-xs rounded p-1" style={{ color: "var(--muted)" }}>✕</button>
            </div>
            <div style={{ borderBottom: "1px solid var(--border)" }} />

            {/* Common: Label */}
            <Field label="Label">
              <input value={(selectedNode.data?.label as string) || ""} onChange={(e) => updateNodeData("label", e.target.value)}
                className="w-full text-xs rounded-lg px-3 py-2 outline-none"
                style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
            </Field>

            {/* Input: parameters this workflow asks for */}
            {selectedNode.type === "input" && (
              <>
                <Field label="Tham số đầu vào">
                  <div className="space-y-2" data-testid="input-fields">
                    {(((selectedNode.data?.fields as InputField[]) || [])).map((f, i) => (
                      <div key={i} className="rounded-lg p-2 space-y-1.5" style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
                        <div className="flex gap-1.5">
                          <input value={f.name || ""} placeholder="ma_bien"
                            onChange={(e) => updateFieldAt(i, { name: e.target.value })}
                            className="flex-1 text-[11px] rounded px-2 py-1 outline-none font-mono" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                          <select value={f.type || "string"} onChange={(e) => updateFieldAt(i, { type: e.target.value as InputField["type"] })}
                            className="text-[11px] rounded px-1 py-1 outline-none" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}>
                            <option value="string">chữ</option>
                            <option value="text">đoạn văn</option>
                            <option value="number">số</option>
                            <option value="date">ngày</option>
                            <option value="boolean">có/không</option>
                            <option value="select">chọn</option>
                          </select>
                        </div>
                        <input value={f.label || ""} placeholder="Nhãn hiển thị"
                          onChange={(e) => updateFieldAt(i, { label: e.target.value })}
                          className="w-full text-[11px] rounded px-2 py-1 outline-none" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                        {f.type === "select" && (
                          <input value={(f.options || []).join(", ")} placeholder="giá trị 1, giá trị 2"
                            onChange={(e) => updateFieldAt(i, { options: e.target.value.split(",").map((o) => o.trim()).filter(Boolean) })}
                            className="w-full text-[11px] rounded px-2 py-1 outline-none" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                        )}
                        <div className="flex items-center justify-between text-[10px]" style={{ color: "var(--muted)" }}>
                          <label className="flex items-center gap-1">
                            <input type="checkbox" checked={!!f.required} onChange={(e) => updateFieldAt(i, { required: e.target.checked })} />
                            bắt buộc
                          </label>
                          <button onClick={() => updateNodeData("fields", ((selectedNode.data?.fields as InputField[]) || []).filter((_, j) => j !== i))}
                            style={{ color: "#ef4444" }}>Xoá</button>
                        </div>
                      </div>
                    ))}
                    <button onClick={() => updateNodeData("fields", [...(((selectedNode.data?.fields as InputField[]) || [])), { name: `tham_so_${(((selectedNode.data?.fields as InputField[]) || []).length) + 1}`, label: "", type: "string", required: false }])}
                      className="w-full text-[11px] rounded-lg px-2 py-1.5" style={{ border: "1px dashed var(--border)", color: "var(--muted)" }}
                      data-testid="add-input-field">+ Thêm tham số</button>
                  </div>
                </Field>
                <p className="text-[10px] -mt-1" style={{ color: "var(--muted)" }}>
                  Tham số hiện thành form khi chạy báo cáo và khi đặt lịch. Dùng trong node khác bằng {"{{inputs.ten_bien}}"}.
                </p>
              </>
            )}

            {/* Tool call */}
            {selectedNode.type === "tool_call" && (
              <>
                <Field label="Công cụ (registry của đơn vị)">
                  <select value={(selectedNode.data?.tool_id as string) || ""} onChange={(e) => updateNodeData("tool_id", e.target.value)}
                    className="w-full text-xs rounded-lg px-3 py-2 outline-none" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} data-testid="tool-select">
                    <option value="">— chọn công cụ —</option>
                    {tools.filter((t) => t.kind !== "mcp").map((t) => (
                      <option key={t.id} value={t.id}>{t.name} ({t.slug}){t.requires_approval ? " · cần duyệt" : ""}</option>
                    ))}
                  </select>
                </Field>
                {(() => {
                  const t = tools.find((x) => x.id === selectedNode.data?.tool_id);
                  if (!t) return null;
                  const props = Object.keys((t.params_schema as any)?.properties || {});
                  return (
                    <p className="text-[10px] -mt-1" style={{ color: t.requires_approval ? "#ef4444" : "var(--muted)" }}>
                      {t.requires_approval
                        ? "Công cụ cần người duyệt — luồng báo cáo chạy tự động nên sẽ bị từ chối."
                        : `Tham số: ${props.join(", ") || "không có"}`}
                    </p>
                  );
                })()}
                {(() => {
                  const t = tools.find((x) => x.id === selectedNode.data?.tool_id);
                  if (t?.kind !== "mcp") return null;
                  const names = mcpTools[t.id];
                  return (
                    <Field label="Công cụ trên MCP server">
                      {names && names.length > 0 ? (
                        <select value={(selectedNode.data?.mcp_tool as string) || ""} onChange={(e) => updateNodeData("mcp_tool", e.target.value)}
                          className="w-full text-xs rounded-lg px-3 py-2 outline-none" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} data-testid="mcp-tool-select">
                          <option value="">— chọn —</option>
                          {names.map((n) => <option key={n} value={n}>{n}</option>)}
                        </select>
                      ) : (
                        <input value={(selectedNode.data?.mcp_tool as string) || ""} onChange={(e) => updateNodeData("mcp_tool", e.target.value)}
                          placeholder={names ? "server không trả về công cụ nào" : "đang dò..."}
                          className="w-full text-xs rounded-lg px-3 py-2 outline-none font-mono" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                      )}
                    </Field>
                  );
                })()}
                <Field label="Tên kết quả (alias)">
                  <input value={(selectedNode.data?.alias as string) || ""} onChange={(e) => updateNodeData("alias", e.target.value)}
                    placeholder="ho_so" className="w-full text-xs rounded-lg px-3 py-2 outline-none font-mono" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                </Field>
                <Field label="Tham số gọi (JSON)">
                  <textarea value={JSON.stringify(selectedNode.data?.args || {}, null, 2)}
                    onChange={(e) => { try { updateNodeData("args", JSON.parse(e.target.value)); } catch { /* đang gõ */ } }}
                    rows={5} className="w-full text-xs rounded-lg px-3 py-2 outline-none resize-y font-mono" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                </Field>
                <p className="text-[10px] -mt-1" style={{ color: "var(--muted)" }}>
                  Dùng {"{{inputs.ten_bien}}"}, {"{{params.x}}"}. Kết quả đọc bằng {"{{tool_results.alias}}"}.
                </p>
              </>
            )}

            {/* Render document */}
            {selectedNode.type === "render_document" && (
              <>
                <Field label="Định dạng">
                  <select value={(selectedNode.data?.format as string) || "markdown"} onChange={(e) => updateNodeData("format", e.target.value)}
                    className="w-full text-xs rounded-lg px-3 py-2 outline-none" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} data-testid="doc-format">
                    <option value="markdown">Markdown (.md)</option>
                    <option value="docx">Word (.docx) theo mẫu</option>
                    <option value="xlsx">Excel (.xlsx) dạng bảng</option>
                  </select>
                </Field>
                <Field label="Tiêu đề">
                  <input value={(selectedNode.data?.title as string) || ""} onChange={(e) => updateNodeData("title", e.target.value)}
                    className="w-full text-xs rounded-lg px-3 py-2 outline-none" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                </Field>
                <Field label="Tên tệp">
                  <input value={(selectedNode.data?.filename as string) || ""} onChange={(e) => updateNodeData("filename", e.target.value)}
                    className="w-full text-xs rounded-lg px-3 py-2 outline-none" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                </Field>
                <Field label="Người xem">
                  <select value={(selectedNode.data?.audience as string) || "admin"} onChange={(e) => updateNodeData("audience", e.target.value)}
                    className="w-full text-xs rounded-lg px-3 py-2 outline-none" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}>
                    <option value="admin">Chỉ quản trị đơn vị</option>
                    <option value="staff">Cán bộ trong đơn vị (Báo cáo của tôi)</option>
                  </select>
                </Field>
                {((selectedNode.data?.format as string) || "markdown") === "xlsx" ? (
                  <>
                    <Field label="Sheet & cột (JSON)">
                      <textarea value={JSON.stringify(selectedNode.data?.sheets || [], null, 2)}
                        onChange={(e) => { try { updateNodeData("sheets", JSON.parse(e.target.value)); } catch { /* đang gõ */ } }}
                        rows={12} spellCheck={false} data-testid="xlsx-sheets"
                        className="w-full text-xs rounded-lg px-3 py-2 outline-none resize-y font-mono" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                    </Field>
                    <button onClick={() => updateNodeData("sheets", [...(((selectedNode.data?.sheets as any[]) || [])), {
                        name: `Sheet ${(((selectedNode.data?.sheets as any[]) || []).length) + 1}`,
                        rows: "{{tool_results.ket_qua.danh_sach}}",
                        columns: [{ header: "Cột A", field: "ma" }, { header: "Số tiền", field: "so_tien", format: "money", total: true }],
                      }])}
                      className="w-full text-[11px] rounded-lg px-2 py-1.5" style={{ border: "1px dashed var(--border)", color: "var(--muted)" }}
                      data-testid="add-sheet">+ Thêm sheet mẫu</button>
                    <p className="text-[10px]" style={{ color: "var(--muted)" }}>
                      Mỗi sheet: <code>name</code>, <code>rows</code> (đường dẫn tới danh sách, vd {"{{tool_results.doanh_so.chi_nhanh}}"}),
                      <code>columns</code> (header + field, format <code>money | int | number | percent</code>, <code>total: true</code> để cộng tổng),
                      <code>summary</code> (các dòng nhãn – giá trị).
                    </p>
                  </>
                ) : ((selectedNode.data?.format as string) || "markdown") === "docx" ? (
                  <>
                    <Field label="Mẫu .docx">
                      <input type="file" accept=".docx" data-testid="template-upload"
                        onChange={async (e) => {
                          const file = e.target.files?.[0];
                          if (!file) return;
                          try {
                            const res = await uploadWorkflowTemplate(workflowId, file);
                            updateNodeData("template_key", res.template_key);
                            updateNodeData("template_name", res.filename);
                            alert(`Đã tải mẫu. Placeholder: ${res.variables.join(", ") || "không có"}`);
                          } catch (err: any) { alert(err?.message || "Tải mẫu thất bại"); }
                        }}
                        className="w-full text-[11px]" style={{ color: "var(--muted)" }} />
                    </Field>
                    <p className="text-[10px] -mt-1 break-all" style={{ color: "var(--muted)" }}>
                      {selectedNode.data?.template_key ? `Đang dùng: ${selectedNode.data?.template_name || selectedNode.data?.template_key}` : "Chưa có mẫu"}
                    </p>
                  </>
                ) : (
                  <Field label="Mẫu Markdown (Jinja)">
                    <textarea value={(selectedNode.data?.template as string) || ""} onChange={(e) => updateNodeData("template", e.target.value)}
                      rows={10} spellCheck={false}
                      className="w-full text-xs rounded-lg px-3 py-2 outline-none resize-y font-mono" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                  </Field>
                )}
                <Field label="Biến rút gọn cho mẫu (JSON)">
                  <textarea value={JSON.stringify(selectedNode.data?.vars || {}, null, 2)}
                    onChange={(e) => { try { updateNodeData("vars", JSON.parse(e.target.value)); } catch { /* đang gõ */ } }}
                    rows={4} className="w-full text-xs rounded-lg px-3 py-2 outline-none resize-y font-mono" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                </Field>
                <p className="text-[10px] -mt-1" style={{ color: "var(--muted)" }}>
                  Biến có sẵn: {"{{ tool_results }} {{ answer }} {{ inputs }} {{ today }}"} · bộ lọc: {"| tien | so | ngay"}
                </p>
              </>
            )}

            {/* Retrieve */}
            {selectedNode.type === "retrieve" && (
              <>
                <Field label="Datasets">
                  <select multiple value={(selectedNode.data?.dataset_ids as string[]) || []}
                    onChange={(e) => updateNodeData("dataset_ids", Array.from(e.target.selectedOptions, (o) => o.value))}
                    className="w-full text-xs rounded-lg px-3 py-2 outline-none"
                    style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)", minHeight: 72 }}>
                    {datasets.map((ds) => <option key={ds.id} value={ds.id}>{ds.name}</option>)}
                  </select>
                </Field>
                <Field label="Top K">
                  <input type="number" min={1} max={20} value={(selectedNode.data?.top_k as number) || 5}
                    onChange={(e) => updateNodeData("top_k", parseInt(e.target.value) || 5)}
                    className="w-full text-xs rounded-lg px-3 py-2 outline-none"
                    style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                </Field>
              </>
            )}

            {/* Compose Prompt */}
            {selectedNode.type === "compose_prompt" && (
              <>
                <Field label="Template">
                  <textarea value={(selectedNode.data?.template as string) || ""} onChange={(e) => updateNodeData("template", e.target.value)}
                    rows={8} className="w-full text-xs rounded-lg px-3 py-2 outline-none resize-y font-mono"
                    style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                </Field>
                <p className="text-[10px] -mt-1" style={{ color: "var(--muted)" }}>{"{{query}} {{context}} {{system_prompt}}"}</p>
              </>
            )}

            {/* LLM */}
            {selectedNode.type === "llm_generate" && (
              <>
                <Field label="Model (empty = default)">
                  <input value={(selectedNode.data?.model as string) || ""} onChange={(e) => updateNodeData("model", e.target.value)}
                    placeholder="e.g. gemini-2.5-flash" className="w-full text-xs rounded-lg px-3 py-2 outline-none"
                    style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                </Field>
                <Field label={`Temperature: ${((selectedNode.data?.temperature as number) ?? 0.7).toFixed(1)}`}>
                  <input type="range" min={0} max={1} step={0.1} value={(selectedNode.data?.temperature as number) ?? 0.7}
                    onChange={(e) => updateNodeData("temperature", parseFloat(e.target.value))} className="w-full" />
                </Field>
                <Field label="Max Tokens">
                  <input type="number" min={100} max={16000} value={(selectedNode.data?.max_tokens as number) || 4096}
                    onChange={(e) => updateNodeData("max_tokens", parseInt(e.target.value) || 4096)}
                    className="w-full text-xs rounded-lg px-3 py-2 outline-none"
                    style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                </Field>
              </>
            )}

            {/* Parameter Extract */}
            {selectedNode.type === "parameter_extract" && (
              <Field label="Schema (JSON: field → description)">
                <textarea value={JSON.stringify(selectedNode.data?.schema || {}, null, 2)}
                  onChange={(e) => { try { updateNodeData("schema", JSON.parse(e.target.value)); } catch {} }}
                  rows={6} className="w-full text-xs rounded-lg px-3 py-2 outline-none resize-y font-mono"
                  style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
              </Field>
            )}

            {/* HTTP Request */}
            {selectedNode.type === "http_request" && (
              <>
                <Field label="Method">
                  <select value={(selectedNode.data?.method as string) || "POST"}
                    onChange={(e) => updateNodeData("method", e.target.value)}
                    className="w-full text-xs rounded-lg px-3 py-2 outline-none"
                    style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}>
                    <option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option>
                  </select>
                </Field>
                <Field label="URL">
                  <input value={(selectedNode.data?.url as string) || ""} onChange={(e) => updateNodeData("url", e.target.value)}
                    placeholder="https://api.example.com/..." className="w-full text-xs rounded-lg px-3 py-2 outline-none"
                    style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                </Field>
                <Field label="Body Template">
                  <textarea value={(selectedNode.data?.body_template as string) || ""} onChange={(e) => updateNodeData("body_template", e.target.value)}
                    rows={5} placeholder='{"name":"{{name}}"}' className="w-full text-xs rounded-lg px-3 py-2 outline-none resize-y font-mono"
                    style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                </Field>
              </>
            )}

            {/* If/Else */}
            {selectedNode.type === "if_else" && (
              <>
                <Field label="Variable (dot path)">
                  <input value={(selectedNode.data?.variable as string) || ""} onChange={(e) => updateNodeData("variable", e.target.value)}
                    placeholder="extracted_params.name" className="w-full text-xs rounded-lg px-3 py-2 outline-none"
                    style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                </Field>
                <Field label="Operator">
                  <select value={(selectedNode.data?.operator as string) || "not_empty"} onChange={(e) => updateNodeData("operator", e.target.value)}
                    className="w-full text-xs rounded-lg px-3 py-2 outline-none"
                    style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}>
                    <option value="exists">exists</option>
                    <option value="not_empty">not empty</option>
                    <option value="equals">equals</option>
                    <option value="contains">contains</option>
                  </select>
                </Field>
                {["equals", "contains"].includes((selectedNode.data?.operator as string) || "") && (
                  <Field label="Compare Value">
                    <input value={(selectedNode.data?.value as string) || ""} onChange={(e) => updateNodeData("value", e.target.value)}
                      className="w-full text-xs rounded-lg px-3 py-2 outline-none"
                      style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                  </Field>
                )}
              </>
            )}

            {/* Answer */}
            {selectedNode.type === "answer" && (
              <Field label="Response Template (empty = use LLM output)">
                <textarea value={(selectedNode.data?.template as string) || ""} onChange={(e) => updateNodeData("template", e.target.value)}
                  rows={5} placeholder="Thank you {{name}}! Your data has been saved."
                  className="w-full text-xs rounded-lg px-3 py-2 outline-none resize-y font-mono"
                  style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
              </Field>
            )}

            {/* Code Execute */}
            {selectedNode.type === "code_execute" && (
              <>
                <Field label="Python Code">
                  <textarea value={(selectedNode.data?.code as string) || ""} onChange={(e) => updateNodeData("code", e.target.value)}
                    rows={12} spellCheck={false}
                    className="w-full text-xs rounded-lg px-3 py-2 outline-none resize-y font-mono"
                    style={{ background: "var(--background)", color: "#6366f1", border: "1px solid var(--border)", lineHeight: 1.6 }} />
                </Field>
                <p className="text-[10px] -mt-1" style={{ color: "var(--muted)" }}>
                  Define main(args) → dict. Args: query, answer, extracted_params, etc.
                </p>
              </>
            )}

            {/* Delete */}
            <div style={{ marginTop: "auto", paddingTop: 12 }}>
              <button onClick={() => {
                  setNodes((nds) => nds.filter((n) => n.id !== selectedNode.id));
                  setEdges((eds) => eds.filter((e) => e.source !== selectedNode.id && e.target !== selectedNode.id));
                  setSelectedNode(null);
                }}
                className="w-full text-xs rounded-lg px-3 py-2 font-medium"
                style={{ background: "rgba(239,68,68,0.08)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.15)" }}>
                Delete Node
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Runs & reports drawer */}
      {runsOpen && (
        <div style={{ position: "fixed", top: 52, right: 0, bottom: 0, width: 420, zIndex: 90, background: "var(--card)",
                      borderLeft: "1px solid var(--border)", overflowY: "auto" }} data-testid="runs-panel">
          <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
            <h3 className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>Lần chạy & báo cáo</h3>
            <div className="flex items-center gap-2">
              <button onClick={loadRuns} className="text-xs rounded px-2 py-1" style={{ color: "var(--muted)", border: "1px solid var(--border)" }}>↻</button>
              <button onClick={() => setRunsOpen(false)} className="text-xs rounded p-1" style={{ color: "var(--muted)" }}>✕</button>
            </div>
          </div>
          {runs.length === 0 ? (
            <p className="text-xs p-4" style={{ color: "var(--muted)" }}>Chưa có lần chạy nào.</p>
          ) : (
            <div className="p-3 space-y-2">
              {runs.map((r) => {
                const tone = r.status === "completed" ? "#22c55e" : r.status === "failed" ? "#ef4444"
                  : r.status === "running" || r.status === "queued" ? "#f59e0b" : "var(--muted)";
                return (
                  <div key={r.id} className="rounded-lg p-3" style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
                    <div className="flex items-center justify-between text-[11px]">
                      <span style={{ color: tone, fontWeight: 600 }}>
                        {r.status === "completed" ? "✓ Hoàn thành" : r.status === "failed" ? "✕ Lỗi"
                          : r.status === "queued" ? "⏳ Đang chờ" : r.status === "running" ? "● Đang chạy" : r.status}
                      </span>
                      <span style={{ color: "var(--muted)" }}>
                        {new Date(r.started_at).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                        {r.latency_ms != null ? ` · ${(r.latency_ms / 1000).toFixed(1)}s` : ""}
                        {r.schedule_id ? " · theo lịch" : r.channel === "report" ? " · chạy nền" : ""}
                      </span>
                    </div>
                    {r.error && <p className="text-[11px] mt-1" style={{ color: "#ef4444" }}>{r.error}</p>}
                    {r.artifacts.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {r.artifacts.map((a) => (
                          <button key={a.id} onClick={() => downloadArtifact(a)} data-testid="artifact-download"
                            className="flex items-center justify-between gap-2 text-[11px] rounded px-2 py-1.5 w-full text-left"
                            style={{ background: "rgba(132,204,22,0.10)", color: "#84cc16" }}>
                            <span className="truncate">📄 {a.title || a.filename}</span>
                            <span style={{ color: "var(--muted)" }}>{formatBytes(a.size)}</span>
                          </button>
                        ))}
                      </div>
                    )}
                    {!r.artifacts.length && r.answer_preview && (
                      <p className="text-[11px] mt-1 line-clamp-2" style={{ color: "var(--muted)" }}>{r.answer_preview}</p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Run Modal */}
      {runModal && (
        <div style={{ position: "fixed", inset: 0, zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
          onClick={() => setRunModal(false)}>
          <div onClick={(e) => e.stopPropagation()} className="rounded-2xl p-6"
            style={{ background: "var(--card)", border: "1px solid var(--border)", width: 520, maxHeight: "80vh", overflow: "auto" }}>
            <h3 className="text-sm font-semibold mb-4" style={{ color: "var(--foreground)" }}>
              {workflowType === "report" ? "📄 Chạy báo cáo" : "🚀 Test Run"}
            </h3>

            {inputFields.length > 0 ? (
              <div className="space-y-3 mb-3" data-testid="run-inputs">
                {inputFields.map((f) => (
                  <Field key={f.name} label={`${f.label || f.name}${f.required ? " *" : ""}`}>
                    {f.type === "boolean" ? (
                      <label className="flex items-center gap-2 text-xs" style={{ color: "var(--foreground)" }}>
                        <input type="checkbox" checked={!!runInputs[f.name]} data-testid={`run-input-${f.name}`}
                          onChange={(e) => setRunInputs((v) => ({ ...v, [f.name]: e.target.checked }))} />
                        {f.description || "Có"}
                      </label>
                    ) : f.type === "select" ? (
                      <select value={runInputs[f.name] ?? ""} data-testid={`run-input-${f.name}`}
                        onChange={(e) => setRunInputs((v) => ({ ...v, [f.name]: e.target.value }))}
                        className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}>
                        <option value="">—</option>
                        {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : f.type === "text" ? (
                      <textarea value={runInputs[f.name] ?? ""} rows={3} data-testid={`run-input-${f.name}`}
                        onChange={(e) => setRunInputs((v) => ({ ...v, [f.name]: e.target.value }))}
                        className="w-full text-sm rounded-lg px-3 py-2 outline-none resize-y" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                    ) : (
                      <input type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
                        value={runInputs[f.name] ?? ""} placeholder={f.description || ""} data-testid={`run-input-${f.name}`}
                        onChange={(e) => setRunInputs((v) => ({ ...v, [f.name]: e.target.value }))}
                        className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
                    )}
                  </Field>
                ))}
              </div>
            ) : (
              <Field label="Câu hỏi">
                <textarea value={runQuery} onChange={(e) => setRunQuery(e.target.value)} rows={3} placeholder="Nhập câu hỏi thử..."
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none resize-none" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }} />
              </Field>
            )}

            <div className="flex items-center gap-2 mt-2 mb-4">
              <button onClick={handleRun} disabled={running || (inputFields.length === 0 && !runQuery.trim())}
                className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium"
                style={{ background: running ? "var(--border)" : "var(--accent)", color: "#fff" }} data-testid="run-now">
                {running ? <><div className="animate-spin rounded-full h-3 w-3 border-2 border-current" style={{ borderTopColor: "transparent" }} /> Đang chạy...</> : "Chạy ngay"}
              </button>
              <button onClick={handleQueue} disabled={running}
                className="rounded-lg px-4 py-2 text-sm font-medium"
                style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}
                data-testid="run-queue" title="Chạy nền trên jobs worker — không phải chờ cửa sổ này">
                Chạy nền
              </button>
            </div>
            {queueMsg && <p className="text-xs mb-3" style={{ color: queueMsg.startsWith("Lỗi") ? "#ef4444" : "#22c55e" }}>{queueMsg}</p>}
            {runResult && (
              <div className="space-y-3">
                <Field label="Answer">
                  <div className="text-sm p-3 rounded-lg" style={{ background: "var(--background)", color: "var(--foreground)", whiteSpace: "pre-wrap" }}>
                    {runResult.answer}
                  </div>
                </Field>
                {Object.keys(runResult.extracted_params || {}).length > 0 && (
                  <Field label="Extracted Parameters">
                    <pre className="text-xs p-3 rounded-lg font-mono" style={{ background: "var(--background)", color: "#14b8a6" }}>
                      {JSON.stringify(runResult.extracted_params, null, 2)}
                    </pre>
                  </Field>
                )}
                {runResult.artifacts?.length > 0 && (
                  <Field label="Tệp đã tạo">
                    <div className="space-y-1.5" data-testid="run-artifacts">
                      {runResult.artifacts.map((a, i) => a.error ? (
                        <p key={i} className="text-xs" style={{ color: "#ef4444" }}>⚠️ {a.error}</p>
                      ) : (
                        <button key={a.id || i} onClick={() => downloadArtifact({ id: a.id!, filename: a.filename || "bao-cao" })}
                          className="flex items-center gap-2 text-xs rounded-lg px-3 py-2 w-full text-left"
                          style={{ background: "rgba(132,204,22,0.10)", color: "#84cc16", border: "1px solid rgba(132,204,22,0.25)" }}>
                          📄 {a.title || a.filename} <span style={{ color: "var(--muted)" }}>· tải về</span>
                        </button>
                      ))}
                    </div>
                  </Field>
                )}
                {runResult.retriever_resources.length > 0 && (
                  <Field label={`Sources (${runResult.retriever_resources.length})`}>
                    <div className="flex flex-wrap gap-1.5">
                      {runResult.retriever_resources.map((r, i) => (
                        <span key={i} className="text-xs px-2 py-0.5 rounded-md" style={{ background: "var(--accent-glow)", color: "var(--accent)" }}>
                          📄 {r.filename || "doc"} §{r.chunk_index}
                        </span>
                      ))}
                    </div>
                  </Field>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* Helper */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[11px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>{label}</label>
      {children}
    </div>
  );
}
