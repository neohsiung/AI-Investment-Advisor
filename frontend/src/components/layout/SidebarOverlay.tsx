"use client";

import React from "react";
import { useSidebar } from "@/context/SidebarContext";

export default function SidebarOverlay() {
    const { isOpen, close } = useSidebar();

    if (!isOpen) return null;

    return (
        <div
            className="fixed inset-0 z-40 bg-black/50 lg:hidden"
            onClick={close}
            aria-hidden="true"
        />
    );
}
