import { ApiResponse } from '../types/unified';
import api from './api';

/**
 * Ergonomic wrapper over the shared axios transport (`lib/api.ts`).
 *
 * Kept as a separate export because its callers expect the response envelope to
 * be unwrapped — `get<T>()` returns `T`, not an AxiosResponse. Collapsing it
 * into the axios instance would have silently changed that contract at every
 * call site.
 *
 * What changed: it used to be a second, independent HTTP stack (raw `fetch`)
 * with its OWN localStorage Bearer token, its OWN refresh-on-401 retry and its
 * OWN unauthorized handler — a duplicate auth policy that could drift from the
 * axios one. Transport and auth policy now live in exactly one place; only the
 * response-unwrapping ergonomics remain here.
 *
 * 此類別保留「自動解開 ApiResponse」的介面，但底層改用共用的 axios 實例；
 * 原本各自實作的 token/refresh 邏輯已刪除，驗證政策只剩一處。
 */
class ApiClient {
  private getUrl(path: string): string {
    if (path.startsWith('/api')) return path;
    const slash = path.startsWith('/') ? '' : '/';
    return `/api${slash}${path}`;
  }

  async get<T>(path: string): Promise<T> {
    try {
      const res = await api.get<ApiResponse<T>>(this.getUrl(path));
      return res.data.data;
    } catch (e) {
      console.error(`ApiClient GET Error: ${path}`, e);
      throw e;
    }
  }

  async post<T>(path: string, body: any): Promise<T> {
    try {
      const res = await api.post<ApiResponse<T>>(this.getUrl(path), body);
      return res.data.data;
    } catch (e) {
      console.error(`ApiClient POST Error: ${path}`, e);
      throw e;
    }
  }

  /**
   * SSE wrapper for the AI chat stream.
   *
   * Still uses `fetch` rather than axios: the browser XHR adapter buffers the
   * whole response, so it cannot yield partial chunks. This is a streaming
   * transport concern, not a second auth stack — it carries no credentials of
   * its own and relies on the same cookie/proxy path as everything else.
   * 串流仍用 fetch（XHR 無法逐塊讀取），但不再自帶任何憑證。
   */
  subscribeToStream(path: string, body: any, onMessage: (data: any) => void, onError: (err: any) => void) {
    fetch(this.getUrl(path), {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify(body),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error('Stream request failed');
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        if (!reader) return;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          for (const line of chunk.split('\n')) {
            if (!line.startsWith('data: ')) continue;
            const dataStr = line.slice(6);
            if (dataStr === '[DONE]') return;
            try {
              onMessage(JSON.parse(dataStr));
            } catch (e) {
              console.warn('Failed to parse SSE line', e);
            }
          }
        }
      })
      .catch(onError);
  }
}

export const apiClient = new ApiClient();
