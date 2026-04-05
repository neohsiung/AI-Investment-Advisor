"use client";

import React from "react";
import { useTheme } from "@/context/ThemeContext";

export default function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  const toggleTheme = () => {
    setTheme(isDark ? "light" : "dark");
  };

  return (
    <button 
      onClick={toggleTheme}
      className={`p-2 rounded-full transition-all active:scale-95 group focus:outline-none ${
        isDark ? "bg-surface-container-highest text-primary" : "bg-secondary-container/20 text-secondary"
      }`}
      aria-label="Toggle Theme"
    >
      <span className="material-symbols-outlined text-lg">
        {isDark ? "light_mode" : "dark_mode"}
      </span>
    </button>
  );
}
