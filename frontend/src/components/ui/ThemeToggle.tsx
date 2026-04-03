"use client";

import React, { useEffect, useState } from "react";

export default function ThemeToggle() {
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    // Check initial state
    const isDarkMode = document.documentElement.classList.contains("dark");
    setIsDark(isDarkMode);
  }, []);

  const toggleTheme = () => {
    const newIsDark = !isDark;
    setIsDark(newIsDark);
    if (newIsDark) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
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
