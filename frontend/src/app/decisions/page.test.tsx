import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DecisionsPage from "./page";

// This page is the audit trail for the council debate behind a trade. What
// matters is that every turn is shown and that a risk challenge is
// distinguishable from a plain stance — a rendering bug that drops or
// mislabels the challenge turn makes a contested decision look unanimous.
// 本頁是交易背後議會辯論的稽核紀錄；漏掉或標錯「風險挑戰」回合，
// 會讓一個有爭議的決策看起來像全體一致。
const useSWRMock = vi.fn();
vi.mock("swr", () => ({
  default: (key: string | null, ...rest: unknown[]) => useSWRMock(key, ...rest),
}));

const SESSION = {
  id: "s-1",
  session_id: "sess-1",
  topic: "NVDA 加碼評估",
  consensus_preview: "維持持有，暫不加碼",
  created_at: "2026-08-13T10:00:00Z",
};

const DETAIL = {
  ...SESSION,
  consensus: "維持持有，暫不加碼",
  transcript: "",
  transcript_entries: [
    "[Fundamental]: 毛利率連兩季走高",
    "[Risk Challenge]: 集中度已達 26%，超過上限",
    "[Momentum]: 高於 20MA 4.1%",
  ],
};

function mockSWR({ sessions = [SESSION], detail = null as typeof DETAIL | null, isLoading = false } = {}) {
  useSWRMock.mockImplementation((key: string | null) => {
    if (key === null) return { data: undefined, isLoading: false };
    if (key.includes("/sessions?")) return { data: { sessions }, isLoading: false };
    return { data: detail ? { session: detail } : undefined, isLoading };
  });
}

beforeEach(() => {
  useSWRMock.mockReset();
});

describe("DecisionsPage", () => {
  it("lists recent sessions with their topic and preview", () => {
    mockSWR();
    render(<DecisionsPage />);

    expect(screen.getByText("NVDA 加碼評估")).toBeInTheDocument();
    expect(screen.getByText("維持持有，暫不加碼")).toBeInTheDocument();
  });

  it("says so explicitly when there are no sessions, rather than rendering blank", () => {
    mockSWR({ sessions: [] });
    render(<DecisionsPage />);

    expect(screen.getByText("尚無議會紀錄")).toBeInTheDocument();
  });

  it("prompts for a selection before any session is chosen", () => {
    mockSWR();
    render(<DecisionsPage />);

    expect(screen.getByText(/選擇左側議程/)).toBeInTheDocument();
  });

  it("requests the detail for the session that was clicked", async () => {
    mockSWR();
    render(<DecisionsPage />);

    await userEvent.click(screen.getByText("NVDA 加碼評估"));

    const keys = useSWRMock.mock.calls.map((c) => c[0]);
    expect(keys).toContain("/api/v1/council/sessions/s-1");
  });

  it("renders every transcript entry, not a truncated subset", async () => {
    mockSWR({ detail: DETAIL });
    render(<DecisionsPage />);
    await userEvent.click(screen.getByText("NVDA 加碼評估"));

    expect(screen.getByText("毛利率連兩季走高")).toBeInTheDocument();
    expect(screen.getByText("集中度已達 26%，超過上限")).toBeInTheDocument();
    expect(screen.getByText("高於 20MA 4.1%")).toBeInTheDocument();
    expect(screen.getByText(/3 則發言/)).toBeInTheDocument();
  });

  it("marks a risk challenge differently from a stance", async () => {
    mockSWR({ detail: DETAIL });
    render(<DecisionsPage />);
    await userEvent.click(screen.getByText("NVDA 加碼評估"));

    const challenge = screen.getByText("集中度已達 26%，超過上限").closest("div");
    const stance = screen.getByText("毛利率連兩季走高").closest("div");

    expect(challenge?.className).toContain("amber");
    expect(stance?.className).not.toContain("amber");
  });

  it("shows the speaker for each entry", async () => {
    mockSWR({ detail: DETAIL });
    render(<DecisionsPage />);
    await userEvent.click(screen.getByText("NVDA 加碼評估"));

    expect(screen.getByText(/Fundamental/)).toBeInTheDocument();
    expect(screen.getByText(/Risk Challenge/)).toBeInTheDocument();
  });

  it("falls back to showing the raw line when an entry has no [speaker] prefix", async () => {
    // Malformed input must still be displayed. Silently dropping a turn is the
    // one outcome an audit trail cannot have.
    mockSWR({ detail: { ...DETAIL, transcript_entries: ["no prefix at all"] } });
    render(<DecisionsPage />);
    await userEvent.click(screen.getByText("NVDA 加碼評估"));

    expect(screen.getByText("no prefix at all")).toBeInTheDocument();
  });

  it("shows a loading state while the detail is in flight", async () => {
    mockSWR({ detail: null, isLoading: true });
    render(<DecisionsPage />);
    await userEvent.click(screen.getByText("NVDA 加碼評估"));

    expect(screen.getByText("載入中...")).toBeInTheDocument();
  });
});
