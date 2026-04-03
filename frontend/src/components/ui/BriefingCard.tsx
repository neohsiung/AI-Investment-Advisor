import React from "react";

interface BriefingCardProps {
  title: string;
  tags?: string[];
  children: React.ReactNode;
  className?: string;
}

export default function BriefingCard({ 
  title, 
  tags, 
  children, 
  className = "" 
}: BriefingCardProps) {
  return (
    <div className={`bg-surface-container-low rounded-xl shadow-sm border border-outline-variant/10 overflow-hidden flex flex-col ${className}`}>
      <div className="p-6 border-b border-outline-variant/10 flex justify-between items-center">
        <h3 className="text-lg font-bold font-headline text-on-surface tracking-tight">
          {title}
        </h3>
        {tags && (
          <div className="flex gap-2">
            {tags.map((tag) => (
              <span key={tag} className="px-2 py-0.5 bg-secondary-container/20 text-secondary text-[10px] font-bold uppercase tracking-wider rounded">
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>
      
      <div className="p-6 flex-1">
        {children}
      </div>
    </div>
  );
}
