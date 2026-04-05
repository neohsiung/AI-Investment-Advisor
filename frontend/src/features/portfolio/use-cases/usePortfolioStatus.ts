import useSWR from 'swr';
import { PortfolioRepository } from '../infra/PortfolioRepository';
import { IPortfolioSummary } from '../domain/types';

// v3.4: Use Case Hook that abstracts away SWR and Repository
export function usePortfolioStatus() {
  const { data, error, isLoading, mutate } = useSWR<IPortfolioSummary>(
    'portfolio-summary', 
    PortfolioRepository.getSummary, 
    { 
      refreshInterval: 600000, // 10 minutes polling
      revalidateOnFocus: false,
    }
  );

  const rebalance = async () => {
    await PortfolioRepository.rebalance();
    mutate(); // Refresh the summary
  };

  const generateReport = async () => {
    await PortfolioRepository.generateReport();
  };

  return {
    summary: data,
    isLoading,
    isError: !!error,
    rebalance,
    generateReport,
    refresh: mutate,
  };
}
