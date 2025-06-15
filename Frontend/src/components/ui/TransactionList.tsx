import React from 'react';
import { motion } from 'framer-motion';
import { ArrowUpRight, ArrowDownLeft, RefreshCw } from 'lucide-react';
import { Badge } from './badge';

export type Transaction = {
  id: number; // Backend returns number
  type: 'sent' | 'received' | 'convert'; // Aligned with backend
  name: string; // Backend uses 'name' instead of 'title'
  amount: number;
  wallet_type?: string; // For sent/received (e.g., 'btc', 'eth', 'sol', 'inr')
  crypto_symbol?: string; // For convert (e.g., 'BTC', 'ETH', 'SOL')
  target_currency?: string; // For convert (e.g., 'INR')
  date: string; // Backend returns string in 'YYYY-MM-DD'
  status: 'completed' | 'pending' | 'failed';
};

type TransactionListProps = {
  transactions: Transaction[];
  showViewAll?: boolean;
};

const TransactionList: React.FC<TransactionListProps> = ({
  transactions,
  showViewAll = true,
}) => {
  // Derive currency from transaction data
  const getCurrency = (transaction: Transaction): string => {
    if (transaction.type === 'convert') {
      return transaction.target_currency || 'INR'; // Default to INR for conversions
    }
    return transaction.wallet_type?.toUpperCase() || 'UNKNOWN'; // e.g., BTC, ETH, SOL, INR
  };

  // Convert string date to Date object and format
  const formatDate = (dateStr: string): string => {
    try {
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) {
        return 'Invalid Date';
      }
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return 'Invalid Date';
    }
  };

  const getIcon = (type: Transaction['type']) => {
    switch (type) {
      case 'sent':
        return <ArrowUpRight className="text-red-500" aria-hidden="true" />;
      case 'received':
        return <ArrowDownLeft className="text-green-500" aria-hidden="true" />;
      case 'convert':
        return <RefreshCw className="text-blue-500" aria-hidden="true" />;
      default:
        return null;
    }
  };

  const getStatusColor = (status: Transaction['status']) => {
    switch (status) {
      case 'completed':
        return 'bg-green-900/30 text-green-500 border-0';
      case 'pending':
        return 'bg-yellow-600/20 text-yellow-500 border-0';
      case 'failed':
        return 'bg-red-900/20 text-red-500 border-0'; // Standard Tailwind classes
    }
  };

  return (
    <div className="bg-[#1a2235] rounded-lg p-6 space-y-6">
      <div className="glass-card p-5 w-full">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-base font-semibold text-white">Recent Transactions</h3>
          {showViewAll && (
            <motion.button
              className="text-sm text-white flex items-center space-x-1"
              whileHover={{ x: 3 }}
              aria-label="View all transactions"
            >
              <span>View All</span>
              <ArrowRight size={14} aria-hidden="true" />
            </motion.button>
          )}
        </div>

        <div className="space-y-3">
          {transactions.length === 0 ? (
            <div className="text-center py-6 text-gray-400">
              No transactions yet
            </div>
          ) : (
            transactions.map((transaction, index) => (
              <motion.div
                key={transaction.id}
                className="flex items-center justify-between p-3 rounded-xl bg-[#2a3348]/60 hover:bg-[#2a3348]/80 transition-colors"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: index * 0.05 }}
                whileHover={{ x: 3 }}
                role="listitem"
              >
                <div className="flex items-center space-x-3">
                  <div className="p-2 rounded-full bg-slate-800">
                    {getIcon(transaction.type) || <span>?</span>}
                  </div>
                  <div>
                    <div className="text-sm font-medium text-white">
                      {transaction.name || 'Unknown'}
                    </div>
                    <div className="text-xs text-gray-400">
                      {formatDate(transaction.date)}
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <div
                    className={`text-sm font-medium ${
                      transaction.type === 'sent'
                        ? 'text-red-500'
                        : transaction.type === 'received' || transaction.type === 'convert'
                        ? 'text-green-500'
                        : 'text-gray-400'
                    }`}
                  >
                    {transaction.type === 'sent' ? '-' : transaction.type === 'received' ? '+' : ''}
                    {getCurrency(transaction)}
                    {Math.abs(transaction.amount).toLocaleString('en-US', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </div>
                  <Badge
                    variant="outline"
                    className={`text-[10px] mt-1 ${getStatusColor(transaction.status)}`}
                  >
                    {transaction.status.charAt(0).toUpperCase() + transaction.status.slice(1)}
                  </Badge>
                </div>
              </motion.div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default TransactionList;