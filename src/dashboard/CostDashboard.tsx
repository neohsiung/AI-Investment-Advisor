
// src/dashboard/CostDashboard.tsx
"""成本儀表板前端組件"""

import React, { useEffect, useState } from 'react';
import {
  LineChart, BarChart, PieChart, Line, Bar, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import { Card, Row, Col, Statistic, Tag, Alert } from 'antd';
import { DollarOutlined, AlertOutlined, CheckOutlined } from '@ant-design/icons';

interface BudgetStatus {
  weekly: {
    budget_usd: number;
    spent_usd: number;
    remaining_usd: number;
    used_pct: number;
    status: 'ok' | 'warning' | 'alert' | 'critical';
  };
  monthly: {
    budget_usd: number;
    spent_usd: number;
    remaining_usd: number;
    used_pct: number;
    status: 'ok' | 'warning' | 'alert' | 'critical';
  };
}

export const CostDashboard: React.FC = () => {
  const [budgetStatus, setBudgetStatus] = useState<BudgetStatus | null>(null);
  const [costByTier, setCostByTier] = useState([]);
  const [costByProvider, setCostByProvider] = useState([]);
  const [trending, setTrending] = useState([]);
  const [modelPerf, setModelPerf] = useState([]);

  useEffect(() => {
    const userId = getUserId(); // 獲取當前用戶 ID
    
    Promise.all([
      fetch(\`/api/v1/costs/budget-status?user_id=\${userId}\`).then(r => r.json()),
      fetch(\`/api/v1/costs/by-tier?user_id=\${userId}&period=week\`).then(r => r.json()),
      fetch(\`/api/v1/costs/by-provider?user_id=\${userId}&period=week\`).then(r => r.json()),
      fetch(\`/api/v1/costs/trending?user_id=\${userId}&days=30\`).then(r => r.json()),
      fetch(\`/api/v1/costs/model-performance?user_id=\${userId}\`).then(r => r.json())
    ]).then(([budget, tier, provider, trend, perf]) => {
      setBudgetStatus(budget);
      setCostByTier(tier.breakdown);
      setCostByProvider(provider.breakdown);
      setTrending(trend.data);
      setModelPerf(perf.models);
    });
  }, []);

  const getStatusColor = (status: string) => {
    const colorMap = {
      'ok': 'success',
      'warning': 'warning',
      'alert': 'error',
      'critical': 'error'
    };
    return colorMap[status] || 'default';
  };

  const statusEmoji = {
    'ok': '✅',
    'warning': '⚠️',
    'alert': '🚨',
    'critical': '🆘'
  };

  if (!budgetStatus) return <div>Loading...</div>;

  return (
    <div style={{ padding: '24px', backgroundColor: '#f5f5f5' }}>
      <h1>💰 成本儀表板</h1>

      {/* 預算概覽 */}
      <Card title="預算狀態" style={{ marginBottom: '24px' }}>
        <Row gutter={16}>
          <Col xs={24} sm={12}>
            <Card>
              <h3>本週預算</h3>
              <Statistic
                title="已使用"
                value={budgetStatus.weekly.used_pct}
                suffix="%"
                prefix={statusEmoji[budgetStatus.weekly.status]}
                valueStyle={{ color: budgetStatus.weekly.used_pct > 85 ? '#ff4d4f' : '#52c41a' }}
              />
              <p>${budgetStatus.weekly.spent_usd.toFixed(2)} / ${budgetStatus.weekly.budget_usd.toFixed(2)}</p>
              <p>還剩 ${budgetStatus.weekly.remaining_usd.toFixed(2)}</p>
              <Tag color={getStatusColor(budgetStatus.weekly.status)}>
                {budgetStatus.weekly.status.toUpperCase()}
              </Tag>
            </Card>
          </Col>
          <Col xs={24} sm={12}>
            <Card>
              <h3>本月預算</h3>
              <Statistic
                title="已使用"
                value={budgetStatus.monthly.used_pct}
                suffix="%"
                valueStyle={{ color: budgetStatus.monthly.used_pct > 85 ? '#ff4d4f' : '#52c41a' }}
              />
              <p>${budgetStatus.monthly.spent_usd.toFixed(2)} / ${budgetStatus.monthly.budget_usd.toFixed(2)}</p>
              <p>還剩 ${budgetStatus.monthly.remaining_usd.toFixed(2)}</p>
            </Card>
          </Col>
        </Row>
      </Card>

      {/* 成本分佈圖表 */}
      <Row gutter={16} style={{ marginBottom: '24px' }}>
        <Col xs={24} md={12}>
          <Card title="按層級分佈">
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie data={costByTier} dataKey="cost_usd" label nameKey="tier">
                  {costByTier.map((entry, index) => (
                    <Cell key={\`cell-\${index}\`} fill={['#8884d8', '#82ca9d', '#ffc658', '#ff7c7c'][index]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => \`$\${value.toFixed(2)}\`} />
              </PieChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="按提供商分佈">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={costByProvider}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="provider" />
                <YAxis />
                <Tooltip formatter={(value) => \`$\${value.toFixed(2)}\`} />
                <Bar dataKey="cost_usd" fill="#8884d8" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      {/* 成本趨勢 */}
      <Card title="30天成本趨勢" style={{ marginBottom: '24px' }}>
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={trending}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis yAxisId="left" label={{ value: '成本 ($)', angle: -90, position: 'insideLeft' }} />
            <YAxis yAxisId="right" orientation="right" label={{ value: '請求數', angle: 90, position: 'insideRight' }} />
            <Tooltip formatter={(value) => value.toFixed(2)} />
            <Legend />
            <Line yAxisId="left" type="monotone" dataKey="cost_usd" stroke="#8884d8" name="日成本" />
            <Line yAxisId="right" type="monotone" dataKey="request_count" stroke="#82ca9d" name="請求數" />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      {/* 模型性能對比 */}
      <Card title="模型性能對比">
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: '#f0f0f0' }}>
                <th style={{ padding: '8px', textAlign: 'left', borderBottom: '1px solid #ddd' }}>模型</th>
                <th style={{ padding: '8px', textAlign: 'center', borderBottom: '1px solid #ddd' }}>使用次數</th>
                <th style={{ padding: '8px', textAlign: 'center', borderBottom: '1px solid #ddd' }}>質量</th>
                <th style={{ padding: '8px', textAlign: 'center', borderBottom: '1px solid #ddd' }}>成功率</th>
                <th style={{ padding: '8px', textAlign: 'center', borderBottom: '1px solid #ddd' }}>延遲 (ms)</th>
                <th style={{ padding: '8px', textAlign: 'center', borderBottom: '1px solid #ddd' }}>成本/次</th>
              </tr>
            </thead>
            <tbody>
              {modelPerf.map((model, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: '8px' }}>{model.provider}/{model.model}</td>
                  <td style={{ padding: '8px', textAlign: 'center' }}>{model.usage_count}</td>
                  <td style={{ padding: '8px', textAlign: 'center' }}>{model.avg_quality.toFixed(1)}/10</td>
                  <td style={{ padding: '8px', textAlign: 'center' }}>{model.success_rate_pct.toFixed(1)}%</td>
                  <td style={{ padding: '8px', textAlign: 'center' }}>{model.avg_latency_ms.toFixed(0)}</td>
                  <td style={{ padding: '8px', textAlign: 'center' }}>${model.avg_cost_per_request.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};
