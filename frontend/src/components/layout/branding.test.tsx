import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/font/google", () => ({
  Inter: () => ({ variable: "inter" }),
  Space_Grotesk: () => ({ variable: "grotesk" }),
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
vi.mock("@/context/SidebarContext", () => ({
  useSidebar: () => ({ isOpen: false, toggle: vi.fn(), close: vi.fn() }),
  SidebarProvider: ({ children }: { children: React.ReactNode }) => children,
}));

import Sidebar from "./Sidebar";
import { metadata } from "@/app/layout";

describe("product name", () => {
  it("is AI Investment Advisor in the sidebar, without a version-and-status tag", () => {
    render(<Sidebar />);

    expect(screen.getByText("AI Investment Advisor")).toBeInTheDocument();
    expect(screen.queryByText(/quantum/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/V3\.2|^Active$/i)).not.toBeInTheDocument();
  });

  it("is AI Investment Advisor in the page title and home-screen title", () => {
    expect(String(metadata.title)).toContain("AI Investment Advisor");
    expect(String(metadata.title)).not.toMatch(/quantum/i);
    expect(metadata.appleWebApp).toMatchObject({ title: "AI Investment Advisor" });
  });
});
