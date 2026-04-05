import useSWR from 'swr';
import { IntelligenceRepository } from '../infra/IntelligenceRepository';
import { IIntelligenceBriefing } from '../domain/types';

// v3.4: Hook that retrieves cached intelligence with automatic refresh
export function useIntelligenceStatus() {
  const { data, error, isLoading, mutate } = useSWR<IIntelligenceBriefing>(
    'market-intelligence', 
    IntelligenceRepository.getLatest, 
    { 
      refreshInterval: 600000, // 10 minutes
      revalidateOnFocus: true,
    }
  );

  return {
    briefing: data,
    isLoading,
    isError: !!error,
    refresh: mutate
  };
}
