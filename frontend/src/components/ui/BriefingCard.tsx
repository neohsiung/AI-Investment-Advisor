import React from "react";

interface BriefingCardProps {
  title: string;
  tags?: string[];
  children?: React.ReactNode;
  className?: string;
}

export default function BriefingCard({
  title,
  tags,
  children,
  className = "",
}: BriefingCardProps) {
  return (
    <div
      className={`bg-surface-container-low rounded-xl shadow-lg border border-outline-variant/10 overflow-hidden flex flex-col transition-all hover:shadow-xl ${className}`}
    >
      {/* Header */}
      <div className="p-6 border-b border-outline-variant/10 flex justify-between items-start bg-surface-container">
        <div className="flex flex-col gap-2">
          <h3 className="text-lg font-black font-headline text-on-surface tracking-tighter uppercase">
            {title}
          </h3>
          {tags && tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {tags.map((tag) => (
                <span
                  key={tag}
                  className="text-[10px] font-mono text-secondary bg-secondary/10 px-1.5 py-0.5 rounded uppercase tracking-widest font-black"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
          <span className="material-symbols-outlined text-sm text-primary animate-pulse">
            analytics
          </span>
        </div>
      </div>

      {/* Body */}
      <div className="p-6 flex-1">{children}</div>
    </div>
  );
}
