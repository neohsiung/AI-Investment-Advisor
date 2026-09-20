"use client";

import React from "react";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Renders the topological layers as columns.
 *
 * These layers are NOT declared in the workflow file — the executor derives them
 * from each node's input/output keys. Showing them is the point: it is how an
 * operator sees that three scouts will actually run concurrently, or that a step
 * they expected to be parallel has accidentally become sequential because it
 * consumes another node's output.
 *
 * 這些層級並非寫在 workflow 檔中，而是由 executor 依輸入輸出鍵推導。
 * 呈現它才能讓使用者看出哪些步驟真的會併行，或某步驟是否因為讀取了
 * 其他節點的輸出而意外變成循序。
 */
export function LayerGraph({ layers }: { layers: string[][] }) {
  if (!layers.length) return null;

  return (
    <div className="flex items-start gap-2 overflow-x-auto pb-2">
      {layers.map((layer, i) => (
        <React.Fragment key={i}>
          <div className="min-w-[150px] shrink-0">
            <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
              Layer {i + 1}
              {layer.length > 1 && (
                <span className="ml-1 text-primary">· {layer.length} parallel</span>
              )}
            </div>
            <div className="space-y-1">
              {layer.map((name) => (
                <div
                  key={name}
                  className={cn(
                    "rounded border border-outline-variant/30 bg-surface-container",
                    "px-2 py-1.5 font-mono text-[11px] text-on-surface",
                  )}
                >
                  {name}
                </div>
              ))}
            </div>
          </div>
          {i < layers.length - 1 && (
            <ArrowRight className="mt-6 h-4 w-4 shrink-0 text-on-surface-variant/40" />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}
