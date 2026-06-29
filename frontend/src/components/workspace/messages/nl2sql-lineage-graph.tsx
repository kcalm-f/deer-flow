"use client";

import type {
  Edge as FlowEdge,
  EdgeProps,
  Node as FlowNode,
} from "@xyflow/react";
import { BaseEdge, getStraightPath, MarkerType, Position } from "@xyflow/react";
import {
  CalculatorIcon,
  DatabaseIcon,
  FileCheckIcon,
  GitBranchIcon,
  LineChartIcon,
  NotebookTextIcon,
  XIcon,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Canvas } from "@/components/ai-elements/canvas";
import {
  Node,
  NodeContent,
  NodeDescription,
  NodeHeader,
  NodeTitle,
} from "@/components/ai-elements/node";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

type LineageNodeType =
  | "claim"
  | "calculation"
  | "query_data"
  | "metric_metadata"
  | "validation"
  | "evidence";

type LineageNode = {
  id: string;
  type: LineageNodeType;
  label?: string;
  evidence_id?: string;
  claim_id?: string;
  field?: string;
  value?: unknown;
  unit?: string;
  status?: string;
  row_count?: number;
  index?: string;
  details?: Record<string, unknown>;
  slices?: Record<string, unknown>;
};

type LineageEdge = {
  id?: string;
  source: string;
  target: string;
  type?: string;
};

export type Nl2sqlLineage = {
  version: number;
  nodes: LineageNode[];
  edges: LineageEdge[];
  index_map?: Record<string, string>;
  missing?: Array<Record<string, string>>;
};

type NodeData = {
  node: LineageNode;
  selected: boolean;
  onOpenDetails: (node: LineageNode) => void;
};

const NODE_WIDTH = 260;
const NODE_HEIGHT = 158;

// 节点类型配色方案
const NODE_TYPE_STYLES: Record<
  LineageNodeType,
  {
    border: string;
    iconBg: string;
    iconColor: string;
    badgeVariant: "default" | "secondary" | "outline" | "destructive";
  }
> = {
  claim: {
    border: "border-blue-200 dark:border-blue-800",
    iconBg: "bg-blue-100 dark:bg-blue-900/50",
    iconColor: "text-blue-600 dark:text-blue-400",
    badgeVariant: "default",
  },
  calculation: {
    border: "border-purple-200 dark:border-purple-800",
    iconBg: "bg-purple-100 dark:bg-purple-900/50",
    iconColor: "text-purple-600 dark:text-purple-400",
    badgeVariant: "secondary",
  },
  query_data: {
    border: "border-emerald-200 dark:border-emerald-800",
    iconBg: "bg-emerald-100 dark:bg-emerald-900/50",
    iconColor: "text-emerald-600 dark:text-emerald-400",
    badgeVariant: "outline",
  },
  metric_metadata: {
    border: "border-amber-200 dark:border-amber-800",
    iconBg: "bg-amber-100 dark:bg-amber-900/50",
    iconColor: "text-amber-600 dark:text-amber-400",
    badgeVariant: "outline",
  },
  validation: {
    border: "border-rose-200 dark:border-rose-800",
    iconBg: "bg-rose-100 dark:bg-rose-900/50",
    iconColor: "text-rose-600 dark:text-rose-400",
    badgeVariant: "destructive",
  },
  evidence: {
    border: "border-slate-200 dark:border-slate-700",
    iconBg: "bg-slate-100 dark:bg-slate-800",
    iconColor: "text-slate-600 dark:text-slate-400",
    badgeVariant: "outline",
  },
};

// 边类型配色
const EDGE_TYPE_COLORS: Record<string, string> = {
  derived_from: "#6366f1",
  calculated_from: "#a855f7",
  uses_metric_caliber: "#f59e0b",
  validates: "#ef4444",
};

function typeLabel(type: LineageNodeType) {
  switch (type) {
    case "claim":
      return "结论值";
    case "calculation":
      return "计算";
    case "query_data":
      return "查询数据";
    case "metric_metadata":
      return "指标口径";
    case "validation":
      return "校验";
    default:
      return "证据";
  }
}

function TypeIcon({
  type,
  className,
}: {
  type: LineageNodeType;
  className?: string;
}) {
  const props = { className: cn("size-4", className) };
  switch (type) {
    case "claim":
      return <LineChartIcon {...props} />;
    case "calculation":
      return <CalculatorIcon {...props} />;
    case "query_data":
      return <DatabaseIcon {...props} />;
    case "metric_metadata":
      return <NotebookTextIcon {...props} />;
    case "validation":
      return <FileCheckIcon {...props} />;
    default:
      return <GitBranchIcon {...props} />;
  }
}

