import { useState, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowRight, Shield, Loader2 } from "lucide-react";
import stellarTrader, { TradeResult } from "@/lib/stellar-client";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

export function StellarTradeExecutor() {
  const [amount, setAmount] = useState("");
  const [fromCurrency, setFromCurrency] = useState("XLM");
  const [toCurrency, setToCurrency] = useState("XLM");
  const [destination, setDestination] = useState("");
  const [memo, setMemo] = useState("");
  const [showPaymentDialog, setShowPaymentDialog] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [stellarStatus, setStellarStatus] = useState<"disconnected" | "connected">("disconnected");
  const [balance, setBalance] = useState<{xlm: string, usd: string} | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastTrade, setLastTrade] = useState<TradeResult | null>(null);
  
  const currencies = [
    { value: "XLM", label: "Stellar (XLM)" },
    { value: "USD", label: "US Dollar (USD)" }
  ];
  
  // Connect to Stellar on component load
  useEffect(() => {
    const connectToStellar = async () => {
      setIsLoading(true);
      try {
        // In a real app, you would get the secret key from user input or secure storage
        const secretKey = localStorage.getItem('stellar_secret_key');
        
        if (!secretKey) {
          toast.warning("Please set your Stellar secret key in the wallet settings");
          return;
        }
        
        const connected = await stellarTrader.connect(secretKey);
        if (connected) {
          setStellarStatus("connected");
          // Load account balance
          const accountBalance = await stellarTrader.getAccountBalance(secretKey);
          setBalance(accountBalance);
          toast.success("Connected to Stellar network");
        }
      } catch (error) {
        console.error("Failed to connect to Stellar network:", error);
        toast.error(`Connection failed: ${error.message}`);
      } finally {
        setIsLoading(false);
      }
    };
    
    connectToStellar();
  }, []);
  
  const handleExecutePayment = async () => {
    if (!amount || isNaN(Number(amount)) || !destination) {
      toast.error("Please fill in all required fields");
      return;
    }
    
    setIsExecuting(true);
    
    try {
      // Execute payment using the Stellar SDK
      const result = await stellarTrader.executePayment(
        destination,
        amount,
        fromCurrency,
        memo
      );
      
      setLastTrade(result);
      toast.success("Payment executed successfully!");
      
      // Update balance after successful payment
      const secretKey = localStorage.getItem('stellar_secret_key');
      if (secretKey) {
        const accountBalance = await stellarTrader.getAccountBalance(secretKey);
        setBalance(accountBalance);
      }
      
      // Reset form
      setAmount("");
      setDestination("");
      setMemo("");
      setShowPaymentDialog(false);
    } catch (error) {
      console.error("Payment failed:", error);
      toast.error(`Payment failed: ${error.message}`);
    } finally {
      setIsExecuting(false);
    }
  };
  
  const handleOpenPaymentDialog = () => {
    if (!stellarTrader.isReady()) {
      toast.error("Please connect your wallet first");
      return;
    }
    setShowPaymentDialog(true);
  };

    return (
    <Card className="bg-slate-800/50 border-slate-700 backdrop-blur-sm">
      <div className="p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-xl font-bold text-white flex items-center">
              <Shield className="h-5 w-5 mr-2 text-emerald-400" />
              Stellar Payment Portal
            </h3>
            <p className="text-sm text-slate-400 mt-1">
              Send and receive payments on the Stellar network
            </p>
          </div>
          <div className="flex items-center space-x-3">
            {balance && (
              <div className="text-right">
                <div className="text-sm text-slate-400">Balance</div>
                <div className="font-medium text-white">
                  {parseFloat(balance.xlm).toFixed(2)} XLM
                </div>
              </div>
            )}
            <div>
              {stellarStatus === "connected" ? (
                <span className="px-3 py-1.5 text-xs rounded-full bg-emerald-500/20 text-emerald-400 flex items-center">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 mr-2"></span>
                  Connected
                </span>
              ) : (
                <span className="px-3 py-1.5 text-xs rounded-full bg-red-500/20 text-red-400 flex items-center">
                  <span className="w-2 h-2 rounded-full bg-red-400 mr-2"></span>
                  Disconnected
                </span>
              )}
            </div>
          </div>
        </div>
        
        {isLoading ? (
          <div className="flex justify-center items-center h-40">
            <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
          </div>
        ) : (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <label htmlFor="from-currency" className="text-sm text-slate-300">From</label>
                <Select 
                  value={fromCurrency} 
                  onValueChange={(value) => setFromCurrency(value)}
                >
                  <SelectTrigger className="bg-slate-700/50 border-slate-600 text-white">
                    <SelectValue placeholder="Select currency" />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-800 border-slate-700">
                    {currencies.map((currency) => (
                      <SelectItem 
                        key={currency.value} 
                        value={currency.value}
                        className="hover:bg-slate-700"
                      >
                        {currency.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              <div className="space-y-2">
                <label htmlFor="to-currency" className="text-sm text-slate-300">To</label>
                <Select 
                  value={toCurrency} 
                  onValueChange={(value) => setToCurrency(value)}
                >
                  <SelectTrigger className="bg-slate-700/50 border-slate-600 text-white">
                    <SelectValue placeholder="Select currency" />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-800 border-slate-700">
                    {currencies.map((currency) => (
                      <SelectItem 
                        key={currency.value} 
                        value={currency.value}
                        className="hover:bg-slate-700"
                      >
                        {currency.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              <div className="space-y-2">
                <label htmlFor="amount" className="text-sm text-slate-300">
                  Amount
                </label>
                <div className="relative">
                  <Input
                    id="amount"
                    type="number"
                    placeholder="0.00"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    className="bg-slate-700/50 border-slate-600 text-white pl-4 pr-16 py-6 text-lg"
                  />
                  <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none">
                    <span className="text-slate-400 text-sm">
                      {fromCurrency}
                    </span>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="space-y-4">
              <div className="space-y-2">
                <label htmlFor="destination" className="text-sm text-slate-300">
                  Destination Address
                </label>
                <Input
                  id="destination"
                  placeholder="Enter Stellar address (G...)"
                  value={destination}
                  onChange={(e) => setDestination(e.target.value)}
                  className="bg-slate-700/50 border-slate-600 text-white"
                />
              </div>
              
              <Button
                onClick={handleOpenPaymentDialog}
                disabled={isExecuting || !amount || !destination || parseFloat(amount) <= 0}
                className="w-full bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white py-6 text-base font-medium"
              >
                {isExecuting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    Send Payment
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </>
                )}
              </Button>
            </div>
            
            {lastTrade && (
              <div className="mt-4 p-4 bg-slate-700/30 rounded-lg border border-slate-700">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-medium text-slate-300">Last Transaction</h4>
                    <p className="text-xs text-slate-400">
                      {new Date(lastTrade.timestamp).toLocaleString()}
                    </p>
                  </div>
                  <span className="px-2 py-1 text-xs rounded-full bg-emerald-500/20 text-emerald-400">
                    Completed
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-slate-400">Amount</p>
                    <p className="text-sm font-medium text-white">
                      {lastTrade.amount} {lastTrade.fromAsset}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-400">Transaction Hash</p>
                    <a 
                      href={`https://stellar.expert/explorer/testnet/tx/${lastTrade.hash}`} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="text-sm font-medium text-sky-400 hover:underline truncate block"
                    >
                      {lastTrade.hash.substring(0, 12)}...{lastTrade.hash.slice(-8)}
                    </a>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
        
        {/* Payment Confirmation Dialog */}
        <Dialog open={showPaymentDialog} onOpenChange={setShowPaymentDialog}>
          <DialogContent className="bg-slate-800 border-slate-700 max-w-md">
            <DialogHeader>
              <DialogTitle className="text-white">Confirm Payment</DialogTitle>
              <DialogDescription className="text-slate-400">
                Review and confirm your transaction details
              </DialogDescription>
            </DialogHeader>
            
            <div className="space-y-4 py-4">
              <div className="bg-slate-700/30 p-4 rounded-lg">
                <div className="flex justify-between mb-2">
                  <span className="text-slate-400">Amount:</span>
                  <span className="font-medium text-white">
                    {amount} {fromCurrency}
                  </span>
                </div>
                <div className="flex justify-between mb-2">
                  <span className="text-slate-400">To:</span>
                  <span className="font-medium text-white text-right max-w-[200px] truncate">
                    {destination || 'Not specified'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Network Fee:</span>
                  <span className="text-slate-300">0.00001 XLM</span>
                </div>
              </div>
              
              <div className="space-y-2">
                <label htmlFor="memo" className="text-sm text-slate-300">
                  Memo (Optional)
                </label>
                <Input
                  id="memo"
                  placeholder="Add a note for this transaction"
                  value={memo}
                  onChange={(e) => setMemo(e.target.value)}
                  className="bg-slate-700/50 border-slate-600 text-white"
                />
              </div>
              
              <div className="flex justify-end space-x-3 pt-2">
                <Button 
                  variant="outline" 
                  onClick={() => setShowPaymentDialog(false)}
                  className="border-slate-600 text-white hover:bg-slate-700"
                  disabled={isExecuting}
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleExecutePayment}
                  disabled={isExecuting}
                  className="bg-emerald-500 hover:bg-emerald-600 text-white"
                >
                  {isExecuting ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Processing...
                    </>
                  ) : (
                    'Confirm Payment'
                  )}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </Card>
  );
}
