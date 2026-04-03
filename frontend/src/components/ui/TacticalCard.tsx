import React from "react";

interface TacticalCardProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  accentColor?: string;
  className?: string;
}

export default function TacticalCard({ 
  title, 
  subtitle, 
  children, 
  accentColor = "var(--primary-container)", 
  className = "" 
}: TacticalCardProps) {
  return (
    <div className={`bg-surface-container rounded-lg p-6 relative overflow-hidden flex flex-col ${className}`}>
      <div 
        className="absolute top-0 left-0 w-1 h-full" 
        style={{ backgroundColor: accentColor }}
      />
      
      {(title || subtitle) && (
        <div className="mb-6 flex justify-between items-start">
          <div>
            <h3 className="font-label text-[10px] uppercase tracking-[0.2em] text-on-surface-variant mb-1">
              {title}
            </h3>
            {subtitle && (
              <p className="text-xl font-bold font-headline tracking-tighter text-on-surface">
                {subtitle}
              </p>
            )}
          </div>
        </div>
      )}
      
      <div className="flex-1">
        {children}
      </div>
    </div>
  );
}
