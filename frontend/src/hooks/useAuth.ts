import useSWR from "swr";
import api, { fetcher } from "@/lib/api";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export function useAuth() {
  const router = useRouter();
  
  const { data, error, mutate, isLoading } = useSWR("/api/auth/me", fetcher, {
    shouldRetryOnError: false,
    revalidateOnFocus: false,
  });

  const isAuthenticated = !!data?.data?.is_authenticated;
  const user = data?.data;

  const logout = async () => {
    try {
      await api.post("/api/auth/logout");
      mutate(undefined, false);
      router.push("/auth/login");
    } catch (e) {
      console.error("Logout failed", e);
    }
  };

  return {
    user,
    isAuthenticated,
    isLoading,
    error,
    logout,
    mutate,
  };
}

/**
 * 中間件：強制防護頁面
 */
export function useRequireAuth() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/auth/login");
    }
  }, [isLoading, isAuthenticated, router]);

  return { isAuthenticated, isLoading };
}
