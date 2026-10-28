import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const socketMock = vi.fn();
vi.mock("@/hooks/useDashboard", () => ({ useDashboardSocket: () => socketMock() }));
vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "owner" }, isLoading: false }),
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
vi.mock("@/context/SidebarContext", () => ({
  useSidebar: () => ({ isOpen: false, toggle: vi.fn(), close: vi.fn() }),
}));
vi.mock("@/components/ui/ThemeToggle", () => ({ default: () => null }));

import TopBar from "./TopBar";

beforeEach(() => socketMock.mockReset());

describe("TopBar connection indicator", () => {
  it("does not say Live when connected but no data has arrived", () => {
    socketMock.mockReturnValue({ status: "CONNECTED", stableStatus: "LIVE", hasLiveData: false });
    render(<TopBar />);

    expect(screen.queryByText(/^live$/i)).not.toBeInTheDocument();
  });

  it("does not say Live when the socket is down", () => {
    socketMock.mockReturnValue({ status: "DISCONNECTED", stableStatus: "POLLING", hasLiveData: false });
    render(<TopBar />);

    expect(screen.queryByText(/^live$/i)).not.toBeInTheDocument();
  });

  it("says Live only when connected and data has arrived", () => {
    socketMock.mockReturnValue({ status: "CONNECTED", stableStatus: "LIVE", hasLiveData: true });
    render(<TopBar />);

    expect(screen.getByText(/^live$/i)).toBeInTheDocument();
  });
});
