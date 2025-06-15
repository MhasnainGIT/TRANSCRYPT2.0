import { Horizon, Keypair, TransactionBuilder, Operation, Asset, Networks, Memo } from 'stellar-sdk';
const { Server } = Horizon;

// Types for trade operations
export interface TradeOptions {
  assetCode: string;
  amount: number;
  action: 'buy' | 'sell';
}

export interface TradeResult {
  id: string;
  fromAsset: string;
  toAsset: string;
  amount: number;
  rate: number;
  timestamp: Date;
  hash: string;
  status: 'pending' | 'completed' | 'failed';
}

// StellarTrader class for Stellar network interactions
export class StellarTrader {
  public server: any; // Using any type to avoid type issues with Horizon.Server
  private keypair: Keypair | null = null;
  private networkPassphrase: string;
  
  constructor(network: 'testnet' | 'public' = 'testnet') {
    const serverUrl = network === 'testnet' 
      ? 'https://horizon-testnet.stellar.org' 
      : 'https://horizon.stellar.org';
    
    this.server = new (Server as any)(serverUrl);
    this.networkPassphrase = network === 'testnet' 
      ? Networks.TESTNET 
      : Networks.PUBLIC;
  }
  
  // Check if trader is properly connected
  isReady(): boolean {
    return this.keypair !== null;
  }
  
  // Connect with a secret key
  async connect(secretKey: string): Promise<boolean> {
    try {
      this.keypair = Keypair.fromSecret(secretKey);
      return true;
    } catch (error) {
      console.error('Failed to connect with secret key:', error);
      return false;
    }
  }

  // Execute a payment on the Stellar network
  async executePayment(
    destination: string, 
    amount: string, 
    assetCode: string = 'XLM',
    memo: string = ''
  ): Promise<TradeResult> {
    if (!this.keypair) {
      throw new Error('Not connected. Call connect() with a valid secret key first.');
    }

    try {
      // Load the source account to get the current sequence number
      const sourceAccount = await this.server.loadAccount(this.keypair.publicKey());
      
      // Create transaction builder
      const transaction = new TransactionBuilder(sourceAccount, {
        fee: '100', // Base fee (in stroops)
        networkPassphrase: this.networkPassphrase
      });

      // Add payment operation
      transaction.addOperation(
        Operation.payment({
          destination: destination,
          asset: assetCode === 'XLM' ? Asset.native() : new Asset(assetCode, this.keypair.publicKey()),
          amount: amount.toString(),
          source: this.keypair.publicKey()
        })
      );

      // Add memo if provided
      if (memo) {
        transaction.addMemo(Memo.text(memo));
      }

      // Set timeout and build the transaction
      transaction.setTimeout(30);
      const builtTransaction = transaction.build();

      // Sign the transaction
      builtTransaction.sign(this.keypair);

      // Submit the transaction to the network
      const result = await this.server.submitTransaction(builtTransaction);
      
      return {
        id: result.hash,
        fromAsset: assetCode,
        toAsset: 'XLM',
        amount: parseFloat(amount),
        rate: 1, // You can implement actual rate fetching if needed
        timestamp: new Date(),
        hash: result.hash,
        status: 'completed'
      };
    } catch (error: any) {
      console.error('Transaction failed:', error);
      if (error.response && error.response.data) {
        console.error('Error details:', error.response.data);
      }
      throw new Error(`Payment failed: ${error?.message || 'Unknown error'}`);
    }
  }

  // Get account balance
  async getAccountBalance(publicKey: string): Promise<{ xlm: string, usd: string }> {
    try {
      const account = await this.server.loadAccount(publicKey);
      const xlmBalance = account.balances.find((b: any) => b.asset_type === 'native')?.balance || '0';
      const usdBalance = account.balances.find((b: any) => b.asset_code === 'USD')?.balance || '0';
      
      return {
        xlm: xlmBalance,
        usd: usdBalance
      };
    } catch (error: any) {
      console.error('Failed to get account balance:', error);
      throw new Error(`Failed to get account balance: ${error?.message || 'Unknown error'}`);
    }
  }
}

// Create a singleton instance for use throughout the app
const stellarTrader = new StellarTrader('testnet');
export default stellarTrader;
