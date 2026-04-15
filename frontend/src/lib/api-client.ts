import { ApiResponse } from '../types/unified';

// Set API base to relative path to use Next.js proxy and eliminate CORS
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL === "http://localhost:8000" ? "/api" : (process.env.NEXT_PUBLIC_API_URL || '/api');

class ApiClient {
  private getUrl(path: string): string {
    if (path.startsWith('/api')) return path;
    const slash = path.startsWith('/') ? '' : '/';
    return `${API_BASE_URL}${slash}${path}`;
  }
  private getHeaders(): HeadersInit {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    // 瀏覽器環境下從 localStorage 獲取 Bearer Token
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('access_token');
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    }

    return headers;
  }

  async get<T>(path: string): Promise<T> {
    try {
      const response = await fetch(this.getUrl(path), {
        method: 'GET',
        headers: this.getHeaders(),
      });

      if (response.status === 401) {
        const refreshed = await this.refreshToken();
        if (refreshed) {
          return this.get<T>(path); // Retry
        }
        this.handleUnauthorized();
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Request failed with status ${response.status}`);
      }

      const result: ApiResponse<T> = await response.json();
      return result.data;
    } catch (e) {
      console.error(`ApiClient GET Error: ${path}`, e);
      throw e;
    }
  }

  async post<T>(path: string, body: any): Promise<T> {
    try {
      const response = await fetch(this.getUrl(path), {
        method: 'POST',
        headers: this.getHeaders(),
        body: JSON.stringify(body),
      });

      if (response.status === 401) {
        const refreshed = await this.refreshToken();
        if (refreshed) {
          return this.post<T>(path, body); // Retry
        }
        this.handleUnauthorized();
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Request failed with status ${response.status}`);
      }

      const result: ApiResponse<T> = await response.json();
      return result.data;
    } catch (e) {
      console.error(`ApiClient POST Error: ${path}`, e);
      throw e;
    }
  }

  private async refreshToken(): Promise<boolean> {
    if (typeof window === 'undefined') return false;
    
    const refresh = localStorage.getItem('refresh_token');
    if (!refresh) return false;

    try {
      // Use v1 auth endpoint directly to avoid legacy router 404s
      const response = await fetch(`/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
        credentials: 'omit', // V1 api expects it in body, but Next proxy forwards it
      });

      if (response.ok) {
        const data = await response.json();
        if (data.access_token) {
          localStorage.setItem('access_token', data.access_token);
          return true;
        }
      }
    } catch (e) {
      console.error('Token refresh failed', e);
    }
    return false;
  }

  /**
   * 專供 AI Chat Stream 使用的 EventSource 封裝
   */
  subscribeToStream(path: string, body: any, onMessage: (data: any) => void, onError: (err: any) => void) {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    
    // 注意：標準 EventSource 不支援 POST 與自定義 Header
    // 這裡我們使用 fetch 來模擬 SSE 處理
    fetch(this.getUrl(path), {
      method: 'POST',
      headers: {
        ...this.getHeaders(),
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
        const lines = chunk.split('\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            if (dataStr === '[DONE]') {
              return;
            }
            try {
              const data = JSON.parse(dataStr);
              onMessage(data);
            } catch (e) {
              console.warn('Failed to parse SSE line', e);
            }
          }
        }
      }
    })
    .catch(onError);
  }

  private handleUnauthorized() {
    console.warn('API Unauthorized (401). Redirecting to login or refreshing token...');
    if (typeof window !== 'undefined') {
      // 可以在這裡觸發跳轉登入頁面
      // window.location.href = '/auth/login';
    }
  }
}

export const apiClient = new ApiClient();
