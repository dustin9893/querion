"use client";

import { isValidElement } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ChartBlock from "./ChartBlock";

interface Props {
  children: string;
  /** Inline CSS colour for the citation badges `[#n]`; defaults to currentColor */
  accent?: string;
  className?: string;
}

/**
 * Renders LLM answers (GitHub-flavoured markdown) and turns `[#n]` citation
 * markers into small badges so they line up with the source chips below.
 * Styling is inline-scoped (`.md-body`) so it works in the staff portal,
 * the customer page and the admin audit drawer without global CSS.
 */
export default function Markdown({ children, accent, className }: Props) {
  const badge = accent || "currentColor";
  // Wrap [#n] (and comma lists like [#1], [#3]) into a marker the text renderer can style.
  const withMarkers = children.replace(/\[#(\d+)\]/g, "⟦$1⟧");

  return (
    <div className={`md-body ${className || ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p style={{ margin: "0 0 0.5em" }}>{renderCites(children, badge)}</p>,
          li: ({ children }) => <li style={{ margin: "0.15em 0" }}>{renderCites(children, badge)}</li>,
          ul: ({ children }) => <ul style={{ paddingLeft: "1.25em", margin: "0.25em 0 0.5em", listStyle: "disc" }}>{children}</ul>,
          ol: ({ children }) => <ol style={{ paddingLeft: "1.25em", margin: "0.25em 0 0.5em", listStyle: "decimal" }}>{children}</ol>,
          strong: ({ children }) => <strong style={{ fontWeight: 600 }}>{children}</strong>,
          h1: ({ children }) => <p style={{ fontWeight: 600, margin: "0.4em 0 0.3em" }}>{children}</p>,
          h2: ({ children }) => <p style={{ fontWeight: 600, margin: "0.4em 0 0.3em" }}>{children}</p>,
          h3: ({ children }) => <p style={{ fontWeight: 600, margin: "0.4em 0 0.3em" }}>{children}</p>,
          table: ({ children }) => (
            <div style={{ overflowX: "auto", margin: "0.5em 0" }}>
              <table style={{ borderCollapse: "collapse", fontSize: "0.92em" }}>{children}</table>
            </div>
          ),
          th: ({ children }) => <th style={{ border: "1px solid rgba(128,128,128,0.35)", padding: "4px 8px", textAlign: "left" }}>{children}</th>,
          td: ({ children }) => <td style={{ border: "1px solid rgba(128,128,128,0.35)", padding: "4px 8px", verticalAlign: "top" }}>{renderCites(children, badge)}</td>,
          // Fenced ```chart blocks render as a chart instead of the <pre> box; every
          // other fenced/inline code block keeps its previous rendering unchanged.
          pre: ({ children }) => {
            const child = Array.isArray(children) ? children[0] : children;
            if (isValidElement(child) && isChartCode((child.props as { className?: string }).className)) {
              // ChartBlock renders its own <svg>/<div>; a <pre> wrapper would force
              // monospace/white-space:pre onto it, so skip the wrapper entirely.
              return <>{children}</>;
            }
            return <pre>{children}</pre>;
          },
          code: ({ className, children }) => {
            if (isChartCode(className)) {
              const text = Array.isArray(children) ? children.join("") : String(children ?? "");
              return <ChartBlock source={text} />;
            }
            return (
              <code style={{ fontSize: "0.9em", padding: "0 4px", borderRadius: 4, background: "rgba(128,128,128,0.15)" }}>{children}</code>
            );
          },
          a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer nofollow" style={{ textDecoration: "underline" }}>{children}</a>,
          // Images are never loaded: an injected ![](http://attacker/...) would otherwise act as a tracking beacon.
          img: ({ alt }) => <span style={{ opacity: 0.7 }}>{alt ? `[hình ảnh: ${alt}]` : "[hình ảnh đã bỏ]"}</span>,
        }}
      >
        {withMarkers}
      </ReactMarkdown>
    </div>
  );
}

/** True when a `code` element's className marks it as a fenced ```chart block. */
function isChartCode(className: unknown): boolean {
  return typeof className === "string" && className.split(/\s+/).includes("language-chart");
}

/** Replace ⟦n⟧ markers inside rendered text nodes with citation badges. */
function renderCites(children: React.ReactNode, badge: string): React.ReactNode {
  const walk = (node: React.ReactNode): React.ReactNode => {
    if (typeof node === "string") {
      if (!node.includes("⟦")) return node;
      const parts = node.split(/(⟦\d+⟧)/g);
      return parts.map((part, i) => {
        const m = part.match(/^⟦(\d+)⟧$/);
        if (!m) return part;
        return (
          <span key={i} title={`Nguồn [#${m[1]}]`}
            style={{
              display: "inline-block", fontSize: "0.72em", fontWeight: 700, lineHeight: 1.2,
              padding: "1px 5px", margin: "0 1px", borderRadius: 6, verticalAlign: "baseline",
              color: badge, border: `1px solid ${badge}`, opacity: 0.85,
            }}>
            #{m[1]}
          </span>
        );
      });
    }
    if (Array.isArray(node)) return node.map((n, i) => <span key={i}>{walk(n)}</span>);
    return node;
  };
  return walk(children);
}