function displayValue(value: unknown, unit?: string) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "object") return null;
  return `${formatCellValue(value)}${unit ?? ""}`;
}

function formatCellValue(value: unknown) {
  if (value === null || value === undefined) return "";
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint"
  ) {
    return String(value);
  }
  return JSON.stringify(value);
}

function LineageGraphNode({ data }: { data: NodeData }) {
  const { node, selected, onOpenDetails } = data;
  const styles = NODE_TYPE_STYLES[node.type] ?? NODE_TYPE_STYLES.evidence;

  const primaryValue =
    node.type === "claim"
      ? displayValue(node.value, node.unit)
      : node.type === "query_data" && typeof node.row_count === "number"
        ? `${node.row_count} 行`
        : node.evidence_id;

  return (
    <Node
      handles={{ target: true, source: true }}
      className={cn(
        "w-[240px] cursor-pointer rounded-xl border bg-white/95 shadow-sm backdrop-blur-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md",
        styles.border,
        selected &&
          "border-primary ring-primary/30 scale-[1.02] shadow-md ring-2",
      )}
      onClick={() => onOpenDetails(node)}
      onDoubleClick={() => onOpenDetails(node)}
    >
      <NodeHeader className="px-3 pt-3 pb-2!">
        <div className="flex items-center gap-2.5">
          <div
            className={cn(
              "flex size-7 items-center justify-center rounded-lg",
              styles.iconBg,
            )}
          >
            <TypeIcon type={node.type} className={styles.iconColor} />
          </div>
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <NodeTitle className="truncate text-xs font-semibold">
              {typeLabel(node.type)}
            </NodeTitle>
            <NodeDescription className="text-muted-foreground/70 truncate text-[10px]">
              {node.claim_id ?? node.evidence_id ?? node.id}
            </NodeDescription>
          </div>
        </div>
      </NodeHeader>
      <NodeContent className="space-y-2.5 px-3 pb-3">
        <div className="text-foreground/90 line-clamp-2 text-xs leading-relaxed font-medium">
          {node.label ?? node.id}
        </div>
        {primaryValue && (
          <Badge
            variant={styles.badgeVariant}
            className="max-w-full truncate rounded-md text-[11px] font-medium"
          >
            {primaryValue}
          </Badge>
        )}
      </NodeContent>
    </Node>
  );
}

const nodeTypes = { lineage: LineageGraphNode };

// 自定义边组件：标签对齐到直线中点
function LabeledStraightEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  style = {},
  markerEnd,
  label,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getStraightPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
  });

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} markerEnd={markerEnd} />
      {label && (
        <foreignObject
          x={labelX - 28}
          y={labelY - 12}
          width={56}
          height={24}
          style={{ overflow: "visible" }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: "100%",
              height: "100%",
              fontSize: 11,
              fontWeight: 500,
              color: "#475569",
              background: "rgba(248,250,252,0.92)",
              borderRadius: 6,
              padding: "2px 6px",
              whiteSpace: "nowrap",
              border: "1px solid rgba(0,0,0,0.06)",
            }}
          >
            {label}
          </div>
        </foreignObject>
      )}
    </>
  );
}

const edgeTypes = { "labeled-straight": LabeledStraightEdge };

function nodePosition(type: LineageNodeType, order: number) {
  const xByType: Record<LineageNodeType, number> = {
    validation: 0,
    claim: 320,
    calculation: 640,
    evidence: 640,
    query_data: 960,
    metric_metadata: 1280,
  };
  return {
    x: xByType[type] ?? 0,
    y: 40 + order * 185,
  };
}

