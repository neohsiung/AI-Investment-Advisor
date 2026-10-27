import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "owner" }, isLoading: false }),
}));

import { WebSocketProvider, useWebSocket } from "./WebSocketContext";

class FakeSocket {
  static instances: FakeSocket[] = [];
  static OPEN = 1;
  readyState = 1;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  constructor() {
    FakeSocket.instances.push(this);
  }
  send() {}
  close() {}
}

function Probe() {
  const { lastMessage } = useWebSocket();
  return <div data-testid="last">{lastMessage ? "has-data" : "no-data"}</div>;
}

beforeEach(() => {
  FakeSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.useFakeTimers();
  vi.spyOn(console, "log").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("WebSocketProvider", () => {
  it("does not keep the old message after a reconnect, until new data arrives", async () => {
    render(
      <WebSocketProvider>
        <Probe />
      </WebSocketProvider>
    );
    const first = FakeSocket.instances[0];

    act(() => first.onopen!());
    act(() => first.onmessage!({ data: JSON.stringify({ type: "PORTFOLIO_UPDATE", payload: {} }) }));
    expect(screen.getByTestId("last")).toHaveTextContent("has-data");

    act(() => first.onclose!({ code: 1006 }));
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    const second = FakeSocket.instances[1];
    expect(second).toBeDefined();

    act(() => second.onopen!());
    expect(screen.getByTestId("last")).toHaveTextContent("no-data");

    act(() => second.onmessage!({ data: JSON.stringify({ type: "PORTFOLIO_UPDATE", payload: {} }) }));
    expect(screen.getByTestId("last")).toHaveTextContent("has-data");
  });
});