function buildFlowElements(
  lineage: Nl2sqlLineage,
  selectedId: string | null,
  onOpenDetails: (node: LineageNode) => void,
) {
  const orderByType = new Map<LineageNodeType, number>();
  const nodes: FlowNode<NodeData>[] = lineage.nodes.map((node) => {
    const order = orderByType.get(node.type) ?? 0;
    orderByType.set(node.type, order + 1);
    return {
      id: node.id,
      type: "lineage",
      position: nodePosition(node.type, order),
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: {
        node,
        selected: node.id === selectedId,
        onOpenDetails,
      },
      style: { width: NODE_WIDTH, height: NODE_HEIGHT },
    };
  });
  const edges: FlowEdge[] = lineage.edges.map((edge) => ({
    id: edge.id ?? `${edge.source}-${edge.target}-${edge.type ?? "lineage"}`,
    source: edge.source,
    target: edge.target,
    type: "labeled-straight",
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: edge.type ? (EDGE_TYPE_COLORS[edge.type] ?? "#94a3b8") : "#94a3b8",
    },
    label: edge.type ? edgeLabel(edge.type) : undefined,
    style: {
      strokeWidth: 2,
      stroke: edge.type
        ? (EDGE_TYPE_COLORS[edge.type] ?? "#94a3b8")
        : "#94a3b8",
    },
  }));
  return { nodes, edges };
}

function edgeLabel(type: string) {
  switch (type) {
    case "derived_from":
      return "来自";
    case "calculated_from":
      return "计算自";
    case "uses_metric_caliber":
      return "口径";
    case "validates":
      return "校验";
    default:
      return type;
  }
}

function asRows(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is Record<string, unknown> =>
      typeof item === "object" && item !== null && !Array.isArray(item),
  );
}

function DetailField({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "object") return null;
  return (
    <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
      <div className="text-muted-foreground text-xs font-medium">{label}</div>
      <div className="text-foreground/90 break-words">
        {formatCellValue(value)}
      </div>
    </div>
  );
}

function JsonBlock({
  value,
  maxHeight,
}: {
  value: unknown;
  maxHeight?: string;
}) {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") {
    return (
      <pre
        className={cn(
          "bg-muted/60 border-border/50 overflow-auto rounded-lg border p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap",
          maxHeight ?? "max-h-56",
        )}
      >
        {value}
      </pre>
    );
  }
  return (
    <pre
      className={cn(
        "bg-muted/60 border-border/50 overflow-auto rounded-lg border p-3 font-mono text-xs leading-relaxed",
        maxHeight ?? "max-h-56",
      )}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function DataRows({
  title,
  rows,
}: {
  title: string;
  rows: Array<Record<string, unknown>>;
}) {
  if (rows.length === 0) return null;
  const columns = Array.from(
    rows.reduce((set, row) => {
      Object.keys(row).forEach((key) => set.add(key));
      return set;
    }, new Set<string>()),
  );
  return (
    <div className="space-y-2">
      <div className="text-foreground/80 text-xs font-semibold">{title}</div>
      <div className="border-border/60 overflow-auto rounded-lg border">
        <table className="w-full min-w-max text-xs">
          <thead className="bg-muted/80">
            <tr>
              {columns.map((column) => (
                <th
                  key={column}
                  className="text-muted-foreground px-3 py-2 text-left font-semibold"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr
                key={index}
                className={cn(
                  "border-border/40 hover:bg-muted/30 border-t transition-colors",
                  index % 2 === 0 && "bg-background",
                )}
              >
                {columns.map((column) => (
                  <td key={column} className="text-foreground/80 px-3 py-2">
                    {formatCellValue(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function NodeDetails({ node }: { node: LineageNode }) {
  const details = node.details ?? {};
  const slices = node.slices ?? {};
  const styles = NODE_TYPE_STYLES[node.type] ?? NODE_TYPE_STYLES.evidence;

  return (
    <div className="space-y-5">
      {/* 基本信息区 */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <div
            className={cn(
              "flex size-8 items-center justify-center rounded-lg",
              styles.iconBg,
            )}
          >
            <TypeIcon
              type={node.type}
              className={cn("size-4", styles.iconColor)}
            />
          </div>
          <Badge
            variant={styles.badgeVariant}
            className="rounded-md text-xs font-medium"
          >
            {typeLabel(node.type)}
          </Badge>
        </div>
        <h3 className="text-base leading-snug font-semibold">
          {node.label ?? node.id}
        </h3>
        <div className="bg-muted/30 space-y-1.5 rounded-lg p-3">
          <DetailField label="Claim" value={node.claim_id} />
          <DetailField label="证据" value={node.evidence_id} />
          <DetailField label="状态" value={node.status} />
          <DetailField label="字段" value={node.field} />
          <DetailField label="值" value={displayValue(node.value, node.unit)} />
          <DetailField label="行数" value={node.row_count} />
        </div>
      </div>

      {/* 分隔线 */}
      <div className="border-border/50 border-t" />

      {node.type === "calculation" && (
        <div className="space-y-3">
          <SectionTitle>计算过程</SectionTitle>
          <div className="bg-muted/30 space-y-1.5 rounded-lg p-3">
            <DetailField label="操作" value={details.operation} />
            <DetailField
              label="计划步骤"
              value={details.calculation_plan_step_id}
            />
            <DetailField label="代码哈希" value={details.code_hash} />
            <DetailField label="输入哈希" value={details.input_data_hash} />
            <DetailField label="输出哈希" value={details.output_hash} />
          </div>
          <JsonBlock value={details.diagnostics} />
          {typeof details.code === "string" && (
            <pre className="bg-muted/60 border-border/50 max-h-72 overflow-auto rounded-lg border p-3 font-mono text-xs leading-relaxed">
              {details.code}
            </pre>
          )}
        </div>
      )}

      {node.type === "query_data" && (
        <div className="space-y-4">
          <SectionTitle>来源数据切片</SectionTitle>
          <DataRows title="全国/汇总行" rows={asRows(slices.national_rows)} />
          <DataRows title="相关维度行" rows={asRows(slices.matched_rows)} />
          <DataRows title="省级汇总排名行" rows={asRows(slices.summary_rows)} />
          <JsonBlock value={details.field_binding} />
        </div>
      )}

      {node.type === "metric_metadata" && (
        <div className="space-y-3">
          <SectionTitle>指标口径</SectionTitle>
          <div className="bg-muted/30 space-y-1.5 rounded-lg p-3">
            <DetailField label="指标" value={details.metric_name} />
            <DetailField label="编码" value={details.metric_code} />
            <DetailField label="单位" value={details.unit} />
            <DetailField label="周期" value={details.period} />
            <DetailField label="维度" value={details.dimensions} />
            <DetailField label="评价" value={details.evaluation_criteria} />
          </div>
          <JsonBlock value={details.business_caliber} maxHeight="max-h-96" />
          <JsonBlock value={details.data_acquisition_config} />
        </div>
      )}

      {node.type === "validation" && (
        <div className="space-y-4">
          <SectionTitle>校验信息</SectionTitle>
          {(() => {
            const summary = (details.validation_summary ?? {}) as Record<
              string,
              unknown
            >;
            const riskSummary = Array.isArray(summary.risk_summary)
              ? (summary.risk_summary as Array<Record<string, unknown>>)
              : [];
            const checkedClaimIds = Array.isArray(summary.checked_claim_ids)
              ? (summary.checked_claim_ids as string[])
              : [];
            const isOk = summary.ok === true;
            return (
              <>
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={isOk ? "default" : "destructive"}
                      className="rounded-md text-xs font-medium"
                    >
                      {isOk ? "校验通过" : "校验未通过"}
                    </Badge>
                    {summary.requires_semantic_review === true && (
                      <Badge
                        variant="secondary"
                        className="rounded-md text-xs font-medium"
                      >
                        需语义评审
                      </Badge>
                    )}
                  </div>
                  <div className="bg-muted/30 space-y-1.5 rounded-lg p-3">
                    <DetailField
                      label="草稿"
                      value={
                        summary.draft_id
                          ? `${summary.draft_id as string}${summary.draft_version ? ` v${summary.draft_version as string}` : ""}`
                          : undefined
                      }
                    />
                    <DetailField
                      label="校验 Claim 数"
                      value={summary.checked_claim_count as number}
                    />
                    <DetailField
                      label="致命风险"
                      value={summary.fatal_risk_count as number}
                    />
                    <DetailField
                      label="可裁决风险"
                      value={summary.adjudicable_risk_count as number}
                    />
                    <DetailField
                      label="总风险数"
                      value={summary.total_risk_count as number}
                    />
                  </div>
                </div>
                {riskSummary.length > 0 && (
                  <div className="space-y-2">
                    <div className="text-muted-foreground text-xs font-semibold">
                      风险类型分布
                    </div>
                    <div className="space-y-1.5">
                      {riskSummary.map((item, index) => (
                        <div
                          key={index}
                          className="bg-muted/40 flex items-center justify-between rounded-lg px-3 py-2 text-xs"
                        >
                          <span className="text-foreground/80 truncate font-mono">
                            {(item.type ?? "") as string}
                          </span>
                          <Badge
                            variant="outline"
                            className="ml-2 shrink-0 text-xs font-medium"
                          >
                            {(item.count ?? 0) as number}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {checkedClaimIds.length > 0 && (
                  <div className="space-y-2">
                    <div className="text-muted-foreground text-xs font-semibold">
                      已校验 Claim
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {checkedClaimIds.map((claimId) => (
                        <Badge
                          key={claimId}
                          variant="outline"
                          className="font-mono text-xs font-medium"
                        >
                          {claimId}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
                <DetailField label="渲染哈希" value={details.rendered_sha256} />
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
}

// 区域标题组件
function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-foreground/90 flex items-center gap-2 text-sm font-semibold">
      <div className="bg-primary/60 h-4 w-0.5 rounded-full" />
      {children}
    </div>
  );
}

export function Nl2sqlLineageGraph({
  lineage,
}: {
  lineage: Nl2sqlLineage | null;
}) {
  const [open, setOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(
    lineage?.nodes[0]?.id ?? null,
  );

  const selectedNode = useMemo(() => {
    if (!lineage) return null;
    return (
      lineage.nodes.find((node) => node.id === selectedId) ??
      lineage.nodes[0] ??
      null
    );
  }, [lineage, selectedId]);

  const { nodes, edges } = useMemo(() => {
    if (!lineage) return { nodes: [], edges: [] };
    return buildFlowElements(lineage, selectedNode?.id ?? null, selectNode);

    function selectNode(node: LineageNode) {
      setSelectedId(node.id);
    }
  }, [lineage, selectedNode?.id]);

  if (!lineage || !Array.isArray(lineage.nodes) || lineage.nodes.length === 0) {
    return null;
  }

  return (
    <div className="mt-3">
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="gap-2 rounded-lg font-medium transition-all hover:shadow-sm"
        onClick={() => setOpen(true)}
      >
        <GitBranchIcon className="size-4" />
        数据血缘
      </Button>
      {open && (
        <>
          <button
            type="button"
            aria-label="关闭数据血缘"
            className="fixed inset-0 z-[70] bg-black/50 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <section
            aria-label="NL2SQL 数据血缘"
            aria-modal="true"
            role="dialog"
            className="bg-background fixed inset-y-0 right-0 z-[80] flex w-[96vw] max-w-[1600px] flex-col border-l shadow-2xl"
          >
            {/* 标题栏 */}
            <div className="from-background to-muted/30 flex items-start justify-between gap-4 border-b bg-gradient-to-r px-6 py-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2.5">
                  <div className="bg-primary/10 flex size-8 items-center justify-center rounded-lg">
                    <GitBranchIcon className="text-primary size-4" />
                  </div>
                  <h2 className="text-lg font-bold tracking-tight">
                    NL2SQL 数据血缘
                  </h2>
                </div>
                <p className="text-muted-foreground pl-10 text-sm">
                  结论值、计算证据、查询数据、指标口径和校验证据的可追溯关系。
                </p>
              </div>
              <Button
                aria-label="关闭数据血缘"
                size="icon-sm"
                variant="ghost"
                className="rounded-lg"
                onClick={() => setOpen(false)}
              >
                <XIcon className="size-4" />
              </Button>
            </div>
            {/* 内容区 */}
            <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_480px] max-lg:grid-cols-1">
              {/* 画布区 */}
              <div className="to-muted/20 min-h-0 border-r bg-gradient-to-br from-slate-50/50 max-lg:min-h-[56vh] max-lg:border-r-0 max-lg:border-b">
                <Canvas
                  nodes={nodes}
                  edges={edges}
                  nodeTypes={nodeTypes}
                  edgeTypes={edgeTypes}
                  fitView
                  minZoom={0.35}
                  maxZoom={1.2}
                  nodesDraggable={false}
                  nodesConnectable={false}
                  elementsSelectable={true}
                  onNodeClick={(_, node) => {
                    const lineageNode = lineage.nodes.find(
                      (item) => item.id === node.id,
                    );
                    if (!lineageNode) return;
                    setSelectedId(lineageNode.id);
                  }}
                />
              </div>
              {/* 详情面板 */}
              <ScrollArea className="min-h-0">
                <div className="space-y-5 p-5">
                  <div className="space-y-1">
                    <div className="text-foreground/90 text-sm font-bold">
                      节点详情
                    </div>
                    {selectedNode && (
                      <div className="text-muted-foreground truncate font-mono text-xs">
                        {selectedNode.id}
                      </div>
                    )}
                  </div>
                  {selectedNode && <NodeDetails node={selectedNode} />}
                </div>
              </ScrollArea>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
